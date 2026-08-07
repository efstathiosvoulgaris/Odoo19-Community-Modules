# pos_community_addons

**Version:** 1.8 | **Odoo:** 19 Community | **License:** LGPL-3

Coffee-shop optimised POS restaurant UI for **Odoo 19 Community** with `pos_restaurant`.

## Features

### Table renaming with free text
Tables on the floor plan can be renamed with any text (e.g. "Window 1", "Bar", "Terrace A") instead of numbers only.
- Adds a `table_name` (Char) field to `restaurant.table`.
- Rename dialog uses a text-input popup instead of the number popup.
- The label propagates everywhere: floor plan, order navbar, ticket screen, payment screen.

### Floor plan enhancements
- Occupancy time badge per table (green < 30 min, yellow 30–60 min, red > 60 min).
- Change count badge (top-right, red) — items not yet sent to the kitchen.
- Item count badge (bottom, dark) — total items on the table.
- Red border + glow on occupied tables.
- Minimum 65 × 65 px touch target on mobile for position-mode tables.

### Streamlined coffee-shop UI — «Απλοποιημένο Ταμείο»
An option, **not** a deletion: *Point of Sale → Configuration → Settings → PoS
Interface → Απλοποιημένο Ταμείο*. On by default for restaurant tills, off
everywhere else. While it is on:
- **Course / Σειρά Πιάτων button** hidden on both mobile and desktop layouts.
- **Select Partner button** hidden in the mobile action bar.
- **"New" button** (desktop) hidden — the Payment button is sufficient; the
  mobile layout shows a direct "Pay" button in its place.
- Tip and Customer buttons hidden on mobile via CSS.

Untick it on a till that needs a customer on the order — a bar issuing a
Τιμολόγιο (ΤΙΜ) to a company, for instance, which needs the customer selector
to pick a partner with ΑΦΜ.

> Nodes are hidden with `position="attributes"`, never removed with
> `position="replace"`. A node an override deletes is gone from **every** till
> in the database, new ones included, and no setting can bring it back — which
> is exactly how ΤΙΜ issuance was blocked before 1.8. Core `t-if` conditions
> are preserved, since `position="attributes"` overwrites them otherwise.

### Customer receipt is skipped on a fiscal till
The clean `CustomerReceipt` template applies only where the receipt is not a
legal document. On a till issuing through `l10n_gr_provider_pos` the thermal
receipt is what prints when the sale never reached the provider, and it must
carry the ΜΑΡΚ/QR block or the TF-1/TF-2 notice — both inherits of
`point_of_sale.OrderReceipt`. The choice is made per session in
`PosStore.afterProcessServerData`, once the config is known.

### Send-to-kitchen always available
Patches `ProductScreen.swapButton` so the Send / Payment button area is always shown for restaurant sessions, regardless of whether preparation printer categories are configured.

