# l10n_gr_provider_ilyda — ILYDA Driver

**Version:** 2.4 | **Odoo:** 19 | **License:** LGPL-3  
**API ref:** ILYDA "Οδηγίες υλοποίησης eInvoicing" v1.0.6

Driver implementing the ILYDA Y.PA.H.E.S. eInvoicing API for the
`l10n_gr_provider_base` dispatch protocol.

---

## Dependencies

| Module | Purpose |
|--------|---------|
| `l10n_gr_provider_base` | Dispatch protocol, fields, cron, PDF markings |

---

## Configuration

Go to **Settings → Accounting → Greek E-Invoicing Provider**.

1. Set **Provider** to `ILYDA (vs.gr)`.
2. The **ILYDA Credentials** section appears:

| Field | Description |
|-------|-------------|
| **ILYDA X-Auth-Key** | API key issued by ILYDA support. Required. |
| **ILYDA Username** | Optional; only if ILYDA agreed username/password as auth method. |
| **ILYDA Password** | Optional; paired with username above. |

3. Keep **Test Environment** enabled until you have confirmed end-to-end
   issuance with ILYDA support.

Credentials are stored encrypted (`groups='base.group_system'`).

---

## Endpoints used

| Operation | Method | Path |
|-----------|--------|------|
| Submit invoice | `POST` | `/api/invoice` |
| Upload PDF | `POST` | `/api/invoice/upload/{invoiceId}` |
| Poll B2G status | `GET` | `/api/invoice/status/{invoiceId}` |

Base URLs:

| Environment | Base URL |
|-------------|----------|
| Production | `https://vs.gr` |
| Test | `https://test.vs.gr` |

---

## Payload mapping

### Top-level

| ILYDA field | Source |
|-------------|--------|
| `b2g` | `l10n_gr_prov_b2g` |
| `selfPricing` | Always `false` (Odoo does not generate self-billing invoices) |
| `vatPaidByBuyer` | Always `false` (reverse-charge not yet supported) |
| `invoiceTypeCode` | `380` (invoice) / `381` (credit note) |
| `seriesNumber` | Parts of `name` before the last `/`, joined with `_` (e.g. `INV_2026`) |
| `serialNumber` | Part of `name` after the last `/` (e.g. `00042`) |
| `invoiceIssueDate` | `invoice_date` as `YYYY-MM-DDT00:00:00` |
| `invoiceCurrencyCode` | `currency_id.name` (default `EUR`) |
| `paymentMethods[0].type` | `l10n_gr_edi_payment_method` (1–7; default 5 = on credit) |
| `paymentMethods[0].amount` | Total gross |
| `docLevelAllowances` | `null` (doc-level allowances not yet supported) |
| `docLevelCharges` | `null` (doc-level charges not yet supported) |

### Seller

| ILYDA field | Source |
|-------------|--------|
| `sellerVatIdentifier` | `company_id.vat` — EL-prefixed |
| `sellerName` | `company_id.name` |
| `branch` | `company_id.partner_id.l10n_gr_edi_branch_number` (default 0) |
| `sellerContact.sellerContactEmail` | `company_id.email` |
| `sellerContact.sellerContactPhoneNumber` | `company_id.phone` |
| `sellerPostalAddress.*` | `company_id.partner_id` address fields |

### Buyer (B2B/B2G only; omitted for retail/B2C)

Populated only when `commercial_partner_id.vat` is set.

| ILYDA field | Source |
|-------------|--------|
| `buyerVatIdentifier` | `commercial_partner_id.vat` — EL-prefixed |
| `buyerName` | `commercial_partner_id.name` |
| `buyerTradingName` | `commercial_partner_id.name` |
| `buyerBranch` | `commercial_partner_id.l10n_gr_edi_branch_number` (default 0) |
| `buyerContact.buyerContactEmail` | `commercial_partner_id.email` |
| `buyerPostalAddress.*` | `commercial_partner_id` address fields |

### Per-line fields

