# Purchase: Create Bill button

**Version:** 1.0 | **Odoo:** 19 | **License:** LGPL-3

Restores the one-click **Create Bill** button on the purchase order form, which
Odoo 19 removed in favour of the "Upload Bill" digitization widget.

## The problem

In Odoo 19 a confirmed purchase order only offers **Upload Bill** — you must
attach a vendor bill file to create the bill from the PO. The no-file paths that
remain in stock Odoo are indirect: select the PO in the list view and use the
header "Create Bills" action, or go to Accounting → Vendor Bills → New →
Auto-Complete.

## What this module does

Adds a **Create Bill / Δημιουργία Λογαριασμού** button next to "Upload Bill" on
the purchase order form, exactly as it behaved up to Odoo 18:

- Calls the standard `action_create_invoice` method (the same one the list-view
  "Create Bills" button uses) — no custom business logic.
- Visible only when the order has something billable
  (`invoice_status == 'to invoice'`), e.g. after the receipt is validated for
  "on received quantities" products.
- Restricted to users with billing access rights (`account.group_account_invoice`).

## Installation

Copy to your addons path, update the apps list, install **Purchase: Create Bill
button**. No configuration needed.

- Odoo version: 19.0 (Community)
- Dependencies: `purchase`
- Translations: Greek (el)

## Usage

Create PO → confirm → validate the receipt → reopen the PO → **Create Bill**
opens a draft vendor bill pre-filled from the order.