> **Note:** The Send button still requires at least one POS category to be assigned to both the preparation printer *and* the products. Without this, `nbrOfChanges` stays 0 and the Send button is hidden. See [Setup](#setup) below.

### Kitchen receipt (preparation printers)
- Dynamic company name (no hardcoded strings).
- Full kitchen layout: order reference, time, employee, grouped item lines with qty / name / attributes / internal notes.
- Correct Greek labels: ΕΣΩΤΕΡΙΚΗ ΣΗΜΕΙΩΣΗ, ΣΗΜΕΙΩΣΗ ΠΕΛΑΤΗ, ΑΝΤΙΓΡΑΦΟ.
- Printer offline fallback: opens a browser print dialog automatically (window.open + auto window.print()); falls back to an in-page iframe if popups are blocked.

### Customer receipt (receipt printers)
Clean, coffee-shop-appropriate layout replacing Odoo's default receipt:
- Company header: name, address, phone, custom header text.
- Order meta: date / time, order reference, table, cashier.
- Lines: qty × product name + price per line (no attributes, no tax breakdown).
- Discount note per line (percentage only) if applicable.
- Grand total (large bold), payment method(s), change.
- Footer: "Σας ευχαριστούμε!"
- Printer offline fallback: same browser-print mechanism as kitchen receipt.
- Auto-prints on payment and returns directly to the floor plan.

### Order line UX improvements
- **Sent / unsent visual separation**: unsent lines get an amber left border; sent lines are dimmed (opacity 0.55), giving staff an instant view of what still needs to go to the kitchen.
- **Swipe-to-delete**: swipe a line left > 80 px to remove it. The background turns red as threshold feedback; the item animates out before removal. Display mode only — receipts are unaffected.

---

## Requirements

| Dependency | Version |
|---|---|
| Odoo Community | 19 |
| `pos_restaurant` | bundled with Odoo 19 |

## Installation

1. Copy the `pos_community_addons` folder into your Odoo addons path (e.g. `server/addons/`).
2. Restart the Odoo server.
3. Enable developer mode, go to **Apps**, search for *POS Community Addons*, and install.
4. Upgrade the module if updating from a previous version:
   ```
   python odoo-bin -u pos_community_addons -d <your_db>
   ```

## Setup

### Preparation printer (required for Send button)

1. **Point of Sale → Configuration → Settings → your POS config**
2. Under **Equipment → Preparation Printers**, open your printer.
3. In **Printed Product Categories**, add every POS category whose products should be sent to the kitchen.
4. Save.

### Products

Each product that should trigger the Send button must have at least one **Point of Sale Category** assigned (product form → *Point of Sale* tab → *POS Category*).

When both the printer and the products share a category, `nbrOfChanges > 0` as soon as items are added to the order, and the Send button appears automatically.

## What is NOT affected

Non-restaurant POS configurations are unaffected. All patches check `pos.config.module_pos_restaurant` at runtime and fall back to standard behaviour when it is `false`.

---

## Changelog

### 1.8
- The streamlined UI became the per-till option «Απλοποιημένο Ταμείο»
  (`pos_ca_simple_ui`, POS settings → PoS Interface), defaulting to on for
  restaurant tills and off elsewhere.
- Buttons are hidden, not removed. The customer selector and the «Τιμολόγιο»
  button had been deleted outright, which killed them on every till in the
  database and made ΤΙΜ issuance impossible; the payment-screen override is
  gone entirely and the actionpad one now sets attributes, preserving the core
  conditions it used to overwrite.
- `OrderReceipt.template` is chosen per session instead of at module load, so a
  provider till keeps Odoo's receipt and its legal markings block.

### 1.7
- Floor plan: minimum 65 × 65 px touch target for position-mode tables on screens ≤ 768 px.
- Order lines: amber left border on unsent items (`has-change`); sent items dimmed to opacity 0.55.
- Swipe-to-delete: swipe an order line left > 80 px to remove it (display mode only).

### 1.6
- Replaced Odoo's default `OrderReceipt` with a clean `pos_community_addons.CustomerReceipt` template.
- Shows: company header, date/time, order reference, table, cashier, lines with qty + name + `price_subtotal_incl`, discount note, grand total, payment method(s), change. No tax breakdown, no product attributes.

### 1.5
- Receipt printer offline fallback: renders the receipt to HTML and opens a browser print dialog on failure. Covers both auto-print after payment and manual reprint from the completed-orders list.

### 1.4
- Preparation printer offline fallback: opens a browser print dialog instead of showing "Αποτυχία εκτύπωσης". Falls back to an in-page iframe if popups are blocked. `RetryPrintPopup` suppressed.

### 1.3
- `order_change_receipt.xml` added to assets (was missing from manifest).
- `getOrderData()` patched to inject `company_name` and `customer_count` dynamically.
- Replaced hardcoded company name in kitchen receipt template.
- Fixed transliterated Greek strings: ΕΣΩΤΕΡΙΚΗ ΣΗΜΕΙΩΣΗ, ΣΗΜΕΙΩΣΗ ΠΕΛΑΤΗ, ΑΝΤΙΓΡΑΦΟ.
- Added `/** @odoo-module **/` header to `order_change_receipt.js`.

### 1.2
- Added `table_name` field and free-text rename flow.
- Patched `RestaurantTable.getName()` for consistent label display.
- Patched `ProductScreen.swapButton` to prevent the Send area from being hidden.
- Removed Course button from mobile and desktop layouts.
- Removed desktop "New" button from `ActionpadWidget`.
- Fixed broken XPath targeting a non-existent element.

### 1.0
- Initial public release.

---

## License

LGPL-3 — see [LICENSE](https://www.gnu.org/licenses/lgpl-3.0.html).

## Author

Efstathios Voulgaris
