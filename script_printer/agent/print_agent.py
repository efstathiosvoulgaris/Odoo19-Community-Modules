"""Print Agent — prints Odoo PDFs on this PC without a dialog.

Stdlib only. Listens on 127.0.0.1:PORT.

  GET  /              settings page (printers, copies, Odoo address, test print)
  GET  /status        Odoo asks whether the agent is here
  POST /print         body = PDF; page narrower than 100 mm -> receipt printer,
                      otherwise the A4 printer
  GET  /api/config    POST /api/config    POST /api/test?kind=a4|receipt

Only two origins are served: this agent's own page and the configured Odoo
address. Every POST needs the X-Print-Agent header, which no other site can
add without a CORS preflight — and the preflight is refused. The Host header
is checked too, so a DNS-rebound name cannot reach the agent.

    python print_agent.py            # run
    python print_agent.py --selftest # check the page-size detection
"""
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

PORT = 8765
HOSTS = {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}
SELF_ORIGINS = {f"http://{h}" for h in HOSTS}
MAX_BODY = 50 * 1024 * 1024
APP_DIR = Path(os.environ.get("APPDATA", Path.home())) / "PrintAgent"
CONFIG = APP_DIR / "config.json"
BASE = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
SUMATRA = next((p for p in (Path(sys.executable).parent / "SumatraPDF.exe",
                            BASE / "SumatraPDF.exe",
                            Path(__file__).parent.parent / "SumatraPDF.exe") if p.exists()),
               Path("SumatraPDF.exe"))
DEFAULTS = {"odoo_url": "https://dev.eskarlas.gr",
            "a4_printer": "", "a4_copies": 1,
            "receipt_printer": "", "receipt_copies": 1}

APP_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(filename=APP_DIR / "print_agent.log", level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("print_agent")
_lock = threading.Lock()


def load_config():
    try:
        return {**DEFAULTS, **json.loads(CONFIG.read_text(encoding="utf-8"))}
    except (OSError, ValueError):
        return dict(DEFAULTS)


def save_config(values):
    cfg = load_config()
    for key in DEFAULTS:
        if key in values:
            cfg[key] = values[key]
    cfg["odoo_url"] = str(cfg["odoo_url"]).strip().rstrip("/")
    for key in ("a4_copies", "receipt_copies"):
        cfg[key] = min(max(int(cfg[key] or 1), 1), 5)
    with _lock:
        CONFIG.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    return cfg


def list_printers():
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "[Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-Printer | Select-Object -ExpandProperty Name"],
        capture_output=True, timeout=20, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return [n.strip() for n in out.stdout.decode("utf-8", "replace").splitlines() if n.strip()]


def page_kind(pdf):
    """'receipt' when the first page is narrower than 100 mm, else 'a4'.
    ponytail: reads the first uncompressed /MediaBox — true for wkhtmltopdf
    output; a PDF that hides it in an object stream falls back to 'a4'."""
    m = re.search(rb"/MediaBox\s*\[\s*(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)", pdf)
    if not m:
        return "a4"
    width_mm = (float(m.group(3)) - float(m.group(1))) * 25.4 / 72
    return "receipt" if width_mm < 100 else "a4"


