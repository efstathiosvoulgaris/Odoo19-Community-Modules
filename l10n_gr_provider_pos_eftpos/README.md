# l10n_gr_provider_pos_eftpos — Α.1155 in the Point of Sale

**Version:** 1.3 | **Odoo:** 19 | **License:** LGPL-3
**Spec refs:** Α.1155/2023 · ILYDA MegEftPos Driver v2.1.10

Brings the Α.1155 EFT/POS signature flow into the Point of Sale. Auto-installs
when both `l10n_gr_provider_pos` and `l10n_gr_provider_eftpos` are present.

The backend module is invoice-bound: an `l10n.gr.prov.eft.payment` needs an
`account.move`. In the POS the signature has to be taken *before* any document
exists, so here the signature rides directly on the payment line and is carried
onto the invoice's myDATA payment line at save time. The two never collide —
backend lines link through `eft_payment_id`, POS lines leave it empty.

---

## Dependencies

| Module | Purpose |
|--------|---------|
| `l10n_gr_provider_pos` | POS → provider issuing (ΑΛΠ/ΤΙΜ journals, myDATA payment types) |
| `l10n_gr_provider_eftpos` | Terminals, signature endpoints, MegEftPos driver client |

---

## Configuration

**Point of Sale → Configuration → Settings → Πάροχος myDATA (ΑΛΠ / ΤΙΜ / ΠΛΑ)**

| Setting | Description |
|---------|-------------|
| **Τερματικό Α.1155** | The card terminal this POS charges. Required — without it, card payments cannot be signed. |

Everything else (driver URL, licence, protocols, API keys) is configured on the
terminal and the company in `l10n_gr_provider_eftpos`.

Which payment methods trigger the flow follows the method's **effective myDATA
type** — the manual override if set, otherwise derived from the method's kind.
Only **type 7** qualifies: `bank` or `terminal` methods.

`qr_code` methods map to type 8 (IRIS direct) and are deliberately left alone.
There the customer pays the merchant's IRIS id from a banking app, no EFT/POS
is involved, and Α.1155 does not apply — no `terminalId`, nothing to sign.
IRIS paid *on* the terminal is not this: it arrives as an ordinary card line,
because it is one.

`paymentMethodId` is not sent to the driver. It is optional (the spec's own
preload example omits it), the cashier cannot know in advance whether the
customer will tap or scan, and preselecting one mode can hide the other on
NSPs that honour it.

---

## The payment flow

Runs inside `askBeforeValidation`, before the order is validated:

1. Every unsigned terminal line with a positive amount asks the server for a
   provider signature — one per line, since each is spent separately.
2. **Driver terminal:** the same call charges the card and returns the
   transaction id. **Standalone terminal:** the cashier charges the machine and
   types the id into a popup.
3. Signature, author, terminal code and transaction id are stashed on the
   payment line and travel to the invoice.

Signing and charging share one round trip on purpose. The signature exists only
to be spent on that charge, and one left issued but unused reaches AADE as an
«Ανοιχτό Παραστατικό» after 24 hours — so if the charge fails, the server
releases the signature before returning the error, and the cashier can never be
left holding a live one.

