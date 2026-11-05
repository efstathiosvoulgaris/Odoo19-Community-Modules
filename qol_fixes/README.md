# Odoo 19: Μικρές Διορθώσεις (QoL)

**Version:** 1.6 | **Odoo:** 19 | **License:** LGPL-3

Small, independent quality-of-life fixes for Odoo 19. No settings — every fix
is always on.

## Adding a fix

- One file per area: `views/<model>_views.xml`, `models/<model>.py` when
  Python is needed. A new area may need a new entry in `depends`; keep that
  list to what the fixes actually touch.
- Add a row to the table below and a changelog line in `__manifest__.py`,
  and bump the version.
- User-facing strings in English in the code, Greek in `i18n/el.po`.

## Fixes

| Since | Area | Fix |
|---|---|---|
| 1.0 | Purchase | **Create Bill / Δημιουργία Λογαριασμού** button on the purchase order form, next to "Upload Bill" (Odoo 19 removed it). Calls the standard `action_create_invoice`; visible only when `invoice_status == 'to invoice'`, for `account.group_account_invoice`. |
| 1.1 | Purchase | **Vendor Reference** (`partner_ref`) column shown by default in the three purchase order lists (RFQs, orders, KPI list). Core has it `optional="hide"`. A user's own column choice is kept. Vendor bills already show their reference by default. |
| 1.2 | Contacts | **Viber** button next to the mobile (`kinito`, from `l10n_gr_partner`) on the contact form. Opens `viber://chat?number=+30…` in the Viber app installed on the PC/phone; a 10-digit number is taken as Greek. Hidden when there is no mobile. |
| 1.3 | Eshop | **Eshop follows stock.** Every 15′ (cron «Eshop: δημοσίευση/απόσυρση με βάση το απόθεμα»): a saleable storable product with stock is published, without stock withdrawn. Skroutz follows by itself (its feed takes published products with an MPN). Per-product opt-out «Χωρίς αυτόματη δημοσίευση». Services/non-storable never touched. The cron ships **inactive**: the addons folder is shared by test and skarlas, so it is switched on per database. Since 1.5 the record is `noupdate`, so an upgrade leaves that switch alone (1.4's upgrade had turned it off in both databases). |
| 1.4 | Contacts | **Find a contact by mobile or phone** in every contact field (sale, service, CRM, invoices, ...) and in the contacts search «Όνομα»: `kinito` and `phone` added to `_rec_names_search`; a number typed with spaces/dashes («698 488 8478») is also tried digits-only. Not the POS (its customer search runs in the browser). |

## Considered and not done

- **Bill date = today on bills created from a PO.** The field is the date on
  the *vendor's* invoice and drives the accounting date and VAT period; a
  default of today would be wrong whenever the paper invoice is older, and
  the required-field check is what makes people look it up. Left empty.
- **Create Invoice on the sale order** — already in core (`invoice_status ==
  'to invoice'`).
- **Product search by barcode / internal reference on order lines** —
  already in core: `product.product._search_display_name` matches name,
  default_code (partial) and barcode (exact), plus vendor codes on purchases.

## Notes per fix

**Create Bill** hooks after the `purchase_file_uploader` widget. If a later
Odoo 19 release renames that widget, the view fails to load on upgrade —
change the xpath.

**Viber** needs the Viber app on the device; without it the browser does
nothing. `ir.actions.act_url` turns `viber://` into a relative path, hence the
tiny client action in `static/src/open_external_url.js`.

## Moving from `purchase_create_bill_button`

This module replaces `purchase_create_bill_button` 1.0. Install this one,
then uninstall the old one — while both are installed the button shows twice.
Nothing is stored, so nothing is lost.
