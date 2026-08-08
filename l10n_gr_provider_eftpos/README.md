# l10n_gr_provider_eftpos — EFT/POS Interconnection (Α.1155)

**Version:** 1.9 | **Odoo:** 19 | **License:** LGPL-3
**Spec refs:** Α.1155/2023 · ILYDA «Οδηγίες υλοποίησης A1155 POS» v1.3 ·
ILYDA MegEftPos Driver v2.1.10 · «Οδηγός Διασύνδεσης ERP με POS»

Interconnects card terminals with the e-invoicing provider, as Α.1155/2023
requires. A card payment is not just recorded — it is *signed* by the provider
(Υ.ΠΑ.Η.Ε.Σ.), the signature is spent on the terminal, and the resulting
transaction id is transmitted with the document.

Terminals can be charged automatically through the **ILYDA MegEftPos Driver**,
a local Windows service that speaks every NSP protocol behind one REST API.
Without it the module still works: the cashier charges a standalone terminal
and types the transaction id back.

---

## Dependencies

| Module | Purpose |
|--------|---------|
| `l10n_gr_provider_base` | Dispatch protocol, myDATA payment lines |
| `l10n_gr_provider_ilyda` | The signature endpoints live on the ILYDA client |

---

## Configuration

### Provider side

Nothing beyond a working `l10n_gr_provider_ilyda` setup. The signature
endpoints (`/api/invoice/sign`, `/sendPaymentMethods`, `/sign/cancel`) reuse
its credentials and test/production switch.

### Driver side

**Settings → Accounting → Greek E-Invoicing Provider → MegEftPos Driver**

| Setting | Description |
|---------|-------------|
| **MegEftPos Driver URL** | Address of `MegEftPosRestServices`, e.g. `http://127.0.0.1:8187` (`rest.server.port` in its config). **Leave empty for manual terminals.** |
| **MegEftPos License Key** | Issued per merchant ΑΦΜ by ILYDA. |
| **ΑΦΜ Άδειας MegEftPos** | The ΑΦΜ the licence was issued for. On test keys ILYDA often binds one that is *not* the company's own. Empty = use the company ΑΦΜ. |
| **Driver Username / Password** | Only when the wrapper runs with `rest.authorization.method=BASIC_AUTH`. Empty = no authentication. |

### Terminals

**Accounting → myDATA → Ρυθμίσεις myDATA → Τερματικά EFT/POS**

| Field | Required for | Notes |
|-------|--------------|-------|
| **Terminal ID** | always | As registered with the NSP. |
| **Πρωτόκολλο NSP** | always | How the *provider* builds the signature (§7.7 NSPProtocol). `DEFAULT` = EDPS construction. |
| **Πρωτόκολλο Driver** | driver only | How the *driver* reaches the terminal. Empty = manual terminal. |
| **IP / Port** | `CARDLINK_DLL`, `EDPS_JSON`, `EDPS_COMMON_TCP_SOCKET`, `NEXI_COMMON_TCP_SOCKET` | The physical terminal on the LAN. |
| **API Key (WebECR)** | `MELLON_`, `EPAY_`, `NEXI_`, `NEXI_SOFT_POS_`, `ATTICA_`, `WORLDLINE_`, `EDPS_WEB_ECR` | Not typed in — enter the terminal's **OTP** and press *Λήψη API Key*. Redeemed once; the key is permanent. |
| **Client ID / Secret** | `VIVA_CLOUD` | From *POS APIs Credentials* in the Viva portal. |

NSP credentials (usernames, passwords, endpoints) live in the driver's own
`MegEftPos.config`, not in Odoo. See «Οδηγός Υλοποίησης MegEftPos Integration»
for the per-NSP keys and their test/production values.

> **Two protocol lists, deliberately.** `nsp_protocol` tells the provider how
> to *construct* the signature; `pos_protocol` tells the driver how to *reach*
> the terminal. They overlap in name but are different enums and are not
> derivable from one another.

---

## The two legal flows

### Real-time (§3) — document issued after payment

1. Request a signature from the provider using the document totals.
2. Charge the terminal, passing that signature through the NSP.
3. Submit the document; its type-7 payment line carries `signature`,
   `signingAuthor`, `terminalId`, `transactionId`.

### Retrograde (§4) — document already marked