> The RPC blocks for the length of the card interaction (up to the driver
> client's 210 s timeout) with no progress indication. The previous manual flow
> blocked on a dialog for the same reason, so it feels similar — but if that
> reads badly on a real terminal, splitting sign and charge into two calls with
> a spinner is the fix.

---

## Giving the money back

A charge that is not followed by a validated order must be reversed. Three
paths are covered:

| Situation | Behaviour |
|-----------|-----------|
| A later card line fails after an earlier one was charged | The earlier charges are voided. |
| Validation abandoned after charging (customer dialog cancelled, etc.) | Everything signed in that attempt is unwound. |
| Cashier removes a signed payment line | Asks for confirmation; the line is removed **only if** the unwind succeeds. |

Unwinding means two different things. A **driver-charged** line is voided on the
terminal, which also releases its signature. A line the cashier charged on a
**standalone** terminal cannot be voided from Odoo — its signature is released
and the cashier is told, by name and amount, to reverse the money on the
terminal themselves. Either way the signature never survives the attempt: an
unused one reaches AADE as an «Ανοιχτό Παραστατικό» after 24 hours.

Void on the terminal happens first, then the provider signature is released —
it was never spent on a transmitted document.

**A failed void is never swallowed.** The cashier gets an alert naming each
amount and error, telling them to reverse it on the terminal by hand. (An
unused *signature* failing to cancel is logged quietly — the provider releases
it after 24 h. Money already taken is not in that category.)

An order abandoned *before* the transaction id is entered on a manual terminal
releases the signature and stops.

---

## Field reference

### `pos.payment`

Carried to the invoice's myDATA payment line on save.

| Field | Type | Description |
|-------|------|-------------|
| `l10n_gr_prov_eft_signature` | Text | Provider signature spent on this payment |
| `l10n_gr_prov_eft_signing_author` | Char | Provider identifier |
| `l10n_gr_prov_eft_transaction_id` | Char | From the terminal; `nspReferenceNumber` under a driver |
| `l10n_gr_prov_eft_terminal_code` | Char | Terminal that executed the payment |
| `l10n_gr_prov_eft_signed_content` | Char | Signed plain text; `providerInput` on a Void |
| `l10n_gr_prov_eft_signature_uid` | Char | uidHash; `providerUid` on a Void |
| `l10n_gr_prov_eft_signature_ts` | Integer | Signature epoch seconds |
| `l10n_gr_prov_eft_ecr_reference` | Char | Driver transaction handle |
| `l10n_gr_prov_eft_bank_auth_code` | Char | Required to Void this charge |
| `l10n_gr_prov_eft_receipt_number` | Char | Required to Void this charge |

The last six exist because a Void has to quote back the exact values the Sale
answered with — `bankAuthorizationCode` and `receiptNumber` are mandatory in
the driver's `VoidRequest`. They double as the bank reconciliation trail.

### `l10n.gr.prov.payment`

| Field | Type | Description |
|-------|------|-------------|
| `l10n_gr_prov_eft_signature` | Text | Signature for a POS card payment |
| `l10n_gr_prov_eft_signing_author` | Char | Provider identifier |
| `l10n_gr_prov_eft_terminal_code` | Char | Terminal code |

### `pos.config`

| Field | Type | Description |
|-------|------|-------------|
| `l10n_gr_prov_eft_terminal_id` | Many2one | Terminal used by this POS |

---

## Server methods (called from the POS client)

All on `l10n.gr.prov.eft.terminal`, all returning `{'error': …}` rather than
raising, so the payment screen can show a dialog.

| Method | Purpose |
|--------|---------|
| `l10n_gr_prov_pos_sign(vals)` | Issue the signature; also charge when the terminal is driver-driven. Returns `signature`, `signing_author`, `terminal_code`, and on the driver path `transaction_id` plus the Void references. |
| `l10n_gr_prov_pos_void(vals)` | Reverse a driver charge and release its signature. |
| `l10n_gr_prov_pos_cancel(vals)` | Release an unused signature. |

`vals` carries `config_id`, the line amount, the order's `net` / `vat` /
`gross` / `vat_rate`, and `is_timologio`.

---

## Payment line construction

`_l10n_gr_prov_pos_payment_vals` fully replaces the base implementation:

- A payment carrying a signature is emitted as **its own line** — each has a
  distinct signature and transaction id, so they cannot be grouped.
- It is always type 7: it went through the EFT/POS, whether the customer
  tapped a card or paid the terminal's IRIS QR.
- Everything else is grouped by type and summed, so cash change (a negative
  return line) nets out.

---

## Returns

An order whose `priceIncl` is negative is a credit document. §5.3 makes
`signature` and `transactionId` mandatory on **every** type-7 payment line, so
a refund to card is signed like a sale — against the credit series (ΠΛΠ 11.4,
or ΠΙΣΤ 5.1 when the original was a ΤΙΜ), with amounts sent positive as the
document itself carries them.

The refund is judged by the amount rather than `order.isRefund`, which Odoo
only sets for the Refund action: an order typed in with negative quantities is
just as much a credit document, and `_l10n_gr_prov_pos_journal()` treats it
that way too.

**The money is given back by the cashier on the terminal**, even on a
driver-connected one, and the transaction id is typed into the popup. A driver
`Refund` has to quote the original Sale's `ecrReferenceNumber`,
`nspReferenceNumber`, `bankAuthorizationCode` and `receiptNumber`; the payment
screen has no dependable handle on the refunded order's payment lines, which is
why the backend flow makes the user pick the «Αρχική Χρέωση» explicitly.
Α.1155 requires the signature, not the automation.

---

## Known gap

Nothing reverses a charge once the order has been **validated**. The recovery
path for a wrongly-charged validated order is a POS refund plus a manual Void
on the terminal, or the backend EFT payment screen.

---

## Changelog

### 1.4 — Returns are signed, no leaked signatures
- A signature taken for a **standalone** terminal was never released when the
  validation was abandoned or the line deleted: only driver-charged lines were
  tracked, so the signature expired into an «Ανοιχτό Παραστατικό». Every signed
  line is now unwound.
- A card refund used to be skipped entirely (`getAmount() > 0`), so the credit
  document was transmitted with an unsigned type-7 line. It now takes its own
  signature against the credit series, and the cashier refunds on the terminal
  and enters the transaction id.

### 1.3 — IRIS is type 7
- Corrected 1.1: IRIS at an EFT/POS transmits as myDATA type 7 like any card.
  `qr_code` methods (IRIS direct, type 8) are outside Α.1155 and no longer
  pulled into the signature flow.
- `paymentMethodId` is no longer sent, so the terminal offers the customer
  both card and IRIS.

### 1.2 — Void path
- A charge not followed by a validated order is given back: terminal voided and
  signature released on a later payment failing, on validation being abandoned,
  and on the cashier removing a charged line (which now asks first instead of
  dropping it silently).
- Six fields added to `pos.payment` to hold what a Void must quote back.

### 1.1 — Driver charging, IRIS
- Driver-connected terminals are charged by the software; the transaction id
  arrives automatically and the cashier prompt is skipped.
- IRIS handling (superseded by 1.3).
- Fixed: `vat_rate` was never sent, so VIVA signatures were built with rate 0.

### 1.0 — Initial release
- Signature request at the payment screen, manual transaction id entry,
  signature carried to the invoice's type-7 payment line, cancellation of an
  unused signature when the order is abandoned.