def print_pdf(pdf, kind=None):
    cfg = load_config()
    kind = kind or page_kind(pdf)
    printer, copies = cfg[f"{kind}_printer"], cfg[f"{kind}_copies"]
    if not printer:
        raise RuntimeError(f"Δεν έχει οριστεί εκτυπωτής για {kind}")
    fd, path = tempfile.mkstemp(suffix=".pdf", prefix="odoo_", dir=APP_DIR)
    with os.fdopen(fd, "wb") as f:
        f.write(pdf)
    try:
        subprocess.run([str(SUMATRA), "-print-to", printer,
                        "-print-settings", f"{copies}x,noscale", "-silent", path],
                       check=True, timeout=120,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.CalledProcessError:
        # Most often the printer is gone — e.g. an RDP-redirected one, whose
        # name changes with every session («ανακατεύθυνση από N»).
        if printer not in list_printers():
            raise RuntimeError(f"Ο εκτυπωτής «{printer}» δεν υπάρχει πια — "
                               "διαλέξτε άλλον στις Ρυθμίσεις Εκτύπωσης") from None
        raise
    finally:
        # Sumatra has spooled the job when it returns; the file is not needed.
        threading.Timer(30, lambda: Path(path).unlink(missing_ok=True)).start()
    log.info("printed %s on %s x%s (%d bytes)", kind, printer, copies, len(pdf))
    return printer


def test_pdf(kind):
    """A one-line PDF in the size of the chosen paper."""
    w, h = (227, 300) if kind == "receipt" else (595, 842)
    text = f"Print Agent - test {kind} - {time.strftime('%Y-%m-%d %H:%M')}"
    stream = f"BT /F1 9 Tf 10 {h - 30} Td ({text}) Tj ET".encode()
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {w} {h}] "
            f"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>".encode(),
            b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, offsets = b"%PDF-1.4\n", []
    for i, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    return out


