# Repair Shop Tickets

An Odoo 19 module for managing repair jobs in a repair/service shop.

## Features

- **Ticket workflow**: New → In Progress → Waiting for Parts → Resolved → Picked Up
- **Parts & Labor**: Add parts from your product catalog with automatic price lookup, plus a separate labor charge
- **Assigned Technician**: Assign an existing employee to each ticket; technician name prints on the receipt
- **Stock consumption**: Resolving a ticket automatically deducts parts from warehouse stock; cancelling or reopening reverses the consumption
- **Customer & Technician Notes**: Two separate note fields — customer-facing notes on the left, internal technician notes on the right; neither prints on the receipt
- **One-click invoicing**: Generate a customer invoice directly from the ticket with dynamic VAT applied
- **80mm thermal receipt**: Bilingual (Greek/English) receipt based on the customer's language — includes itemized parts, dynamic VAT total, technician name, and full terms & conditions
- **Brands & Models**: Maintain a device catalog; filter and group tickets by brand or model
- **Job Types**: Categorize repairs for reporting and filtering
- **Chatter**: Log notes, send messages, and schedule activities on every ticket
- **Kanban & List views**: Visual overview of all open jobs grouped by status
- **Greek translation**: Full `el` locale included for all menus, fields, buttons, and receipts

## Workflow

```
New → In Progress ↔ Waiting for Parts → Resolved → Picked Up
         ↑                                   |
         └───────── Reopen (Repair Failed) ──┘
```

Cancel is available at any active stage with a confirmation dialog.

## Requirements

- **Odoo 19 Community Edition**
- The following built-in Odoo modules must be installed: `Accounting`, `Inventory`, `Employees`

## Configuration

Before using the module, ensure the following are set up in Odoo:

- **Sale Tax**: Go to Accounting → Configuration → Taxes and make sure at least one active sale tax (percentage type) exists for your company. This is used on invoices and printed dynamically on the receipt. If none is found, the receipt will show 0%.
- **Stock Locations**: The default internal stock location (`WH/Stock`) and production/consumption location must exist. These are created automatically by the Inventory module. If they are missing or renamed, stock consumption on ticket resolution will be silently skipped.
- **Employees**: Go to Employees and create your technician records before assigning them to tickets. The module does not allow creating employees from within a ticket.
- **Income Account**: At least one income account must exist in your Chart of Accounts (type: Income or Other Income). This is used when adding a labor line to an invoice.

## Installation

1. Copy the `service` folder into your Odoo addons directory
2. Update the apps list in Odoo
3. Install **Repair Shop Tickets**

## Dependencies

- `base`, `product`, `account`, `mail`, `stock`, `hr`

## License

LGPL-3 — See [LICENSE](LICENSE) for details.

## Author

Punished_Snake — efstathiosvoulgaris@gmail.com
