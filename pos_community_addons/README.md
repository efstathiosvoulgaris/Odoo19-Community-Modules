# pos_community_addons

Coffee-shop optimised POS restaurant UI for **Odoo 19 Community** with `pos_restaurant`.

## Features

### Table renaming with free text
Tables on the floor plan can be renamed with any text (e.g. "Window 1", "Bar", "Terrace A") instead of numbers only.
- Adds a `table_name` (Char) field to `restaurant.table`.
- Rename dialog uses a text-input popup instead of the number popup.
- The label propagates everywhere: floor plan, order navbar, ticket screen.

### Streamlined coffee-shop UI
Removes POS restaurant features that are not useful in a coffee-shop context:
- **Course / Σειρά Πιάτων button** removed from both mobile and desktop layouts.
- **Select Partner button** removed from the mobile action bar.
- **"New" button** (desktop) removed — the Payment button is sufficient; baristas go straight to payment after sending the order.
- Mobile layout replaces the "New" button with a direct "Pay" button.

### Send-to-kitchen always available
Patches `ProductScreen.swapButton` so the Send / Payment button area is always shown for restaurant sessions, regardless of whether preparation printer categories are configured.

> **Note:** The Send button still requires at least one POS category to be assigned to both the preparation printer *and* the products. Without this, `nbrOfChanges` stays 0 and the Send button is hidden. See [Setup](#setup) below.

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

## Changelog

### 1.2
- Added `table_name` field and free-text rename flow.
- Patched `RestaurantTable.getName()` for consistent label display.
- Patched `ProductScreen.swapButton` to prevent the Send area from being hidden.
- Removed Course button from mobile and desktop layouts.
- Removed desktop "New" button from `ActionpadWidget`.
- Fixed broken XPath targeting a non-existent element.

### 1.0
- Initial public release.

## License

LGPL-3 — see [LICENSE](https://www.gnu.org/licenses/lgpl-3.0.html).

## Author

Efstathios Voulgaris
