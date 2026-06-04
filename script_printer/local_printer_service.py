"""
Odoo 19 Direct Print — Local Print Agent
=========================================
A Flask service running on Windows that receives print jobs from the
Odoo browser client and dispatches them to locally installed printers.

Supports:
  - PDF reports  → printed via SumatraPDF (silent, command-line)
  - Raw receipts → sent directly to thermal printers via win32print (RAW)
  - HTML receipts→ rendered to a temp HTML file and printed via the OS

Endpoints:
  GET  /                → Status dashboard (HTML)
  GET  /status          → Health-check JSON
  GET  /get_printers    → List of installed Windows printers
  POST /print_pdf       → Print a PDF (base64-encoded body)
  POST /print_receipt   → Print raw ESC/POS text to thermal printer
  POST /print_html      → Print HTML content (for receipts on regular printers)
"""

import base64
import datetime
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from collections import deque
from pathlib import Path

from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS

try:
    import win32print
    import win32api
except ImportError:
    print("ERROR: pywin32 is required. Run: pip install pywin32")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
AGENT_HOST = "127.0.0.1"
AGENT_PORT = 5000
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "print_agent.log"
TMP_DIR = LOG_DIR / "tmp"
TMP_DIR.mkdir(exist_ok=True)

# SumatraPDF — will be auto-detected or downloaded by install.bat
SUMATRA_PATHS = [
    Path(__file__).parent / "SumatraPDF" / "SumatraPDF.exe",
    Path(r"C:\Program Files\SumatraPDF\SumatraPDF.exe"),
    Path(r"C:\Program Files (x86)\SumatraPDF\SumatraPDF.exe"),
    Path(os.environ.get("LOCALAPPDATA", "")) / "SumatraPDF" / "SumatraPDF.exe",
]

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("PrintAgent")

# ---------------------------------------------------------------------------
# Print job history (in-memory, last 100)
# ---------------------------------------------------------------------------
job_history = deque(maxlen=100)
job_lock = threading.Lock()


def _record_job(job_type, printer, status, detail=""):
    with job_lock:
        job_history.appendleft({
            "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "type": job_type,
            "printer": printer,
            "status": status,
            "detail": detail[:200],
        })


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def find_sumatra():
    """Locate SumatraPDF executable."""
    for p in SUMATRA_PATHS:
        if p.exists():
            log.info("SumatraPDF found at %s", p)
            return str(p)
    # Try PATH
    which = shutil.which("SumatraPDF") or shutil.which("SumatraPDF.exe")
    if which:
        log.info("SumatraPDF found on PATH: %s", which)
        return which
    log.warning("SumatraPDF not found — PDF printing will use ShellExecute fallback")
    return None


SUMATRA_EXE = find_sumatra()


_printers_cache: list = []
_printers_cache_ts: float = 0.0
_PRINTERS_CACHE_TTL = 10  # seconds


def get_printers_list():
    global _printers_cache, _printers_cache_ts
    now = time.time()
    if _printers_cache and now - _printers_cache_ts < _PRINTERS_CACHE_TTL:
        return _printers_cache
    flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
    raw = win32print.EnumPrinters(flags)
    default = win32print.GetDefaultPrinter()
    _printers_cache = [{"name": p[2], "is_default": p[2] == default} for p in raw]
    _printers_cache_ts = now
    return _printers_cache


def _shell_execute_print(filepath, printer_name):
    args = f'/d:"{printer_name}"' if printer_name else None
    win32api.ShellExecute(0, "print", str(filepath), args, ".", 0)


def _schedule_cleanup(path, delay=15):
    def _run():
        time.sleep(delay)
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
    threading.Thread(target=_run, daemon=True).start()


def _print_pdf_bytes(pdf_bytes, printer_name, filename, copies, job_type, tmp_prefix):
    tmp_path = TMP_DIR / f"{tmp_prefix}_{int(time.time()*1000)}_{filename}"
    tmp_path.write_bytes(pdf_bytes)
    try:
        print_pdf_file(str(tmp_path), printer_name, copies)
        _record_job(job_type, printer_name or "(default)", "success", filename)
        log.info("%s printed: %s → %s", job_type, filename, printer_name or "(default)")
        return jsonify({"status": "success", "printer": printer_name or "(default)", "filename": filename})
    except Exception as e:
        _record_job(job_type, printer_name or "(default)", "error", str(e))
        log.error("%s print failed: %s", job_type, traceback.format_exc())
        return jsonify({"error": str(e)}), 500
    finally:
        _schedule_cleanup(tmp_path)


