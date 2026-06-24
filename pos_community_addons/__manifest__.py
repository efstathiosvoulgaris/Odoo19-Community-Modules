# -*- coding: utf-8 -*-
{
    "name": "POS Community Addons",
    "summary": "Restaurant POS customizations: kitchen receipts, floor plan styling, streamlined UI",
    "version": "1.7",
    "description": """Coffee-shop optimised POS restaurant UI for Odoo 19 Community.

Changelog
---------
* 1.7 — Mobile UX improvements
  - Floor plan: minimum 65×65 px touch target for position-mode tables on
    screens ≤768 px wide, preventing accidental mis-taps on small tables.
  - Orderline sent/unsent visual separation: unsent lines (has-change) get
    an amber left border; sent lines are dimmed (opacity 0.55) so staff can
    immediately see what still needs to go to the kitchen.
  - Swipe-to-delete: swipe an order line left > 80 px to remove it. The
    background turns red as threshold feedback; the line animates out before
    removal. Scoped to display mode only (does not affect receipt view).

* 1.6 — Clean customer receipt
  - Replaced Odoo's default OrderReceipt with pos_community_addons.CustomerReceipt.
  - Shows: company header (name, address, phone, custom header text), date/time,
    order reference, table, cashier, lines with qty + name + price_subtotal_incl,
    discount note per line (percentage only), grand total, payment method(s),
    change amount. No tax breakdown, no product attributes/variants.

* 1.5 — Receipt printer offline fallback
  - Patched PosStore.printReceipt() so that when the receipt printer is
    unreachable the receipt is rendered to HTML and opened in a browser
    print dialog (window.open + auto window.print()). Covers both the
    auto-print after payment and manual reprint from the completed orders
    list (TicketScreen). Falls back to an iframe overlay if popups are
    blocked. nb_print counter still increments normally.

* 1.4 — Printer offline fallback
  - When the preparation printer is unreachable, instead of showing
    "Αποτυχία εκτύπωσης" and blocking the workflow, the module now opens a
    browser print dialog automatically (window.open + auto window.print()).
    If the popup is blocked, an overlay iframe is injected in-page instead.
    In both cases the cashier can print to any local printer or save as PDF.
    RetryPrintPopup is suppressed (order is already saved in POS).

* 1.3 — Kitchen receipt fixes
  - order_change_receipt.xml added to assets (was missing from manifest).
  - Patched PosStore.getOrderData() to inject company_name and customer_count
    so both the XML template and the Epson JS builder share the same data.
  - Replaced hardcoded company name in XML kitchen receipt with dynamic
    data.company_name (works for any company, not just Erkyna Cafe).
  - Fixed transliterated Greek strings: ΕΣΩΤΕΡΙΚΗ ΣΗΜΕΙΩΣΗ, ΣΗΜΕΙΩΣΗ
    ΠΕΛΑΤΗ, ΑΝΤΙΓΡΑΦΟ.
  - Added /** @odoo-module **/ header to order_change_receipt.js.

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
            "pos_community_addons/static/src/overrides/order_change_receipt.xml",
            "pos_community_addons/static/src/overrides/barista_ticket.xml",
            "pos_community_addons/static/src/overrides/receipt_screen.js",
            "pos_community_addons/static/src/overrides/orderline_swipe.js",
            "pos_community_addons/static/src/css/mobile_overrides.css",
      ],
    },
    "images": ["static/description/icon.png", "static/description/banner.gif"],
    "currency": "USD",
    "installable": True,
    "application": True,
    "auto_install": False,
}