1. Request a signature **by MARK**.
2. Charge the terminal (or preload — below).
3. `sendPaymentMethods` returns a `paymentMethodMark` per payment, stored on
   the record.

### Preload (§4) — customer pays later

For an already-issued document, *Προφόρτωση στο Τερματικό* pushes the pending
signature onto the terminal and stops. Nothing is charged. When the customer
eventually pays, *Ανάκτηση Εκκρεμούς* fetches the outcome and completes the
payment.

Only `ecr_reference` and `preloaded_at` are stored at preload time —
deliberately **not** the driver result fields, because an approved *preload*
means "signature loaded", not "card charged", and recording it as a charge
would let the cancel path fire a Void against a transaction that never
happened.

---

## Usage

**Accounting → myDATA → Πληρωμές EFT/POS**, or press *Send to Provider* on an invoice
that carries a type-7/8 payment line — the EFT dialog opens instead of
transmitting.

| Button | When | Does |
|--------|------|------|
| **OK — Έκδοση Υπογραφής** | draft | Requests the signature. With a driver terminal it charges immediately afterwards. |
| **Χρέωση Τερματικού** | signed, driver | Sale (or Refund on a credit note). |
| **Προφόρτωση στο Τερματικό** | signed, driver | Preload for later payment. |
| **Ανάκτηση Εκκρεμούς** | after a preload or a failed/interrupted charge | Asks the driver what became of the transaction. |
| **Ολοκλήρωση Αποστολής** | signed, manual terminal | Completes with the hand-typed transaction id. |
| **Ακύρωση Υπογραφής** | signed / paid | Voids the charge on the terminal if one was approved, then cancels the signature with an AADE reason code. |

### Credit notes

A credit note goes to `/refund`, not `/sale`, and must quote the original
charge. Set **Αρχική Χρέωση** — it is auto-filled from the reversed invoice's
approved payment when one exists.

### 8.4 / 8.5 receipts

**Accounting → myDATA → Είσπραξη με Κάρτα (8.4/8.5)** builds an 8.4 or 8.5 with the single type-7
payment line Α.1155 demands, posts it, and hands over to the EFT dialog.

---

## Interrupted transactions

A dropped connection leaves the charge in an unknown state. The module never
rolls back after calling the driver, because `ecrReferenceNumber` is the only
handle for recovering it. *Ανάκτηση Εκκρεμούς* queries the driver by
`ecrReferenceNumber`, then `nspReferenceNumber`, then falls back to listing all
pending transactions (refusing to guess when more than one is open).

---

## Rules enforced before the card is charged

Α.1155 §5.3 is checked locally, not left to the provider — by the time the
provider rejects a document the money is already taken.

| Rule | Behaviour |
|------|-----------|
| Signature must not be expired | Blocks charge and completion. |
| Payment ≤ signature amount | Blocks; `amount` stays writable server-side, so the view being readonly is not protection. |
| Signature must match the document (net / VAT / gross) | Blocks, naming the drifted fields — reachable when an invoice is reset to draft and edited after signing. |
| Terminal charged a different amount | `paidAmount` is adopted when lower (so the transmitted figure is one that happened) and the shortfall is posted on the move. A charge *above* the request raises, since it breaches the signature ceiling. |

`paidAmount` is treated as agreeing if it equals the requested amount **or**
that amount plus the tip — NSPs disagree on whether it is tip-inclusive, and
guessing one convention would create false mismatches.

---

## IRIS

**Μέσο Πληρωμής** preselects what the terminal offers: `BANK_CARD` or `IRIS`
(where the terminal shows a QR for the customer to pay). It does **not** change
the fiscal treatment.

> ⚠️ **UNRESOLVED — the code here does not match the AADE schema.** Asked of
> ILYDA on 2026-08-08 (question Α7); do not treat the current behaviour as
> correct.
>
> This module currently treats type 8 as outside Α.1155 and never signs it,
> on the reasoning that the ILYDA A1155 guide never mentions IRIS and §7.1
> mandates the signature fields only for "πληρωμή με POS (type == 7)".
>
> **That is an argument from silence, and the myDATA v2.0.1 XSD contradicts
> it.** `PaymentMethodDetailType` (types 1–8) carries an optional
> `ProvidersSignature`, and `ProviderSignatureType` contains
> `EndToEndReferenceID`, documented as «Το μοναδικό αναγνωριστικό αιτήματος
> πληρωμής (**για πληρωμές IRIS**)». `tid` is optional. So an IRIS payment
> does carry a provider signature, identified by an end-to-end reference
> instead of a terminal id — and ILYDA's own API model has the field.
>
> What remains genuinely open is whether IRIS executed **on the terminal**
> transmits as 7 or as 8, where `endToEndReferenceID` comes from, and how to
> obtain a signature for IRIS when the documented sign request requires
> `terminalId` + `nspProtocol`. We send `endToEndReferenceID` nowhere.

