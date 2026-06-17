# -*- coding: utf-8 -*-
{
    "name": "POS Community Addons",
    "summary": "Restaurant POS customizations: kitchen receipts, floor plan styling, streamlined UI",
    "version": "1.2",
    "description": """Coffee-shop optimised POS restaurant UI for Odoo 19 Community.

Changelog
---------
* 1.2 — pos_restaurant compatibility pass
  - Added table_name (Char) field to restaurant.table; tables can now be
    renamed with free text instead of numbers only.
  - Patched RestaurantTable.getName() so table labels propagate everywhere
    (floor plan, order navbar, ticket screen).
  - Patched FloorScreen.renameTable() to open a text-input popup instead of
    a number popup.
  - Patched ProductScreen.swapButton to always return true for restaurant
    sessions so the Send button area is never hidden by a missing printer-
    category check.
  - Removed Course / Σειρά Πιάτων button from both the mobile ActionpadWidget
    and the desktop ControlButtons row.
  - Removed the desktop "New" button from ActionpadWidget (Payment button
    already present; coffee shops go straight to payment after sending).
  - Fixed broken XPath that tried to remove a non-existent element.

* 1.0 — Initial public release.""",
    "author": "Efstathios Voulgaris",
    "publisher": "Efstathios Voulgaris",
    "category": "Point of Sale",
    "license": "LGPL-3",
    "depends": ["pos_restaurant"],
    "assets": {
      'point_of_sale._assets_pos': [
            "pos_community_addons/static/src/floor_screen/floor_screen.js",
            "pos_community_addons/static/src/floor_screen/floor_screen.xml",
            "pos_community_addons/static/src/overrides/product_screen.js",
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
