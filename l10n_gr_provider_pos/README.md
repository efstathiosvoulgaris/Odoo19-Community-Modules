# l10n_gr_provider_pos — the Point of Sale through the provider

**Version:** 1.7 | **Odoo:** 19 | **License:** LGPL-3
**Spec refs:** myDATA v2.0.1 (§8.12 payment types) · Α.1138/2020 · Α.1112/2025

Every validated POS order becomes a posted invoice on the proper Greek journal
and is transmitted to the licensed e-invoicing provider (Υ.ΠΑ.Η.Ε.Σ.) while the
customer is still at the counter. There is no separate POS pipeline: the order's
`account.move` rides the same workflow as any back-office invoice — send, TF-2
queue, TF-1 offline QR, retry cron.

---

## Dependencies

| Module | Purpose |
|--------|---------|
| `point_of_sale` | The till |
| `l10n_gr_provider_base` | Provider fields, retry queue, Greek print forms |
| `l10n_gr_provider_ilyda` | The provider API driver |

---

## Configuration

**Point of Sale → Configuration → Settings → Πάροχος myDATA (ΑΛΠ / ΤΙΜ / ΠΛΑ)**

| Setting | Default | Description |
|---------|---------|-------------|
| **Ημερολόγιο ΑΛΠ (11.x)** | — | Every order is issued here. **Leave it empty and the till behaves exactly like stock Odoo** — this one field is the master switch. |
| **Ημερολόγιο ΤΙΜ (1.1)** | — | Used when the cashier presses «Τιμολόγιο». |
| **Ημερολόγιο ΠΛΠ (11.4)** | — | Retail refunds. Falls back to any 11.4 journal of the company. |
| **Πελάτης Λιανικής** | — | The partner used on an ΑΛΠ with nobody selected. Create one contact and pick it here. |
| **Τι Εκτυπώνει το Ταμείο** | Νόμιμο παραστατικό | `legal` / `receipt` / `both` — see [Printing](#printing). |
| **Έκδοση Τιμολογίου (ΤΙΜ)** | on | Shows the «Τιμολόγιο» button on the payment screen. Refuses to save without a ΤΙΜ journal. |
| **Αποτυχία Διαβίβασης** | Συνέχεια | `ignore` / `warn` / `block` — see [When the send fails](#when-the-send-fails). |

`l10n_gr_prov_enabled` is a computed Boolean (ΑΛΠ journal set **and** the
company has an active provider). The front end reads it rather than the
journals, because `account.journal` is not among the models the POS loads.

### Payment methods

**Ρυθμίσεις → Τακτοποίηση Καταλόγου Φόρων** also seeds the Greek POS payment
methods Odoo does not ship — IRIS (8), Web Banking (6), Επιταγή (4), τραπεζικές
μεταφορές (1/2) — plus «Κάρτα-POS» (7), each stamped with its AADE §8.12 code.
They are created unattached; tick the ones you want per till.

> Odoo creates its own «Card» method only while the company has **no**
> bank-journal payment method at all. Seeding the Greek ones first suppressed it
> permanently, leaving tills with no type-7 method and the Α.1155 signature flow
> with nothing to act on — hence the explicit card seed (1.4).

The myDATA type of a method is derived live from its kind (cash → 3, card → 7,
QR → 8, pay-later → 5). `Τύπος Πληρωμής myDATA` on the method form overrides it;
leave it blank unless you mean to.

---

## Which document is issued

| Situation | Journal | myDATA |
|-----------|---------|--------|
| Ordinary sale | ΑΛΠ | 11.1 (or 11.2/11.3/11.5, per the journal) |
| Cashier pressed «Τιμολόγιο» | ΤΙΜ | 1.1 |
| Refund of a retail sale | ΠΛΠ | 11.4 |
| Refund of a ΤΙΜ | ΠΙΣΤ | 5.1 |

A refund is judged by `amount_total < 0`, not by Odoo's Refund action — an order
typed with negative quantities is just as much a credit document. Credit
documents never fall back to the sale journal's R-sequence.

A **ΤΙΜ names a real buyer**: with no partner, or a partner without ΑΦΜ, the
order is refused with a Greek error instead of silently being issued to
«Πελάτης Λιανικής». An ΑΛΠ with nobody selected gets the walk-in partner, and
the partner is written on the **order**, not only on the invoice — Odoo takes
the receivable account from `payment.partner_id`, so an anonymous order produces
a payment line with no account at all.

Line classification is derived at create (`_get_invoice_lines_values`) because
POS invoice lines never pass through the form onchange that would normally set
it. myDATA payment lines are built in `_prepare_invoice_vals`, before posting —
core's `_generate_pos_order_invoice` posts *and* transmits inside itself, so
setting them afterwards reached the provider too late.

---

## Printing

The till prints the **legal document**: the posted `account.move` rendered on
the journal's Greek form (ΑΛΠ 80mm, ΤΙΜ A4) with ΜΑΡΚ, provider QR and the
authentication code. The customer and an auditor get the same paper the back
office would hand out, from a single source of truth.

| Mode | What prints |
|------|-------------|
| `legal` (default) | `/report/pdf/account.report_invoice/<id>` in a hidden iframe → print dialog |
| `receipt` | Odoo's thermal ticket, carrying the ΜΑΡΚ/QR block |
| `both` | The document, then the ticket |

The thermal receipt always survives as the **offline fallback**: with no
`account.move` there is nothing to render, and the ticket prints the TF-1/TF-2
notice instead. The restaurant «Λογαριασμός» (an unfinalised order) prints
«ΔΕΝ ΑΠΟΤΕΛΕΙ ΦΟΡΟΛΟΓΙΚΟ ΣΤΟΙΧΕΙΟ» in words.

> The markings block is gated on the **till**, not on the document state. A send
> that failed at validation leaves the state empty, which used to hide the whole
> block — including its own «ΔΕΝ ΔΙΑΒΙΒΑΣΤΗΚΕ» fallback — handing the customer a
> plain receipt indistinguishable from a legal one (fixed in 1.5).

> `ponytail:` printing goes through the browser, which is what this deployment
> uses. An ePOS/IoT thermal printer configured in Odoo would **not** receive it —
> that path rasterizes an OWL component, so it would need the report rendered as
> HTML into the printer container instead.

---

## When the send fails

| Mode | Behaviour |
|------|-----------|
| `ignore` (default) | The document stays in the retry queue, the receipt says «ΔΕΝ ΔΙΑΒΙΒΑΣΤΗΚΕ», service never stops. |
| `warn` | Same, and the cashier sees it on the receipt screen. |
| `block` | `UserError` — the sale does not complete. |

> `ponytail:` `block` re-raises inside the sync, which rolls the whole thing
> back: the order returns to the till unsaved and the cashier retries. That is
> the point for a shop that may not hand over an untransmitted document, and the
> wrong choice for a busy restaurant. A softer «hold the order» would need its
> own state machine on `pos.order`.

---

## Field reference

### `pos.order`

| Field | Type | Description |
|-------|------|-------------|
| `l10n_gr_prov_timologio` | Boolean | The cashier's explicit ΤΙΜ request (`to_invoice` is forced on for every provider order, so it cannot carry that meaning) |
| `l10n_gr_prov_doc_name` | related | Document number |
| `l10n_gr_prov_inv_type` | related | myDATA document type |
| `l10n_gr_prov_mark` | related | ΜΑΡΚ |
| `l10n_gr_prov_verification_hash` | related | Συμβ. Αυθεντικοποίησης |
| `l10n_gr_prov_qr_url` | related | Provider QR |
| `l10n_gr_prov_state` | related | Transmission state |

The last six are surfaced on `pos.order` purely so the receipt can read them
after sync.

### `pos.config`

`l10n_gr_prov_alp_journal_id`, `l10n_gr_prov_tim_journal_id`,
`l10n_gr_prov_pla_journal_id`, `l10n_gr_prov_walkin_partner_id`,
`l10n_gr_prov_enabled` (computed), `l10n_gr_prov_print_mode`,
`l10n_gr_prov_allow_tim`, `l10n_gr_prov_send_failure`.

### `pos.payment.method`

`l10n_gr_prov_payment_type` — optional §8.12 override.

---

## Tests

`tests/test_send_failure.py` covers the three failure modes with the provider
stubbed to raise.

---

## Changelog

### 1.7 — Per-till options
- What the till prints (legal document / receipt with ΜΑΡΚ / both), whether the
  «Τιμολόγιο» button is offered, and what a failed transmission costs — all in
  POS settings, every default reproducing the previous behaviour.
- A ΤΙΜ now demands a partner with ΑΦΜ instead of silently falling back to the
  walk-in customer.
- The «Τιμολόγιο» button is hidden by a `t-if`, not removed, so the option can
  bring it back.

### 1.6 — The till prints the legal document
- The posted `account.move` on the journal's Greek form replaces the Odoo
  thermal receipt, which survives only where there is no document to print.
- The restaurant «Λογαριασμός» prints «ΔΕΝ ΑΠΟΤΕΛΕΙ ΦΟΡΟΛΟΓΙΚΟ ΣΤΟΙΧΕΙΟ».

### 1.5 — The markings block is gated on the till
- A failed send left `l10n_gr_prov_state` empty, hiding the whole block and its
  own «ΔΕΝ ΔΙΑΒΙΒΑΣΤΗΚΕ» fallback with it.

### 1.4 — «Κάρτα-POS» seeded
- Seeding the Greek payment methods first suppressed Odoo's own card method
  permanently, leaving tills with no type-7 method and the Α.1155 flow with
  nothing to act on.

### 1.0 — Initial release
- ΑΛΠ/ΤΙΜ/ΠΛΠ issuance, synchronous send, receipt markings, §8.12 payment type
  mapping.