Preselection is advisory. The driver spec notes that where an NSP does not
support it the terminal shows every method and the customer chooses on the
spot, so whatever comes back in the response is adopted onto the record.
`NONE_PAYMENT_METHOD` means the NSP does not report it at all, and the
requested value is kept — as the driver spec instructs.

---

## Field reference

### `l10n.gr.prov.eft.terminal`

| Field | Type | Description |
|-------|------|-------------|
| `code` | Char | terminalId as registered with the NSP |
| `nsp_protocol` | Selection | Provider signature strategy (§7.7) |
| `pos_protocol` | Selection | Driver transport protocol; empty = manual |
| `host` / `port` | Char / Integer | LAN address for socket protocols |
| `api_key` | Char | WebECR key (system group); produced by OTP redemption |
| `client_id` / `client_secret` | Char | Viva Cloud credentials |
| `otp` | Char | Terminal's one-time code, consumed by *Λήψη API Key* |

### `l10n.gr.prov.eft.payment`

| Field | Type | Description |
|-------|------|-------------|
| `move_id` / `terminal_id` | Many2one | Document and terminal |
| `amount` / `tip_amount` | Monetary | Requested payment and tip |
| `payment_method` | Selection | `BANK_CARD` / `IRIS` preselected on the terminal; both transmit as type 7 |
| `state` | Selection | `draft` / `signed` / `paid` / `submitted` / `cancelled` |
| `signature` | Text | The provider signature spent on the terminal |
| `signing_author` | Char | Provider identifier (e.g. `008`) |
| `signature_uid` | Char | **uidHash** — sent as `providerUid` |
| `signed_content` | Char | The signed plain text; sent as `providerInput` |
| `signed_at` / `signature_expiry` | Datetime | Issue and expiry |
| `signature_expired` | Boolean (computed) | Blocks use |
| `signature_amount` | Monetary | Payment ceiling for this signature |
| `signature_net` / `_vat` / `_gross` | Monetary | Document totals the signature is bound to |
| `transaction_id` | Char | Transmitted to AADE; the `nspReferenceNumber` under a driver |
| `driver_response_code` | Selection | `APPROVED` / `DECLINED` / `BUSY` / … |
| `driver_message` | Char | NSP response code + description |
| `preloaded_at` | Datetime | Signature pushed to the terminal for later payment |
| `paid_amount` / `original_amount` | Monetary | What the terminal reports it charged |
| `ecr_reference` | Char | Driver's transaction handle — used for recovery |
| `nsp_reference` | Char | NSP transaction code |
| `bank_auth_code` / `receipt_number` | Char | Required to Void or Refund this charge |
| `card_type` / `card_number` | Char | Masked card details |
| `origin_payment_id` | Many2one | The charge a refund reverses |
| `payment_method_mark` | Char | AADE mark for a retrograde payment |
| `cancel_reason` / `cancel_reason_text` | Selection / Char | AADE cancellation reasons |

### `res.company`

| Field | Type | Description |
|-------|------|-------------|
| `l10n_gr_prov_eft_driver_url` | Char | REST wrapper base URL; empty = manual mode |
| `l10n_gr_prov_eft_license_key` | Char | Driver licence (system group) |
| `l10n_gr_prov_eft_vat` | Char | ΑΦΜ the licence is bound to |
| `l10n_gr_prov_eft_driver_user` / `_password` | Char | Optional Basic Auth |

---

## Driver wire format — corrections

The **v2.1.5 PDF is OCR-damaged in two field names**. The Postman collection
shipped with 2.1.10 and the v2.1.10 PDF are authoritative:

