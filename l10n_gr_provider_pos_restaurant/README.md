# l10n_gr_provider_pos_restaurant — Δελτίο Παραγγελίας Εστίασης (8.6)

**Version:** 1.2 | **Odoo:** 19 | **License:** LGPL-3
**Spec refs:** AADE Α.1138/2020 as amended by Α.1170/2023 · ILYDA «Οδηγίες
υλοποίησης Διαβίβασης Δελτίων Παραγγελίας Εστίασης» §4, §5.2, §5.4

Every round a waiter sends to the kitchen is transmitted as one Δελτίο
Παραγγελίας Εστίασης (myDATA type 8.6) carrying the table number, the items and
their VAT. When the table pays, the retail document closes the open notes.

Auto-installs when `l10n_gr_provider_pos` and `pos_restaurant` are both present.

---

## Why it is not an `account.move`

An order note is informational, not a document of value. Posting an invoice per
kitchen round would book revenue that the closing ΑΛΠ books again, so notes live
in their own model (`l10n.gr.prov.catering.order`) and never touch accounting.
Only the closing document does.

---

## The 24-hour rule

A note left unclosed for 24 hours obliges the provider to **suspend transmission
for the whole entity** — not just that table. Everything below exists because of
that one sentence: the cancellation routes, the back-office list, the alert
cron.

Open notes are visible under **Λογιστική → myDATA → Δελτία Παραγγελίας
Εστίασης**, filtered «Ανοιχτά Δελτία».

---

## Configuration

**Point of Sale → Configuration → Settings → Πάροχος myDATA**

| Setting | Default | Description |
|---------|---------|-------------|
| **Δελτία Παραγγελίας Εστίασης (8.6)** | on | Issue a note per kitchen round. Mandatory for catering businesses using a provider. |
| **Αυτόματη Καθολική Ακύρωση** | on | Transmit a «Καθολική Ακύρωση 8.6» when the order is cancelled. Off, the notes stay open and must be cancelled by hand before the 24h limit. |
| **Αυτόματο Αρνητικό Δελτίο** | on | Transmit a negative note when an already-sent item is removed. |
| **Ειδοποίηση Ανοιχτών Δελτίων (ώρες)** | 20 | Activity on notes approaching the limit. 0 = no alert. |

The front end asks on every round; **the server decides**. Each option is
re-checked in `l10n_gr_prov_issue_note` / `l10n_gr_prov_cancel_order`, so a till
running a stale bundle cannot transmit what the admin switched off.

---

## What is transmitted

### The note (8.6)

- `tableAA` = the table number, one note per round;
- income classified exclusively as `category1_95` (Λοιπά Πληροφοριακά Στοιχεία
  Εσόδων) — never an E3 code;
- real VAT per rate (categories 1–7); 0% carries exemption 27;
- `paymentMethods` type 5 (Επί Πιστώσει) — a note is not paid, it is closed;
- no buyer, no extra taxes.

Failures are recorded on the note, never raised: the kitchen round must go out
even when the provider is unreachable. Retry from the back-office list.

### The closing document

The ΑΛΠ/ΤΙΜ is transmitted with the MARKs of every open note of that table in
`multipleConnectedMarks` and the mandatory «Συναλλαγές Εστίασης» flag
(`aadeSpecialInvoiceCategory` 12).

---

## Cancellation — both routes of the guide

Neither route has its own endpoint. Both are ordinary submissions through
`POST /api/invoice`; grepping for a cancel URL finds nothing.

### An item is removed from a round (§5.2)

A **new** note whose rows carry `recType: 7` («αρνητικό δελτίο»), amounts
**positive** — the opposite sign is expressed by the row type, not by the
numbers. Must be within 24 h of the original.

Prices come from the note that transmitted the item, matched by the POS
`preparationKey`, not from the client: the waiter may have deleted the order
line outright, and even when the client can supply amounts the credit has to
match the original cent for cent. A row never transmitted is dropped — there is
nothing to cancel.

### The whole table walks out (§5.4)

One zero-value note with `totalCancelDeliveryOrders: true` and every cancelled
MARK in `multipleConnectedMarks`, VAT category 8 and category code `Z`. It
closes them with no correlation at all. The cancelled notes move to
«Ακυρώθηκε» — but only once the cancellation itself came back `sent`.

The same action is on the back-office list (**Καθολική Ακύρωση**) for notes an
offline till left open.

---

## The alert cron

Hourly. For each till with `alert_hours > 0`, notes that are `sent`, unclosed
and older than the threshold get **one** activity — on whoever last opened a
session on that till, not on OdooBot, and not a fresh one every hour (the cron
checks for an existing activity first: one open reminder is a reminder, 24 are
noise nobody reads).

---

## Field reference

### `l10n.gr.prov.catering.order`

| Field | Type | Description |
|-------|------|-------------|
| `kind` | Selection | `order` / `negative` / `cancel` |
| `table_aa` | Char | Table number as transmitted (`tableAA`) |
| `pos_order_uuid` | Char | Link to the POS order — by uuid, because the order may not be synced server-side when the round is sent |
| `pos_order_id` | Many2one | Resolved when the table closes |
| `closing_move_id` | Many2one | The document of value that closed this note |
| `cancelled_note_ids` | Many2many | The notes this Καθολική Ακύρωση closes |
| `state` | Selection | draft / sent / closed / cancelled / error |
| `mark`, `verification_hash`, `qr_url`, `invoice_id_provider` | Char | Provider markings |
| `series` / `serial` | Char | ΔΠΕ + own sequence |

Inherits `mail.thread` and `mail.activity.mixin` — both, because
`mail.activity` subscribes the assignee on create, which needs `mail.thread`.

### `l10n.gr.prov.catering.order.line`

`name`, `prep_key` (the POS `preparationKey`, the handle a negative note prices
against), `quantity`, `net_value`, `vat_amount`, `vat_rate`.

### `pos.config`

`l10n_gr_prov_catering_notes`, `l10n_gr_prov_catering_auto_cancel`,
`l10n_gr_prov_catering_auto_negative`, `l10n_gr_prov_catering_alert_hours`.

---

## Tests

`tests/test_catering_cancel.py` — four cases (negative pricing off the original,
whole cancellation payload, config guards), provider stubbed.

---

## Changelog

### 1.2 — Per-till options
- Issue notes per round, auto Καθολική Ακύρωση on cancel, auto negative note on
  item removal, and an alert for notes approaching the 24 h limit — the one
  thing nobody notices until the provider suspends transmission. All on by
  default.

### 1.1 — Cancellation, both routes of §4
- Removing an already-sent item issues an «αρνητικό» note (`recType: 7`, priced
  from the note that transmitted it, so a deleted orderline is still credited).
- Cancelling the order issues a «Καθολική Ακύρωση 8.6».
- Same action on the back-office list for notes an offline till left open.

### 1.0 — Phase 1
- Issue 8.6 on send-to-kitchen; close the table with the ΑΛΠ carrying the
  connected marks.
