# Repair Shop Tickets

An Odoo 19 module for managing repair jobs in a repair/service shop.

## Features

- **Ticket workflow**: New → In Progress → Waiting for Parts → Resolved → Ready for Pickup → Picked Up
- **Parts & Labor**: Add parts from your product catalog with automatic price lookup, plus a separate labor charge
- **Stock consumption**: Resolving a ticket automatically deducts parts from warehouse stock; cancelling or reopening reverses the consumption
- **Customer & Technician Notes**: Two separate note fields — one visible to the customer-facing side, one for internal technician use
- **One-click invoicing**: Generate a customer invoice directly from the ticket with dynamic VAT applied
- **80mm thermal receipt**: Bilingual (Greek/English) receipt based on the customer's language — includes itemized parts, dynamic VAT total, and full terms & conditions
- **Brands & Models**: Maintain a device catalog; filter and group tickets by brand or model
- **Job Types**: Categorize repairs for reporting and filtering
- **Chatter**: Log notes, send messages, and schedule activities on every ticket
- **Kanban & List views**: Visual overview of all open jobs grouped by status
- **Greek translation**: Full `el` locale included for all menus, fields, buttons, and receipts

## Workflow

```
New → In Progress ↔ Waiting for Parts → Resolved → Ready for Pickup → Picked Up
                                           ↑                    |
                                           └─ Reopen (Repair Failed)
```

Cancel is available at any active stage with a confirmation dialog.

## Installation

1. Copy the `service` folder into your Odoo addons directory
2. Update the apps list in Odoo
3. Install **Repair Shop Tickets**

## Dependencies

- `base`, `product`, `account`, `mail`, `stock`

## License

OPL-1 — See [LICENSE](LICENSE) for details.

## Author

Punished_Snake — efstathiosvoulgaris@gmail.com
