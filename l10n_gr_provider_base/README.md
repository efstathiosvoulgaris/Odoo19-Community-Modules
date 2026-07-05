# l10n_gr_provider_base — Greece E-Invoicing Provider Base

**Version:** 1.8 | **Odoo:** 19 | **License:** LGPL-3

Provider-agnostic base for issuing sales documents through a licensed Greek
e-invoicing provider (Υ.ΠΑ.Η.Ε.Σ.), as required by the 2026 B2B e-invoicing
mandate. A driver module (e.g. `l10n_gr_provider_ilyda`) implements the
actual API calls.

---

## Dependencies

| Module | Purpose |
|--------|---------|
| `account` | Core invoicing |
| `l10n_gr_edi` | myDATA field definitions (invoice type, income classifications, payment method, VAT exemption category, branch number) |

---

## What it does

1. **Adds fields** to `account.move`, `res.partner`, and `product.template`
   (see [Field reference](#field-reference)).
2. **Queues** posted sales invoices with `l10n_gr_prov_state = 'to_send'`.
3. **Suppresses** the `l10n_gr_edi` ERP-channel transmission for documents
   that will be sent through a provider — one channel per document.
4. **Sends** queued documents via a manual button, the Send & Print flow, or
   a scheduled cron job.
5. **Stores** the legal markings returned by the provider (MARK, verification
   hash, invoice identifier, QR URL).
6. **Prints** a legal markings block on the invoice PDF (A.1035/2020 art. 3
   par. 7).

---

## Configuration

Go to **Settings → Accounting → Greek E-Invoicing Provider**.

| Setting | Description |
|---------|-------------|
| **Provider** | Select the licensed provider. `None` disables provider routing. Driver modules add options to this list. |
| **Test Environment** | Send to the provider's sandbox. Disable only when going live. |
| **Auto-send on Post** | When enabled, the cron job sends queued invoices automatically. When disabled, use the manual button or Send & Print. |

---

## Transmission flows

### Manual button
Open a posted invoice → click **Send to Provider** in the header. The document
is issued synchronously; errors are shown immediately.

### Send & Print
The provider call is made *before* the PDF renders, so the printed PDF already
carries the MARK and QR code. Errors block the PDF and are surfaced in the
dialog.

### Cron (scheduled job: every 10 minutes)
Processes three queues in order:

1. **Send queue** — `state=to_send` (auto-send companies) or `state=error`
   (all companies; retry previous failures).
2. **PDF upload queue** — marked documents whose PDF has not yet been uploaded
   to the provider.
3. **B2G status poll** — B2G documents waiting for Peppol delivery confirmation.

Each record is processed inside its own savepoint, so a single failure does
not roll back the rest of the batch.

---

## Field reference

### `account.move`

| Field | Type | Description |
|-------|------|-------------|
| `l10n_gr_prov_state` | Selection | `to_send` / `sent` / `error` |
| `l10n_gr_prov_error` | Text | Last error message |
| `l10n_gr_prov_send_datetime` | Datetime | When the document was successfully issued |
| `l10n_gr_prov_mark` | Char | ΜΑΡΚ assigned by AADE |
| `l10n_gr_prov_invoice_id` | Char | Provider's internal invoice ID (used for PDF upload and status polling) |
| `l10n_gr_prov_verification_hash` | Char | SHA-1 Συμβολοσειρά Αυθεντικοποίησης (Appendix B1, A.1035/2020) |
| `l10n_gr_prov_invoice_identifier` | Char | SHA-1 Αναγνωριστικό Παραστατικού (Appendix B2, A.1035/2020) |
| `l10n_gr_prov_qr_url` | Char | URL encoded in the provider QR code |
| `l10n_gr_prov_provider_url` | Char | Provider verification portal URL |
| `l10n_gr_prov_previously_submitted` | Boolean | Set when the provider recovered a marking from a prior submission (AADE error 228) |
| `l10n_gr_prov_pdf_uploaded` | Boolean | Whether the legal PDF has been uploaded to the provider |
| `l10n_gr_prov_applicable` | Boolean (computed) | True when a provider is active and the document is a Greek sale |
| `l10n_gr_prov_b2g` | Boolean | Route through Peppol (public sector) |
| `l10n_gr_prov_contract_ref` | Char | Contract reference ΑΔΑΜ (BT-12) |
| `l10n_gr_prov_budget_type` | Selection | Budget type 1/2/3 (BT-11) |
| `l10n_gr_prov_budget_ref` | Char | ΑΔΑ Ανάληψης or Ενάριθμος ΠΔΕ (BT-11) |
| `l10n_gr_prov_purchase_order_ref` | Char | Purchase order reference (BT-13) |
| `l10n_gr_prov_buyer_ref` | Char | Buyer reference `"name\|ΑΑΗΤ"` (BT-10); auto-defaulted from partner |
| `l10n_gr_prov_b2g_status` | Char | Last B2G/Peppol delivery status |

### `res.partner`

| Field | Type | Description |
|-------|------|-------------|
| `l10n_gr_prov_aaht` | Char | ΑΑΗΤ code from the ΜΑΑΗΤ registry (webapps.gsis.gr/dsae2/foreisreg). Used to default BT-10. |

### `product.template`

| Field | Type | Description |
|-------|------|-------------|
| `l10n_gr_prov_cpv` | Char | Common Procurement Vocabulary code (EC Reg. 213/2008), e.g. `30237200-1`. Mandatory on B2G invoice lines (BT-158, scheme STI). |

### `res.company`

| Field | Type | Description |
|-------|------|-------------|
| `l10n_gr_prov_provider` | Selection | Active provider (`none` by default; drivers add options) |
| `l10n_gr_prov_test_env` | Boolean | Use the provider's test endpoint |
| `l10n_gr_prov_auto_send` | Boolean | Auto-send queued invoices via cron |

---

## Driver dispatch protocol

The base module routes calls to driver modules via the naming convention:

```
_l10n_gr_prov_<operation>_<provider>(self)
```

| Operation | Called when |
|-----------|-------------|
| `send` | Submitting the document to the provider |
| `upload_pdf` | Uploading the legal PDF after marking |
| `poll_b2g_status` | Polling Peppol delivery status (B2G only) |

Example for a provider named `acme`:

```python
def _l10n_gr_prov_send_acme(self):
    ...

def _l10n_gr_prov_upload_pdf_acme(self):
    ...

def _l10n_gr_prov_poll_b2g_status_acme(self):
    ...
```

See [doc/developer_guide.md](doc/developer_guide.md) for the full contract.

---

## Invoice PDF markings

The template `report_invoice_document_l10n_gr_prov` injects a block after the
myDATA QR code when `l10n_gr_prov_mark` is set. It shows:

- Provider QR code (30×30 mm PNG, generated from `l10n_gr_prov_qr_url`)
- ΜΑΡΚ
- Συμβολοσειρά Αυθεντικοποίησης
- Αναγνωριστικό Παραστατικού
- Provider URL

---

## Changelog

### 1.8 — ΤΔΑ/ΠΤΔΑ, dispatch planning data, UI tabs
- **Τιμολόγιο–Δελτίο Αποστολής (ΤΔΑ) & Πιστωτικό ΤΔΑ**: new journal flag
  «Τιμολόγιο – Δελτίο Αποστολής» (`isDeliveryNote`) with ready-made journals
  ΤΔΑ (1.1) and ΠΤΔΑ (5.1). Combined documents send full invoice data plus
  στοιχεία διακίνησης and take part in the delivery lifecycle (status,
  polling, Δελτία Αποστολής list). Σκοπός Διακίνησης defaults to 1 (Πώληση) /
  5 (Επιστροφή on credit notes).
- **Στοιχεία Διακίνησης (planned data, §5.3)**: Έναρξη Αποστολής
  (datetime, auto-defaults to now), Αριθμός Μεταφορικού Μέσου as a reusable
  vehicle list (Οχήματα), εγκαταστάσεις έναρξης/ολοκλήρωσης, Τίτλος Λοιπής
  Αιτίας for σκοπός 19. Vehicle sent via `aadeVehicleNumber`
  (`otherTransportDetails` is deprecated in myDATA v2.0.x).
- **Invoice form split into 4 tabs**: Ψηφιακή Διακίνηση / Κατάσταση &
  Σημάνσεις / myDATA Φόροι / B2G (checkbox reveals the B2G fields).
- Fixed-amount Λοιποί Φόροι/Τέλη categories (hotel & short-term-rental
  taxes, €/τεμ fees) default the labeled amount on selection, editable.
- Clear message when AADE dev does not know a MARK (provider-test MARKs
  are not registered in mydataapidev).

### 1.7 — Ψηφιακή Διακίνηση, tax net, v2.0.1 labels
- **Ψηφιακή Διακίνηση (dispatch lifecycle)**: new menu (Λογιστική → Ψηφιακή
  Διακίνηση) with the ΔΑ list + recipient wizard (Επιβεβαίωση Παραλαβής /
  Απόρριψη via QR URL or MARK, direct to AADE using the l10n_gr_edi
  credentials). Delivery status + lifecycle history on the ΔΑ form, polled by
  cron every 30'. Issuer + recipient roles; RegisterTransfer (carrier) deferred.
- **Journal-driven tax net**: cross-border journals (1.2/2.2/1.3/2.3) auto-apply
  their 0% tax + Απαλλαγή ΦΠΑ reason on lines and restrict the Φόροι dropdown;
  domestic journals offer only the valid GR rates.
- **Classification defaults**: derived from the v2.0.1 map per (inv type ×
  product type) with a sparse override menu; retail types prefer the retail E3
  codes (E3_561_003); product-template overrides are now type-aware.
- **v2.0.1 label refresh**: VAT exemptions renumbered to ν.5144/2024 articles,
  Χαρτόσημο → Ψηφιακό Τέλος Συναλλαγής, official §8.4/8.5/8.7 wording,
  Σκοπός Διακίνησης table §8.14 (codes 6/15/16/17 blocked as non-sendable).
- Extra taxes: category-first UI on one row, fixed-rate categories
  auto-calculate and lock the amount.
- Dispatch types now include the buyer (AADE: counterpart mandatory).
- Classification fields moved to the line detail form (Προβολή).

### 1.6 — myDATA v2.0.1
- **Data refresh to myDATA v2.0.1**: `gr_mydata.py` regenerated from the
  official v2.0.1 xlsx + ERP doc — 53 invoice types, 27 classification
  categories (incl. `category1_10`, `category3`), 106 E3 codes, and the full
  `CLASSIFICATION_MAP` (validated combo-by-combo against the source).
- **New dispatch/delivery types** 9.1, 9.2, 10.1, 10.2 with dedicated journals
  (ΔΑΣ, ΣΔΑ, ΔΠΠ, ΔΠΠΜ) and `category3` classification. (Dispatch *lifecycle*
  API — RegisterTransfer, packaging, QR — is a planned follow-up.)
- **Partner-driven journal net**: on a sale document, `journal_id` is filtered
  by the partner's class (GR company → B2B, individual → retail 11.x, EU →
  intra-community, non-EU → third-country), derived from `is_company` +
  country + VAT. Implemented by narrowing `suitable_journal_ids`.
- **Line classification defaults**: category + E3 auto-fill on product
  selection from a derived default (map + product type), with a sparse
  override table (**Accounting → Configuration → Προεπιλογές Χαρακτηρισμού
  myDATA**) for special cases. Untyped products default to *goods*.
- Classification fields moved off the crowded line grid into the line's detail
  form (Προβολή), with a save-time constraint rejecting invalid type/category/E3
  combos.

### 1.1
- Extended B2G per the national format: budget type and identifier (BT-11),
  purchase order reference (BT-13), buyer reference (BT-10) auto-defaulted
  from customer name and ΑΑΗΤ.
- New ΑΑΗΤ field on contacts (ΜΑΑΗΤ registry code).
- CPV code field on products (BT-158, scheme STI).
- Fixed: `_compute_l10n_gr_prov_buyer_ref` guard is now per-record so it
  correctly defaults all records in a multi-record compute set.
- Fixed: cron uses `savepoint()` per record instead of raw `commit()`.
- Fixed: report template renders the QR barcode once via `t-set`.
- Fixed: partner view anchor changed from `category_id` to `vat` for Odoo 19
  form layout compatibility.

### 1.0
Initial release: provider fields on `account.move`, send-on-demand plus cron
retry queue, legal markings block on the invoice PDF, `l10n_gr_edi`
suppression, B2G reference fields.