def print_pdf_file(pdf_path, printer_name=None, copies=1):
    """Print a PDF file. Uses SumatraPDF if available, else ShellExecute."""
    if SUMATRA_EXE:
        cmd = [SUMATRA_EXE, "-silent"]
        if printer_name:
            cmd += ["-print-to", printer_name]
        else:
            cmd.append("-print-to-default")
        if copies > 1:
            cmd += ["-print-settings", f"copies={copies}"]
        cmd.append(str(pdf_path))
        log.info("Printing PDF via SumatraPDF: %s", " ".join(cmd))
        result = subprocess.run(cmd, capture_output=True, timeout=60)
        if result.returncode != 0:
            raise RuntimeError(f"SumatraPDF exited with code {result.returncode}: {result.stderr.decode(errors='replace')}")
    else:
        # Fallback: ShellExecute "print" verb (no copies support)
        log.info("Printing PDF via ShellExecute: %s → %s", pdf_path, printer_name or "(default)")
        _shell_execute_print(pdf_path, printer_name)
        # ShellExecute is async — give it a moment
        time.sleep(2)


def print_raw(data_bytes, printer_name, doc_name="Odoo Receipt"):
    """Send raw bytes directly to a printer (RAW mode for ESC/POS thermal printers)."""
    log.info("RAW print to '%s' (%d bytes)", printer_name, len(data_bytes))
    hprinter = win32print.OpenPrinter(printer_name)
    try:
        win32print.StartDocPrinter(hprinter, 1, (doc_name, "", "RAW"))
        win32print.StartPagePrinter(hprinter)
        win32print.WritePrinter(hprinter, data_bytes)
        win32print.EndPagePrinter(hprinter)
        win32print.EndDocPrinter(hprinter)
    finally:
        win32print.ClosePrinter(hprinter)


def print_html_content(html, printer_name=None):
    """
    Write HTML to a temp file and print it via the OS default browser print.
    This is useful for POS receipts on regular (non-thermal) printers.
    """
    tmp = tempfile.NamedTemporaryFile(suffix=".html", delete=False, dir=str(LOG_DIR))
    try:
        tmp.write(html.encode("utf-8"))
        tmp.close()
        log.info("Printing HTML via ShellExecute: %s", tmp.name)
        _shell_execute_print(tmp.name, printer_name)
        time.sleep(3)
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Flask App
# ---------------------------------------------------------------------------
app = Flask(__name__)
CORS(app, origins=["http://localhost:*", "http://127.0.0.1:*", "http://192.168.*"])

# Increase max content length to 50 MB for large PDF reports
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024

