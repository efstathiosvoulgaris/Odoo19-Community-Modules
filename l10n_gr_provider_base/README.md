# l10n_gr_provider_base — Greece E-Invoicing Provider Base

**Version:** 2.10 | **Odoo:** 19 | **License:** LGPL-3

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
| `l10n_gr_prov_applicable` | Boolean (computed) | True when a provider is active, the document is a Greek sale, **and its journal carries a myDATA type**. A journal without one is an accounting-only book (the chart's ΠΩΛ, for recording old invoices) and is never transmitted. |
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

## Tests

`tests/test_mydata_tables.py` — the pure myDATA layer: partner class → allowed
invoice types, classification defaults, `all_above` expansion, the rate tables,
and the module's own `_demo()` integrity assertions. `tests/test_try_send.py` —
the transmission state machine (sent / queued / duplicate guard / offline
fallback / error) with the driver dispatch replaced. Neither contacts a
provider or needs a configured company.

---

## Changelog

### 2.11 — Κρατήσεις υπέρ Τρίτων (BG-24)
- New move field **`l10n_gr_prov_yper3_amount`** («Κρατήσεις υπέρ Τρίτων Φορέων
  (BG-24)»), on the myDATA Φόροι tab, visible only for B2G. It is text-only
  information for the Ελλην. Δημόσιο (ΕΑΑΔΗΣΥ, ΑΕΠΠ, υπέρ Ψυχικής Υγείας…) and
  by design changes **no** total — see the ILYDA changelog for the transmission
  side.

### 2.10 — One unit, told the same way twice
- **Street numbers reach AADE separately.** BT-36 (`sellerAddressLine2`) and
  every `number` in `otherDeliveryNoteHeader` are mandatory on dispatch
  documents (MDP-0024 / MDP-0026), but Odoo has no house-number field, so
  «Γεωργαντά 22» sat whole in `street` and the number went out empty.
  `res.partner._l10n_gr_prov_street_number()` returns the pair: «Αριθμός»
  (`arithmos_odou`) or `street2` when filled, otherwise the trailing number is
  split off `street`. A dispatch note whose loading or delivery address is
  still missing street/number/city/ZIP is now refused before transmission,
  naming the partner and the missing parts.
- The setup button now **unarchives** the AADE units as well as stamping them.
  Odoo ships m³ archived, so «Κυβικά Μέτρα» was stamped with code 6 and still
  impossible to pick on a line. It also reports how many active units carry no
  §8.13 code — those transmit as 7 (Λοιπές Περιπτώσεις) with their name.
  Ones with no code that nothing refers to are archived, so the picker stops
  offering units that can only go out as 7. Use is decided by scanning every
  stored relational field pointing at `uom.uom`, which is what keeps g, ml and
  mm — the base units of kg, L and m — out of it. Reversible from the
  «Archived» filter.
- **A journal without a myDATA type is now accounting-only.** Posting a sale on
  one no longer queues it, the send button is gone, and the auto-send cron
  leaves it alone. Before this, an invoice on the chart's «Πωλήσεις» (ΠΩΛ) —
  the book for recording old invoices a customer still owes — was queued on
  post and transmitted to AADE as 1.1, the type core `l10n_gr_edi` fills in on
  its own. Every provider control on the form already keyed off
  `l10n_gr_prov_applicable`, so such a document now looks like a plain Odoo
  invoice.
- The «Invoice Type» selector is gone from the invoice form. The myDATA type
  comes from the journal, and so do numbering, print form, allowed taxes and
  EFT/POS routing — the selector only ever appeared on a journal without a type
  (the chart's own «Πωλήσεις»/ΠΩΛ), where changing it moved nothing but itself.
  The now-unused helper field `journal_id_inv_type_default` was dropped with it.
- `invoicedQuantityUnits` (BT-130) was hardcoded `EA`, so a line billed in κιλά
  went to AADE as measurement unit 2 and to the buyer as «each». The UN/ECE
  Rec 20 code is now derived from the same §8.13 code (`REC20_BY_AADE_UNIT`),
  which is why they cannot drift apart. Only κιλά/λίτρα/μέτρα/m²/m³ change
  value; τεμάχια stay `EA`.
- A row that carries a quantity (διακίνηση, δελτίο αποστολής, 8.6, and a
  document closing catering notes) is refused before transmission when the
  quantity is not > 0. The XSD types it `minExclusive 0`, and AADE's rejection
  does not name the offending line.
- An unmapped unit still transmits as §8.13 code 7 with the unit name and the
  quantity as `otherMeasurementUnitTitle`/`otherMeasurementUnitQuantity`, e.g.
  «500_g». Note 9 means that pair as a *packaging* count, which Odoo does not
  model here; nothing validates it. Set «Είδος Ποσότητας» on the unit of
  measure to avoid code 7 altogether.

### 2.9 — Constraints that never existed
- Odoo 19 stopped reading `_sql_constraints`, so the uniqueness rules on
  Προεπιλογές Χαρακτηρισμού (τύπος/είδος/εταιρεία) and on Οχήματα
  (όνομα/εταιρεία) were silently absent from the database. Ported to
  `models.Constraint`.

### 2.8 — A4/80mm print rework
- One source of truth for the form (`_l10n_gr_prov_print_form`): paper choice,
  QWeb routing and header geometry all read it, so a database with no provider
  configured prints the plain Odoo form instead of the Odoo template laid over
  Greek geometry.
- Issuer block, μηχανογραφικός τίτλος and buyer moved out of the repeating
  wkhtmltopdf header into page flow — header height no longer depends on
  customer data (`margin_top` 85 → 10).
- Amount correctness: ΑΞΙΑ/ΕΚΠΤΩΣΗ computed from `price_subtotal` (a
  VAT-inclusive pricelist used to print gross value and the VAT as a discount);
  ΑΝΑΛΥΣΗ ΦΠΑ read from the posted tax lines, so it matches the totals column
  exactly. Decimal comma throughout.
- Legal markings that were stored but never printed: vatExemptionCategory,
  «Αυτοτιμολόγηση» (3.1/3.2), ΣΤΟΙΧΕΙΑ ΔΙΑΚΙΝΗΣΗΣ, ΓΕΜΗ and issuer activity,
  delivery address, due date. ΩΡΑ ΑΠΟΣΤΟΛΗΣ shows the dispatch start, not the
  transmission moment.
- 80mm receipt lines print gross (`price_total`) with VAT analysis per rate.

### 2.7 — Journal setup hardened
- Odoo translates the sales journal code «INV» to «ΤΙΜ» in Greek, taking the
  code the 1.1 journal needs; the chart journal is moved to «ΠΩΛ» instead.
- Journals are created after the chart loads, carry an explicit sequence so the
  picker follows myDATA order, are repaired when code or type drifts, and
  collisions are logged rather than passed over.

### 2.6 — Units, Επισήμανση, paperformat
- AADE measurement units (§8.13) on `uom.uom`, stamped by the settings button.
- Επισήμανση (§8.15) on invoice lines for Εκκαθάριση Πωλήσεων Τρίτων.
- The «Παραστατικό» report binds its own paperformat; the POS receivable
  account is set, without which every POS payment fails on a fresh database.

### 2.5 — Classification off the onchange path
- Serial numbers print inline under their invoice line.
- Lines created outside the onchange path (sale invoicing, imports, POS) derive
  their myDATA classification and cross-border 0% tax at create.

### 2.4 — The retry queue gives up
- Documents whose issue date has passed are unacceptable to AADE (ER-30); the
  cron abandons them with a new «abandoned» state. TF-1 offline documents keep
  retrying.

### 2.3 — 8.2 Ειδικό Στοιχείο Τέλους Διαμονής (ΤΔΙ)
- Button on marked invoices builds the fee document server-side (8.2 journal,
  correlation, zero line, category1_95, fee = fixed € × nights from the stay
  document); journal default per property fee category; per-night amount
  recomputed from category/correlation.

### 2.2 — «Διαβιβάσεις» log
- Every provider-routed document in one list (state, MARK, send date,
  PDF-uploaded flag, error) with filters for pending / errors / PDF backlog and
  grouping by state, journal or month.

### 2.1 — myDATA menu, tax guards, tax tidy-up
- Consolidated «myDATA» menu in the Accounting bar; vehicles get their own
  screen; Ρυθμίσεις myDATA visible to Accounting managers only.
- Tax guards (admin-toggleable, default on): posting is blocked with a listed
  reason on a line without VAT, a tax outside the document type's allowed set,
  0% without an exemption reason, a missing classification, or an island-rate
  inconsistency.
- Τακτοποίηση Καταλόγου Φόρων: self-explanatory Greek tax names, unused «EU
  Other» variants archived; internal matching switched from names to chart
  xmlids so renames are safe.

### 2.0 — TF-1 offline QR (Α.1112/2025)
- Offline signing keys (issue/verify/revoke through the provider), automatic
  fallback to a locally signed JWS QR when the provider is unreachable, new
  «offline» state with forced retries and a 1-day deadline warning, offline
  notice on the PDF. Send button hidden while queued (TF-2).

### 1.9 — Provider search & reconciliation
- «Ανάκτηση από Πάροχο» action and myDATA UID field; a failed document is
  looked up at the provider before any retry resend, so a resend cannot
  duplicate it.
- New «queued» state for TF-2 (provider accepted, AADE offline): the PDF prints
  the provider QR with a waiting notice and the cron polls until the MARK
  arrives.

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
- **Τρόποι Πληρωμής (§5.2/§8.12)**: multiple payment methods per document
  (types 1–8 incl. Άμεσες Πληρωμές IRIS) with amount, info, tip and
  transaction id, on a dedicated «Πληρωμές» tab. One line is auto-seeded on
  post from the myDATA payment method for the full payable; new lines
  default to the remainder. POS Α.1155 signature fields deferred until a
  POS provider integration exists.

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
