{  # pyright: ignore[reportUnusedExpression]
    "name": "Direct Print",
    "summary": "Print Odoo reports and POS receipts directly to local Windows printers",
    "description": """
Direct Print for Odoo 19
========================
Sends PDF reports and POS receipts directly to locally installed
Windows printers via a lightweight local print agent service.

Features:

- Direct PDF report printing (no download dialog)
- POS receipt printing to thermal printers
- Per-report printer routing with copy count
- Offline print queue with auto-retry
- Configurable agent URL with automatic port detection
- Systray status indicator
- Print history log in Odoo
- Label printing support
- Settings UI for printer selection

Requirements:

- Local Print Agent running on the same machine (see start_print_agent.bat)

Changelog
---------

* 1.0 — Initial public release.
""",
    "version": "1.0",
    "category": "Technical",
    "author": "Efstathios Voulgaris",
    "publisher": "Efstathios Voulgaris",
    "license": "LGPL-3",
    "depends": ["web", "point_of_sale", "base_setup"],
    "data": [
        "security/ir.model.access.csv",
        "views/direct_print_log_views.xml",
        "views/direct_print_route_views.xml",
        "views/res_config_settings_views.xml",
        "views/menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "direct_print/static/src/js/print_service.js",
            "direct_print/static/src/js/report_action_override.js",
            "direct_print/static/src/xml/systray_status.xml",
            "direct_print/static/src/js/systray_status.js",
            "direct_print/static/src/xml/settings_panel.xml",
            "direct_print/static/src/js/settings_panel.js",
        ],
        "point_of_sale._assets_pos": [
            "direct_print/static/src/js/print_service.js",
            "direct_print/static/src/js/pos_receipt_override.js",
        ],
    },
    "images": ["static/description/icon.png"],
    "installable": True,
    "application": True,
    "auto_install": False,
}