| ILYDA field | Source |
|-------------|--------|
| `lineNumber` | 1-based sequence |
| `note` | `""` (always empty; line notes not sent) |
| `invoicedQuantity` | `invoice_line_ids.quantity` |
| `invoicedQuantityUnits` | `"EA"` (default; UoM mapping not yet implemented) |
| `netAmount` | `price_subtotal` (rounded to 2 dp) |
| `discountPercentage1` | `invoice_line_ids.discount` |
| `discountPercentage2/3` | `0.0` |
| `discountAmount` | `price_unit × quantity × discount / 100` |
| `discountTotalAmount` | Same as `discountAmount` |
| `itemInfo.itemInfoName` | `product_id.name` (max 200 chars) |
| `itemInfo.itemInfoDescription` | `invoice_line_ids.name` (max 200 chars) |
| `priceDetails.itemNetPrice` | `price_unit × (1 − discount/100)` |
| `lineVatInfo.vatRate` | Tax rate (%) |
| `lineVatInfo.vatCategoryCode` | `S` if rate > 0, `E` otherwise |
| `lineVatInfo.aadeVatData.aadeVatCategory` | Derived (see VAT category rules) |
| `lineVatInfo.aadeVatData.aadeVatExemptionCategory` | `l10n_gr_edi_tax_exemption_category` (only when category = 7) |
| `incomeClassification[0].classificationCategory` | `l10n_gr_edi_cls_category` |
| `incomeClassification[0].classificationType` | `l10n_gr_edi_cls_type` |
| `itemClassificationIdentifiers[0]` | CPV code from `product_id.l10n_gr_prov_cpv` (B2G only) |

### VAT category derivation rules

Mirrors the logic in `l10n_gr_edi`:

| Condition | `aadeVatCategory` |
|-----------|-------------------|
| No tax on line, or invoice type in `TYPES_WITH_VAT_CATEGORY_8` | 8 |
| Invoice type in `TYPES_WITH_VAT_EXEMPT` (3.1, 3.2) | 8 |
| Tax rate 24% | 1 |
| Tax rate 13% | 2 |
| Tax rate 6% | 3 |
| Tax rate 17% | 4 |
| Tax rate 9% | 5 |
| Tax rate 4% | 6 |
| Tax rate 0% | 7 |

For category 7, `aadeVatExemptionCategory` must be set on the line (myDATA tab).

### VAT breakdowns

One entry per unique `(rate, aadeVatCategory, exemption)` tuple across all lines.
`exemptionReasonCode` is populated from the exemption category when present (category 7).

### AADE data block

| ILYDA field | Source |
|-------------|--------|
| `aadeInvoiceTypeCode` | `l10n_gr_edi_inv_type` |
| `incomeClassifications` | Aggregated per `(category, type)` pair |
| `invoiceRowTypes` | One entry per line with net, VAT, category, and per-line classifications |

---

## B2G extra fields

Added to the payload when `l10n_gr_prov_b2g = True`:

| ILYDA field | Source |
|-------------|--------|
| `contractReference` | `l10n_gr_prov_contract_ref` (ΑΔΑΜ) |
| `projectReference` | `"<budget_type>\|<budget_ref>"` (BT-11) |
| `buyerReference` | `l10n_gr_prov_buyer_ref` (BT-10) |
| `purchaseOrderReference` | `l10n_gr_prov_purchase_order_ref` (BT-13) |
| `sellerIdentifiers[0].sellerIdentifier` | Company VAT EL-prefixed (BT-29) |
| `buyerIdentifiers[0].buyerIdentifier` | `partner.l10n_gr_prov_aaht` (ΑΑΗΤ code) |
| `buyer.buyerName` | `commercial_partner_id.name` |
| `buyer.buyerTradingName` | `commercial_partner_id.name` |
| `buyer.buyerBranch` | `commercial_partner_id.l10n_gr_edi_branch_number` (default 0) |
| `buyer.buyerElectronicAddress.buyerElectronicAddress` | Bare 9-digit VAT (no EL prefix) |
| `buyer.buyerElectronicAddress.buyerElectronicAddressSchemeIdentifier` | `"9933"` |
| `delivery.partyName` | Shipping address name (or buyer name) |
| `delivery.deliveryAddress.*` | `partner_shipping_id` or `commercial_partner_id` address |
| Per-line `itemClassificationIdentifiers` | CPV from `product_id.l10n_gr_prov_cpv`, scheme `STI` |

---

## Credit note preceding reference

When `move_type == 'out_refund'` and the reversed invoice has a MARK, the payload
includes:

```json
"precedingInvoices": [{
  "precedingInvoiceReference": "<sellerVAT9digit>|<dd/mm/yyyy>|<branch>|<aadeType>|<series>|<serial>",
  "precedingInvoiceIssueDate": "<YYYY-MM-DD>T00:00:00"
}]
```

