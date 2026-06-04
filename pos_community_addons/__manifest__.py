# -*- coding: utf-8 -*-
{
    "name": "POS Community Addons",
    "summary": "Restaurant POS customizations: kitchen receipts, floor plan styling, streamlined UI",
    "version": "1.0",
    "description": "Initial public release.\n\nChangelog\n---------\n* 1.0 — Initial public release.",
    "author": "Efstathios Voulgaris",
    "publisher": "Efstathios Voulgaris",
    "category": "Point of Sale",
    "license": "LGPL-3",
    "depends": ["pos_restaurant"],
    "assets": {
      'point_of_sale._assets_pos': [
            "pos_community_addons/static/src/floor_screen/floor_screen.xml",
            "pos_community_addons/static/src/overrides/actionpad_widget.xml",
            "pos_community_addons/static/src/overrides/product_screen.xml",
            "pos_community_addons/static/src/overrides/payment_screen.xml",
            "pos_community_addons/static/src/overrides/order_change_receipt.js",
            "pos_community_addons/static/src/overrides/barista_ticket.xml",
            "pos_community_addons/static/src/overrides/receipt_screen.js",
            "pos_community_addons/static/src/css/mobile_overrides.css",
      ],
    },
    "images": ["static/description/icon.png", "static/description/banner.gif"],
    "currency": "USD",
    "installable": True,
    "application": True,
    "auto_install": False,
}
