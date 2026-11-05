# Direct Print — Odoo 19 PDFs to the PC's printers

Two parts:

| | |
|---|---|
| `agent/print_agent.py` | **Print Agent** on each shop PC. Python stdlib, `127.0.0.1:8765`. Prints through `SumatraPDF.exe`. Settings page at <http://127.0.0.1:8765>: laser (A4) printer + copies, thermal (80mm) printer + copies, Odoo address, test print. Config in `%APPDATA%\PrintAgent\config.json`, log beside it. |
| `direct_print/` | Odoo addon (2.0). The **Print** button of any PDF report and the till's legal document (`l10n_gr_provider_pos`) go to the agent; no agent on the PC → the browser prints as before. |

The agent chooses the printer by page width: under 100 mm → thermal, otherwise
laser. ΑΛΠ (80mm) and ΤΙΜ (A4) already carry the right paper, so nothing is
configured in Odoo.

## Security

The agent only answers its own settings page and the configured Odoo address
(Origin check), only on `127.0.0.1` with a matching Host header (no DNS
rebinding), and every POST needs the `X-Print-Agent` header — which forces a
CORS preflight that other sites fail. Settings can only be changed from the
agent's own page. Chrome asks once per PC to let the Odoo site reach «apps on
this device» (Local Network Access): allow it.

## Build the setup

```powershell
pip install pyinstaller
winget install JRSoftware.InnoSetup
cd installer
.\build.ps1        # -> installer\Output\PrintAgent-2.0-Setup.exe
```

The setup installs per user (no admin) into `%LOCALAPPDATA%\PrintAgent`, starts
the agent at logon, puts «Ρυθμίσεις Εκτύπωσης» on the desktop and opens it at
the end.

## Check

```
python agent/print_agent.py --selftest
```

## Not done (add when needed)

Per-report routing, print log, ESC/POS, label printers — removed in 2.0. The
1.0 code is in git history.
