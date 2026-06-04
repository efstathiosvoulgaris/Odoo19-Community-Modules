
# Odoo 19 Direct Print Integration

Bridges Odoo 19's web interface with your local Windows printers. PDF reports (invoices, picking lists, etc.) and POS thermal receipts are sent directly to the printer — no download dialog, no browser print preview.

## How It Works

1. **Local Print Agent** (`local_printer_service.py`) — A lightweight Flask service running on your Windows machine (default port 5000). Receives print jobs from the Odoo browser client and dispatches them to local printers using SumatraPDF for PDFs and raw ESC/POS commands for thermal receipts.

2. **Odoo Addon** (`direct_print`) — A custom Odoo 19 module that intercepts print actions in the browser and routes them to the local agent. Includes a settings UI, per-report printer routing, print history log, and a systray status indicator.

---

## Features

- **Direct PDF printing** — Reports open silently in the printer; no download dialog.
- **POS receipt printing** — Sends raw ESC/POS text to thermal printers; falls back to HTML for regular printers.
- **Label printing** — Dedicated endpoint for label/thermal printers, tracked separately in the log.
- **Print Routes** — Assign a specific printer and copy count per report type (e.g. always print invoices to the office laser on 2 copies).
- **Settings UI** — Select your PDF and receipt printers directly from the Odoo interface. No browser console needed.
- **Systray indicator** — Shows agent online/offline status in the Odoo top bar. Click to refresh or open settings.
- **Offline queue** — If the agent is temporarily unreachable, jobs are queued and retried automatically for up to ~2 minutes.
- **Print history log** — All print jobs (success and error) are recorded in Odoo under Direct Print → Print Log.
- **Configurable agent URL** — Change the port if 5000 is already in use; port auto-detection scans 5000–5004.

---

## Installation

### Prerequisites

- **Python 3.10+** — must be on PATH (`python --version` should work in a terminal).
- **Odoo 19** — installed as a Windows service on the same machine.

### Step 1 — Run the deployment script

1. Open this folder in Windows Explorer.
2. Double-click **`deploy.bat`** and allow Administrator privileges when prompted.

The script will:
- Install Python dependencies (`flask`, `flask-cors`, `pywin32`).
- Download SumatraPDF if not already present (needed for silent PDF printing).
- Add the Odoo `thirdparty` folder to the System PATH (so Odoo can find `wkhtmltopdf`).
- Create a Startup shortcut so the Print Agent launches automatically on login.
- Restart the Odoo Windows service to apply PATH changes.

### Step 2 — Install the Odoo addon

1. Copy the **`direct_print`** folder to your Odoo addons directory.
   - Typical path: `C:\Program Files\Odoo 19.0.xxxxx\server\addons\`
2. Open Odoo in your browser and log in as Administrator.
3. Enable **Developer Mode** (Settings → scroll to the bottom → Activate Developer Mode).
4. Go to **Apps** → click **Update Apps List**.
5. Search for **Direct Print** and click **Install**.

### Step 3 — Start the Print Agent

Double-click **`start_print_agent.bat`** (or reboot — the installer created a Startup shortcut).

Verify it's running by opening `http://127.0.0.1:5000` in your browser. You should see the agent dashboard listing your installed printers.

---

## Configuration

### Selecting printers

1. In Odoo, open the **Direct Print** menu → **Settings**.
2. The page shows whether the agent is online and lists all printers installed on your Windows machine.
3. Select your **PDF / Report Printer** (used for all PDF reports by default).
4. Select your **Receipt / Thermal Printer** (used for POS receipts).
5. Click **Save Settings**.

Printer selections are stored per browser (localStorage). Each workstation can have its own printer mapped without affecting others.

### Per-report routing (Print Routes)

To send a specific report to a different printer or always print multiple copies:

1. Go to **Direct Print** → **Print Routes**.
2. Click **New**.
3. Enter the report's technical name (e.g. `account.report_invoice_with_payments`) — visible in the URL when you normally open a report.
4. Set the target **Printer** and **Copies**.
5. Save and activate the route.

Routes take priority over the default printer selection.

### Changing the agent port

If port 5000 is already in use:

1. Start `local_printer_service.py` with a different port by editing `AGENT_PORT` at the top of the file.
2. In Odoo, go to **Direct Print** → **Settings** and update the **Agent URL** field (admin only).

The agent also auto-detects nearby ports (5000–5004) on startup, so changing the port and restarting Odoo is usually enough.

---

## Monitoring

- **Dashboard** — `http://127.0.0.1:5000` shows service status, installed printers, and the last 100 print jobs.
- **Print Log** — Odoo menu → **Direct Print** → **Print Log** shows all jobs with status, printer, copies, and error details.
- **Systray** — The printer icon in the Odoo top bar shows green (online) or red (offline). Click it for a quick status view and Refresh button.
- **Log file** — `logs/print_agent.log` contains detailed agent-side output.

---

## Uninstallation

Follow these steps in order to avoid crashing Odoo:

1. **Uninstall the module from Odoo** — Apps menu → search "Direct Print" → Uninstall.
2. **Delete the addon folder** — Remove `direct_print` from your Odoo `addons` directory.
3. **Run `uninstall.bat`** — Removes the Startup shortcut and restarts the Odoo service to clear the module cache.
4. **Delete this folder** — The `script_printer` directory can now be safely removed.