class Handler(BaseHTTPRequestHandler):
    server_version = "PrintAgent"

    def log_message(self, fmt, *args):
        log.info("%s %s", self.address_string(), fmt % args)

    def _origin_ok(self):
        origin = self.headers.get("Origin")
        allowed = SELF_ORIGINS | {load_config()["odoo_url"]}
        return self.headers.get("Host") in HOSTS and (origin is None or origin in allowed)

    def _send(self, code, body=b"", ctype="application/json"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        origin = self.headers.get("Origin")
        if origin and self._origin_ok():
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        if not self._origin_ok():
            return self._send(403, {"error": "origin"})
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", self.headers.get("Origin", ""))
        self.send_header("Access-Control-Allow-Methods", "GET, POST")
        self.send_header("Access-Control-Allow-Headers", "X-Print-Agent, Content-Type")
        # Chrome's Private/Local Network Access preflight
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.send_header("Vary", "Origin")
        self.end_headers()

    def do_GET(self):
        if not self._origin_ok():
            return self._send(403, {"error": "origin"})
        path = urlparse(self.path).path
        if path == "/":
            return self._send(200, SETTINGS_HTML, "text/html; charset=utf-8")
        if path == "/status":
            cfg = load_config()
            return self._send(200, {"ok": True, "a4": bool(cfg["a4_printer"]),
                                    "receipt": bool(cfg["receipt_printer"])})
        if path == "/api/config":
            try:
                printers = list_printers()
            except Exception as e:  # noqa: BLE001 — shown on the page
                log.warning("printer list failed: %s", e)
                printers = []
            return self._send(200, {"config": load_config(), "printers": printers})
        self._send(404, {"error": "not found"})

    def do_POST(self):
        if not self._origin_ok() or self.headers.get("X-Print-Agent") != "1":
            return self._send(403, {"error": "origin"})
        url = urlparse(self.path)
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            return self._send(413, {"error": "too large"})
        body = self.rfile.read(length)
        try:
            if url.path == "/print":
                if not body.startswith(b"%PDF"):
                    return self._send(400, {"error": "not a PDF"})
                return self._send(200, {"ok": True, "printer": print_pdf(body)})
            # Settings: only from the agent's own page.
            if self.headers.get("Origin") not in SELF_ORIGINS:
                return self._send(403, {"error": "origin"})
            if url.path == "/api/config":
                return self._send(200, {"ok": True, "config": save_config(json.loads(body or b"{}"))})
            if url.path == "/api/test":
                kind = parse_qs(url.query).get("kind", ["a4"])[0]
                kind = kind if kind in ("a4", "receipt") else "a4"
                return self._send(200, {"ok": True, "printer": print_pdf(test_pdf(kind), kind)})
        except Exception as e:  # noqa: BLE001 — reported to the caller
            log.exception("POST %s failed", url.path)
            return self._send(500, {"error": str(e)})
        self._send(404, {"error": "not found"})


SETTINGS_HTML = """<!doctype html>
<html lang="el"><head><meta charset="utf-8"><title>Ρυθμίσεις Εκτύπωσης</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
 body{font-family:Segoe UI,Arial,sans-serif;max-width:560px;margin:32px auto;padding:0 16px;color:#222}
 h1{font-size:22px} fieldset{border:1px solid #ccc;border-radius:8px;margin:0 0 16px;padding:12px 16px}
 legend{font-weight:600} label{display:block;margin:8px 0 4px}
 select,input{width:100%;padding:6px;box-sizing:border-box;font-size:14px}
 .row{display:flex;gap:8px;align-items:end} .row>div{flex:1} .row input[type=number]{width:80px}
 button{padding:8px 14px;font-size:14px;border-radius:6px;border:1px solid #888;background:#f4f4f4;cursor:pointer}
 button.primary{background:#714b67;color:#fff;border-color:#714b67}
 #msg{margin-top:12px;min-height:1.2em} .ok{color:#1a7f37} .err{color:#b00020}
</style></head><body>
<h1>Ρυθμίσεις Εκτύπωσης</h1>
<p class="ok">● Ο agent λειτουργεί σε αυτό το PC.</p>
<fieldset><legend>Τιμολόγια — Laser (A4)</legend>
 <div class="row"><div><label>Εκτυπωτής</label><select id="a4_printer"></select></div>
 <div><label>Αντίγραφα</label><input id="a4_copies" type="number" min="1" max="5"></div></div>
 <p><button onclick="test('a4')">Δοκιμαστική εκτύπωση</button></p></fieldset>
<fieldset><legend>Αποδείξεις — Θερμικός (80mm)</legend>
 <div class="row"><div><label>Εκτυπωτής</label><select id="receipt_printer"></select></div>
 <div><label>Αντίγραφα</label><input id="receipt_copies" type="number" min="1" max="5"></div></div>
 <p><button onclick="test('receipt')">Δοκιμαστική εκτύπωση</button></p></fieldset>
<fieldset><legend>Odoo</legend><label>Διεύθυνση</label><input id="odoo_url"></fieldset>
<button class="primary" onclick="save()">Αποθήκευση</button>
<div id="msg"></div>
<script>
const F=["a4_printer","a4_copies","receipt_printer","receipt_copies","odoo_url"];
const $=id=>document.getElementById(id);
const say=(t,ok)=>{$("msg").textContent=t;$("msg").className=ok?"ok":"err"};
async function call(path,body){
 const r=await fetch(path,{method:"POST",headers:{"X-Print-Agent":"1","Content-Type":"application/json"},body:JSON.stringify(body||{})});
 const j=await r.json(); if(!r.ok) throw new Error(j.error||r.status); return j;}
async function load(){
 const {config,printers}=await (await fetch("/api/config")).json();
 for(const k of ["a4_printer","receipt_printer"]){
  const s=$(k); s.innerHTML='<option value="">— κανένας —</option>';
  for(const p of new Set([...printers,config[k]].filter(Boolean))){const o=new Option(p,p);s.add(o)}
  s.value=config[k]||"";}
 for(const k of F) if(!k.endsWith("_printer")) $(k).value=config[k];
 if(!printers.length) say("Δεν βρέθηκαν εκτυπωτές στα Windows.",false);}
async function save(){
 const v={}; for(const k of F) v[k]=$(k).value;
 try{await call("/api/config",v);say("Αποθηκεύτηκε.",true)}catch(e){say("Σφάλμα: "+e.message,false)}}
async function test(kind){
 try{await save();const j=await call("/api/test?kind="+kind);say("Στάλθηκε στον "+j.printer+".",true)}
 catch(e){say("Σφάλμα: "+e.message,false)}}
load();
</script></body></html>"""


def selftest():
    assert page_kind(test_pdf("receipt")) == "receipt"
    assert page_kind(test_pdf("a4")) == "a4"
    assert page_kind(b"%PDF-1.4 no box") == "a4"
    # 80 mm roll as wkhtmltopdf writes it
    assert page_kind(b"/MediaBox [0 0 226.771654 841.889764]") == "receipt"
    print("selftest ok")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
        sys.exit()
    log.info("listening on 127.0.0.1:%s", PORT)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