The first field is the **bare 9-digit seller VAT number** (no EL prefix), not the MARK.
This matches the format confirmed in the ILYDA JSON examples (e.g. `"177472438|02/12/2024|0|1.1|Α|1333335"`).

The reversed invoice must be submitted (MARK present) before the credit note
can be sent — the validation step enforces this.

---

## Response handling

A successful response contains `invoiceMarking`:

```json
{
  "invoiceMarking": {
    "mark": "...",
    "invoiceId": "...",
    "verificationHash": "...",
    "invoiceIdentifier": "...",
    "qrCode": "https://...",
    "providerUrl": "https://...",
    "previouslySubmitted": false
  }
}
```

These values are written to the corresponding `l10n_gr_prov_*` fields on the
invoice. `aadePreviouslySubmittedError228 = true` means AADE had already seen
this document (error 228 recovery); the marking is still valid and
`l10n_gr_prov_previously_submitted` is flagged for audit visibility.

Fatal errors in the `errors` array raise a `UserError`; non-fatal warnings are
posted as chatter messages.

---

## Validation checklist

Before submission the driver checks:

- Company VAT number is set.
- `l10n_gr_edi_inv_type` is set (myDATA invoice type).
- At least one product line exists.
- Every line has myDATA income classification (category + type).
- Every line has a valid Greek VAT rate (24/13/6/17/9/4/0); if 0% and not
  an exempt type, the Tax Exemption Category must be set.
- For credit notes: the reversed invoice must have a MARK.
- For B2G: contract reference (ΑΔΑΜ), budget identifier, buyer reference,
  customer VAT number, and CPV on every product line must be present.
- Company address (city and ZIP) must be complete.

---

## Tests

`tests/test_ilyda_response.py` — how the driver reads what ILYDA sends back,
which is where a misread means either a duplicate at AADE or a lost MARK:
error-code classification and the lookup contract, the submit-response matrix
(marked, I0008 re-mark, MQ00x queue beating the fatal flag, rejections), the
VAT/VAT-number helpers, and the A.1035-B2 UID over Greek series. The API
client is never constructed.

---

## Changelog

### 2.4 — ΠΟΣΕ refunds
- A refund on the ΠΟΣΕ journal transmits as **8.5**, instead of being turned
  into a 5.x credit note.

### 2.3 — Real units, 9.2, invoiceDetailType
- `measurementUnit` is the line's actual unit (§8.13) rather than a hardcoded
  1; an unmapped unit goes as 7 carrying its name and count.
- 9.2 transmits the generic counterpart ΑΦΜ `000000000` and no longer demands a
  VAT on the partner.
- `invoiceDetailType` per line, with a 1.5 blocked before sending unless both
  line kinds are present.

### 2.2 — Retail refunds
- Refunds on the ΠΛΑ journal submit as 11.4.

### 2.1 — 8.2 Ειδικό Στοιχείο Τέλους Διαμονής
- Payload shape for the accommodation fee document.

### 2.0 — TF-1 offline QR
- `/api/offline-qr` key lifecycle: issue, verify installation, revoke.
- A connection failure on submit raises a typed *unreachable* error, which is
  what triggers the base module's offline fallback — anything else would have
  been recorded as a rejection.
- The offline JWS payload is built from the same sources as the submit payload.
- A recovered document with no provider `invoiceId` gets a chatter note saying
  its PDF must be uploaded by hand.

### 1.9 — Search & reconciliation, TF-2
- UID lookups (`by-uid`, `by-mark`, `by-authentication-code`) and the TF-2
  pending queue (`pending`, `by-uid`).
- Recovery **adopts** a MARK issued during a lost-response submission instead of
  resending it — the duplicate guard.
- TF-2 responses (MQ001/MQ002 + I9999/I0004) store the identifier and QR and
  mark the document queued rather than rejected; I0008 re-issues adopt the
  original marking.
- Local myDATA UID computation (SHA-1 / ISO-8859-7), self-checked against the
  identifiers the provider returns.

### 1.8 — Combined invoice + delivery note (ΤΔΑ/ΠΤΔΑ)
- Documents on «Τιμολόγιο – Δελτίο Αποστολής» journals send
  `isDeliveryNote: true` with aadeMovePurpose, otherDeliveryNoteHeader
  (loading/delivery addresses, shipping branches) and per-row
  itemDescr/quantity/measurementUnit (MDP-0028).
