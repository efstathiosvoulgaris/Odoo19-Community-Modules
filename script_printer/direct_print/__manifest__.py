{
    "name": "Direct Print",
    "summary": "Odoo PDFs straight to the PC's laser / thermal printer through the local Print Agent",
    "description": """
Sends report PDFs and the till's legal document to the Print Agent running
on the PC (script_printer/agent). The agent picks the printer by page size:
80mm to the thermal, everything else to the laser, as set on its own
settings page (http://127.0.0.1:8765). Without an agent the browser prints
as before.

Changelog
---------

* 2.1 — Hide the POS «Local Network Access» menu entry.
* 2.0 — Rewrite: printers, copies and Odoo address are set on the agent;
  routes, print log, settings panel, systray and ESC/POS removed.
* 1.0 — Initial release.
""",
    "version": "2.1",
    "category": "Technical",
    "author": "Efstathios Voulgaris",
    "license": "LGPL-3",
    "depends": ["web", "l10n_gr_provider_pos"],
    "assets": {
        "web.assets_backend": [
            "direct_print/static/src/agent.js",
            "direct_print/static/src/report_handler.js",
        ],
        "point_of_sale._assets_pos": [
            "direct_print/static/src/agent.js",
            "direct_print/static/src/pos_legal_print.js",
            "direct_print/static/src/pos_navbar.xml",
        ],
    },
    "images": ["static/description/icon.png"],
    "installable": True,
    "application": False,
}