| PDF v2.1.5 says | Actually | Consequence of the typo |
|-----------------|----------|-------------------------|
| `tpAmount` | **`tipAmount`** | Tips silently dropped both ways |
| `bankAuthorizatonCode` | **`bankAuthorizationCode`** | Refund and Void rejected |

Two more traps, neither stated in prose:

- **`providerUid` is the `uidHash`, not the `uid`.** In every driver example
  `providerUid` equals the first segment of `providerInput` — the 40-char
  SHA-1. Sending the long `ΑΦΜ-date-…-GUID` uid fails validation.
- **`signatureTimestamp` is epoch seconds, UTC.** Odoo stores naive UTC
  datetimes and `datetime.timestamp()` reads a naive value as *local* time, so
  it must be stamped as UTC explicitly or Greek servers are 2–3 hours off.

The response side still accepts the misspelled `bankAuthorizatonCode` and
`nspResponseCodeDescripton`, in case a build emits them.

---

## Open questions for ILYDA

- **IRIS: type 7 or 8, and does it need an Α.1155 signature?** The XSD says a
  signature is carried (`EndToEndReferenceID` «για πληρωμές IRIS»); this module
  signs neither. See [IRIS](#iris) — this is the one open question that affects
  daily operation, since a business taking IRIS at the terminal is transmitting
  unsigned payments today.
- Does the provider's sign endpoint accept `nspProtocol` values `WORLDLINE`
  and `ATTICA`? The driver config supports both NSPs (`wl.mreceipts.com`,
  `gbl.mreceipts.com`), but the A1155 §7.7 enum lists only DEFAULT, NEOSOFT,
  MELLON, EPAY, NEXI, CARDLINK, VIVA. (`ATTICA` is confirmed working in
  practice — it returned a signature with `errors: null`.)

Full text of both, with the evidence, in
`paroxos_documentation/erotiseis_ILYDA_2026-08-08.txt`.

---

## Changelog

### 1.9 — A constraint that never existed
- Odoo 19 stopped reading `_sql_constraints`, so the CHECK keeping an EFT
  payment amount positive was never created in the database. Ported to
  `models.Constraint`.

### 1.8 — Instalments, Viva free refund
- `installments` on the payment, sent only when greater than 1 (optional in
  Sale/Refund/Preload, and NSPs without δόσεις reject a value).
- Viva Cloud «Ελεύθερο Refund» (driver V02.01.08): on a `VIVA_CLOUD` terminal a
  credit note may be refunded without an «Αρχική Χρέωση». Every other NSP still
  needs the original transaction's references.

### 1.6 — IRIS is type 7
- Corrected 1.4: IRIS at an EFT/POS is a settlement mode within the terminal
  transaction, not a separate rail, so it transmits as myDATA type 7 like any
  card. Type 8 is IRIS *direct*, which never touches a terminal and is outside
  Α.1155. `payment_method` remains, as a terminal preselection only.

### 1.5 — Signature invariants, honest amounts
- The signature records what it was issued for (`signature_amount`, plus net /
  VAT / gross), and a payment exceeding it — or whose document changed after
  signing — is refused (§5.3).
- `paidAmount` and `originalAmount` recorded. A lower charge is adopted so the
  amount transmitted to AADE is the one actually taken; a higher one raises.

### 1.4 — IRIS, expired signatures
- `payment_method` (`BANK_CARD` / `IRIS`) sent as `paymentMethodId`, honouring
  what the terminal reports back. ~~IRIS transmits as myDATA type 8~~ —
  **wrong, superseded by 1.6.**
- An expired signature can no longer be charged or transmitted (§5.3).

### 1.3 — Driver 2.1.10
- Corrected `tipAmount` and `bankAuthorizationCode` request field names —
  the v2.1.5 PDF misspells both, breaking tips and all Refund/Void calls.
- `providerUid` now carries the `uidHash`; `signatureTimestamp` computed as UTC.
- `NEXI_SOFT_POS_WEB_ECR` protocol; optional Basic Auth for the REST wrapper.

### 1.2 — MegEftPos Driver
- Automatic Sale, Refund on credit notes, Void when a charged payment is
  cancelled, and recovery of interrupted transactions.

### 1.0 — Initial release
- Terminal registry, EFT payments menu, payment window on the invoice,
  real-time and retrograde flows, signature cancellation.