- Planned dispatch data: `aadeDispatchDate`/`aadeDispatchTime`
  (Europe/Athens) and `aadeVehicleNumber` — `otherTransportDetails` is
  rejected by myDATA v2.0.x (MPD-0100).
- `otherMovePurposeTitle` for σκοπός διακίνησης 19; numeric validation for
  shipping branches.
- Multiple `paymentMethods` from the payment lines table (AADE type sent
  directly per ILYDA ET-63, with tipAmount/transactionId); validation that
  the amounts sum to the payable; legacy single-method fallback when the
  table is empty.

### 1.7 — Withholding totals, error clarity
- **Withholding (BR-CO-16 / MDP-0081 / BG-22 fixes)**: withheld tax is now an
  EN16931 doc-level allowance (BT-107) at Z/0%%, so BT-109/BT-112 and the
  myDATA gross (ET-25) agree; extra vatBreakdowns entry with negative taxable,
  as in ILYDA's own reference example.
- Doc-level charges (Ψηφιακό Τέλος/Τέλη/Λοιποί Φόροι) included in BT-109/112.
- paymentMethods amount = myDATA gross (net + VAT + charges − withheld).
- Error messages now include AADE's `aadeMessage` (no more blank "204:").
- Pre-send guard for non-sendable Σκοπός Διακίνησης codes (6/15/16/17).
- Dispatch payloads: buyer block included; payment method skipped for all
  dispatch types (9.x/10.x).

### 1.6 — myDATA v2.0.1
- Aligned with the v2.0.1 data refresh in `l10n_gr_provider_base` (new types,
  categories, E3 codes).
- **Series sent as Greek**: the AADE `series` field (xs:string, max 50) is now
  transmitted verbatim from the journal code (ΤΙΜ, ΔΑ, ΑΛΠ) instead of being
  transliterated to Latin. `_ascii_safe` kept as a fallback.
- **Provider-submittable guard**: only invoice types 1.1–11.5 may be submitted
  through the provider (per provider spec); other types raise a clear error.
- Dispatch types (9.x/10.x) skip the line E3 requirement (category3-only).
- Foreign buyer VAT numbers are no longer prefixed with `EL` (only GR VATs are
  normalised).

### 1.2
- Added `selfPricing: false` and `vatPaidByBuyer: false` (mandatory ET-1/ET-2
  fields; previously missing, could cause API rejection).
- Buyer block now includes `buyerName`, `buyerTradingName`, and `buyerBranch`
  (were missing in B2B; all three required by ILYDA examples).
- Per-line: added `note`, `invoicedQuantityUnits` (default `"EA"`), and all
  discount fields (`discountPercentage1/2/3`, `discountAmount`,
  `discountTotalAmount`).
- Classification `amount` changed from formatted string to float.
- `docTotal` now includes `paidAmount`, `roundingAmount`,
  `documentLevelAllowancesSum`, `documentLevelChargesSum`, `exchangeRate`
  (non-zero for foreign currency), and `invoiceTotalVatAmountInAccountingCurrency`.
- `docLevelAllowances: null` and `docLevelCharges: null` added to base payload.
- B2G: added `sellerIdentifiers` (BT-29), `buyerIdentifiers` from partner ΑΑΗΤ,
  corrected `buyerElectronicAddress` value to bare VAT without `9933:` prefix.
- Credit note `precedingInvoiceReference`: first field is now bare seller VAT
  (9 digits, no EL prefix), not the MARK — matches confirmed example format.
- Response handler: reads `aadePreviouslySubmittedError228` (correct field name;
  was reading nonexistent `previouslySubmitted`).

### 1.1
- VAT category derivation extracted to `_aade_vat_category()` helper; logic
  matches `l10n_gr_edi` exactly.
- `vatBreakdowns[*].exemptionReasonCode` now populated from the exemption
  category (was hardcoded `null`).
- Series/serial follow the `l10n_gr_edi` myDATA convention (`INV/2026/00042`
  → series `INV_2026`, serial `00042`), also in credit-note preceding
  references.
- B2G payload: `projectReference` from budget type + identifier; Peppol
  routing address (scheme 9933); delivery details from shipping address;
  CPV per line (BT-158, scheme STI) with validation.
- Amounts sent positive for both invoices and credit notes (removed the
  unused `sign` variable).

### 1.0
Initial release: B2B/B2C/B2G submit, marking ingestion (MARK, verification
hash, identifier, QR), PDF upload, B2G status polling, credit-note preceding
invoice reference.