# ---------------------------------------------------------------------------
# Dashboard template
# ---------------------------------------------------------------------------
DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Odoo Print Agent</title>
<style>
  :root { --bg: #0f172a; --card: #1e293b; --accent: #3b82f6; --green: #22c55e; --text: #f8fafc; --muted: #94a3b8; }
  * { margin:0; padding:0; box-sizing:border-box; }
  body { font-family: 'Segoe UI', system-ui, sans-serif; background: var(--bg); color: var(--text); min-height:100vh; }
  .container { max-width: 900px; margin: 0 auto; padding: 2rem 1rem; }
  h1 { font-size: 1.8rem; margin-bottom: .5rem; }
  h1 span { color: var(--accent); }
  .subtitle { color: var(--muted); margin-bottom: 2rem; }
  .status-bar { display:flex; gap:1rem; margin-bottom:2rem; flex-wrap:wrap; }
  .status-card { background: var(--card); border-radius: 12px; padding: 1.2rem 1.5rem; flex:1; min-width:200px; border: 1px solid #334155; }
  .status-card .label { color: var(--muted); font-size:.85rem; margin-bottom:.4rem; }
  .status-card .value { font-size:1.4rem; font-weight:700; }
  .dot { display:inline-block; width:10px; height:10px; border-radius:50%; margin-right:6px; background:var(--green); animation: pulse 2s infinite; }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.4} }
  table { width:100%; border-collapse:collapse; background:var(--card); border-radius:12px; overflow:hidden; border:1px solid #334155; }
  th { text-align:left; padding:.8rem 1rem; background:#334155; color:var(--muted); font-size:.8rem; text-transform:uppercase; letter-spacing:.05em; }
  td { padding:.7rem 1rem; border-top:1px solid #334155; font-size:.9rem; }
  .badge { display:inline-block; padding:2px 10px; border-radius:999px; font-size:.75rem; font-weight:600; }
  .badge-ok { background:#166534; color:#bbf7d0; }
  .badge-err { background:#991b1b; color:#fecaca; }
  .section-title { font-size:1.1rem; margin: 2rem 0 .8rem; }
  .printers li { padding:.4rem 0; color:var(--muted); }
  .printers li .name { color:var(--text); font-weight:500; }
  .printers li .default-tag { color:var(--accent); font-size:.75rem; margin-left:6px; }
  .empty { color:var(--muted); text-align:center; padding:2rem; }
  a { color:var(--accent); }
</style>
</head>
<body>
<div class="container">
  <h1>🖨️ Odoo <span>Print Agent</span></h1>
  <p class="subtitle">Local printer service for Odoo 19 — direct printing without dialogs</p>

  <div class="status-bar">
    <div class="status-card">
      <div class="label">Service Status</div>
      <div class="value"><span class="dot"></span> Running</div>
    </div>
    <div class="status-card">
      <div class="label">Printers Detected</div>
      <div class="value">{{ printer_count }}</div>
    </div>
    <div class="status-card">
      <div class="label">SumatraPDF</div>
      <div class="value">{{ 'Available ✓' if sumatra else 'Not found ✗' }}</div>
    </div>
    <div class="status-card">
      <div class="label">Total Jobs</div>
      <div class="value">{{ job_count }}</div>
    </div>
  </div>

  <h2 class="section-title">Installed Printers</h2>
  <ul class="printers" style="list-style:none; background:var(--card); border-radius:12px; padding:1rem 1.5rem; border:1px solid #334155;">
    {% for p in printers %}
    <li><span class="name">{{ p.name }}</span>{% if p.is_default %}<span class="default-tag">(default)</span>{% endif %}</li>
    {% endfor %}
  </ul>

  <h2 class="section-title">Recent Print Jobs</h2>
  {% if jobs %}
  <table>
    <tr><th>Time</th><th>Type</th><th>Printer</th><th>Status</th><th>Detail</th></tr>
    {% for j in jobs %}
    <tr>
      <td>{{ j.time }}</td>
      <td>{{ j.type }}</td>
      <td>{{ j.printer }}</td>
      <td><span class="badge {{ 'badge-ok' if j.status=='success' else 'badge-err' }}">{{ j.status }}</span></td>
      <td>{{ j.detail }}</td>
    </tr>
    {% endfor %}
  </table>
  {% else %}
  <div class="empty" style="background:var(--card); border-radius:12px; border:1px solid #334155;">No print jobs yet.</div>
  {% endif %}
</div>
</body>
</html>
"""

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def dashboard():
    printers = get_printers_list()
    with job_lock:
        jobs = list(job_history)
    return render_template_string(
        DASHBOARD_HTML,
        printers=printers,
        printer_count=len(printers),
        sumatra=SUMATRA_EXE is not None,
        jobs=jobs,
        job_count=len(jobs),
    )


@app.route("/status", methods=["GET"])
def status():
    return jsonify({
        "status": "running",
        "sumatra": SUMATRA_EXE is not None,
        "printer_count": len(get_printers_list()),
        "version": "1.0.0",
    })


@app.route("/get_printers", methods=["GET"])
def get_printers():
    """Returns all printers installed on this Windows PC."""
    printers = get_printers_list()
    return jsonify({"printers": printers})


@app.route("/print_pdf", methods=["POST"])
def handle_print_pdf():
    if request.content_type and "multipart" in request.content_type:
        f = request.files.get("pdf")
        if not f:
            return jsonify({"error": "No 'pdf' file in multipart request"}), 400
        pdf_bytes = f.read()
        printer_name = request.form.get("printer_name")
        filename = f.filename or "odoo_report.pdf"
        copies = max(1, int(request.form.get("copies", 1)))
    else:
        data = request.get_json(silent=True) or {}
        b64 = data.get("data")
        if not b64:
            return jsonify({"error": "Missing 'data' (base64 PDF)"}), 400
        try:
            pdf_bytes = base64.b64decode(b64)
        except Exception:
            return jsonify({"error": "Invalid base64 data"}), 400
        printer_name = data.get("printer_name")
        filename = data.get("filename", "odoo_report.pdf")
        copies = max(1, int(data.get("copies", 1)))
    return _print_pdf_bytes(pdf_bytes, printer_name, filename, copies, "PDF", "print")


@app.route("/print_receipt", methods=["POST"])
def handle_print_receipt():
    """
    Print raw text/ESC-POS data to a thermal printer.
    Expects JSON: { "printer_name": "...", "content": "...", "encoding": "utf-8" }
    """
    data = request.get_json(silent=True) or {}
    printer_name = data.get("printer_name")
    content = data.get("content")
    encoding = data.get("encoding", "utf-8")

    if not printer_name:
        return jsonify({"error": "Missing 'printer_name'"}), 400
    if not content:
        return jsonify({"error": "Missing 'content'"}), 400

    try:
        if isinstance(content, str):
            raw_bytes = content.encode(encoding)
        else:
            raw_bytes = base64.b64decode(content)
        print_raw(raw_bytes, printer_name)
        _record_job("Receipt", printer_name, "success", f"{len(raw_bytes)} bytes")
        return jsonify({"status": "success", "printer": printer_name})
    except Exception as e:
        _record_job("Receipt", printer_name, "error", str(e))
        log.error("Receipt print failed: %s", traceback.format_exc())
        return jsonify({"error": str(e)}), 500


@app.route("/print_html", methods=["POST"])
def handle_print_html():
    """
    Print HTML content (e.g. POS receipt) via the OS print dialog.
    Expects JSON: { "printer_name": "...", "html": "..." }
    """
    data = request.get_json(silent=True) or {}
    html = data.get("html")
    printer_name = data.get("printer_name")

    if not html:
        return jsonify({"error": "Missing 'html' content"}), 400

    try:
        print_html_content(html, printer_name)
        _record_job("HTML", printer_name or "(default)", "success", f"{len(html)} chars")
        return jsonify({"status": "success", "printer": printer_name or "(default)"})
    except Exception as e:
        _record_job("HTML", printer_name or "(default)", "error", str(e))
        log.error("HTML print failed: %s", traceback.format_exc())
        return jsonify({"error": str(e)}), 500


@app.route("/print_label", methods=["POST"])
def handle_print_label():
    data = request.get_json(silent=True) or {}
    b64 = data.get("data")
    if not b64:
        return jsonify({"error": "Missing 'data' (base64 PDF)"}), 400
    try:
        pdf_bytes = base64.b64decode(b64)
    except Exception:
        return jsonify({"error": "Invalid base64 data"}), 400
    printer_name = data.get("printer_name")
    filename = data.get("filename", "label.pdf")
    copies = max(1, int(data.get("copies", 1)))
    return _print_pdf_bytes(pdf_bytes, printer_name, filename, copies, "Label", "label")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    log.info("=" * 60)
    log.info("Odoo Print Agent starting on http://%s:%s", AGENT_HOST, AGENT_PORT)
    log.info("SumatraPDF: %s", SUMATRA_EXE or "NOT FOUND")
    printers = get_printers_list()
    for p in printers:
        tag = " (DEFAULT)" if p["is_default"] else ""
        log.info("  Printer: %s%s", p["name"], tag)
    log.info("=" * 60)
    app.run(host=AGENT_HOST, port=AGENT_PORT, debug=False)