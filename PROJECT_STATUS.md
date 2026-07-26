# Greek e-invoicing suite — project status

_Last reviewed: 24 July 2026 · 36 commits since 4 June 2026 · Odoo 19.0_

A stocktake of the `l10n_gr_provider_*` suite and its companion modules: what is
built and working, what is known-shaky, and what is left to develop.

---

## 1. The stack at a glance

| Module | Ver | Size | Role |
|---|---|---|---|
| `l10n_gr_provider_base` | 2.4 | ~3 950 py / 1 360 xml | Provider-agnostic core: myDATA constants, journals, guards, forms, dispatch, offline keys |
| `l10n_gr_provider_ilyda` | 2.2 | ~1 475 py | ILYDA (vs.gr) driver — the only provider implementation |
| `l10n_gr_provider_eftpos` | 1.0 | ~510 py | Α.1155 card-terminal signatures on backend invoices |
| `l10n_gr_provider_pos` | 1.2 | ~355 py | POS orders issued as ΑΛΠ / ΤΙΜ / ΠΛΑ through the provider |
| `l10n_gr_provider_pos_eftpos` | 1.0 | ~260 py | Bridge: Α.1155 signature flow inside the POS payment screen |
| `aade_vat_lookup` | 1.1 | ~330 py | ΑΦΜ lookup against the AADE RgWsPublic2 SOAP service |
| `l10n_gr_partner` (+`_pos`) | 1.0 | ~185 py | Greek partner fields (ΔΟΥ, ΓΕΜΗ, επωνυμία, αριθμός) + POS search |
| `l10n_gr_translation_fixes` | 1.1 | ~150 py | Greek UI terminology corrections |

Architecture: **base** defines the model and dispatches operations by name to a
driver (`_l10n_gr_prov_<operation>_<provider>`); **ilyda** implements them. A
second provider would only need a new driver module.

---

## 2. What is built and working

### Document issuance
- Invoice types **1.1 – 11.5** submittable through the provider; accounting-only
  types (13.x–17.x) correctly excluded and left to the core ERP channel.
- Journals for the whole Greek document set auto-created per company, with
  series codes (ΤΙΜ, ΑΛΠ, ΔΑ, ΠΙΣΤ …) and no year in the sequence.
- Partner-class → journal filtering (b2b / retail / eu / third country).
- Send on post (queued), Send & Print integration, manual send button.
- Credit notes with `precedingInvoices`, correlated documents, self-billing
  (Τίτλος Κτήσης 3.1/3.2 on the purchase side).
- **8.2 Ειδικό Στοιχείο Τέλους Διαμονής** — full special-case handling.
- B2G / Peppol routing fields (ΑΔΑΜ, ΑΔΑ, BT-10/11/12/13/15) + status polling.

### Resilience (the legally important part)
- **TF-2** — provider accepted, AADE offline: document parked in `queued`, MARK
  recovered later by poll. Implemented.
- **TF-1** — provider unreachable: locally signed offline QR (JWS/HS256), key
  lifecycle (issue → verify → revoke), Α.1112/2025 one-day deadline warning.
  Implemented; **verified working in a separate session**.
- Duplicate guard: before re-submitting, the document is looked up by UID
  (A.1035 Appendix B2 algorithm, self-checked on every marked document).
- Every record processed in its own savepoint; failures never roll back a batch.

### Tax & classification correctness
- Full myDATA v2.0.1 data: 53 invoice types, 27 classification categories,
  106 E3 codes, the whole valid-combination map, VAT categories and exemptions,
  withholding / fees / stamp duty / other-taxes tables.
- Derived line classification (product type → category + E3), sparse override
  table, product-template overrides.
- Pre-post guards: wrong tax for the document type, 0 % without an exemption
  reason, island vs mainland VAT rates, missing classification.
- "Τακτοποίηση Καταλόγου Φόρων" button: renames chart taxes to meaningful Greek
  names, archives unused ones, fixes the upstream island-VAT fiscal-position
  bug, creates missing journals, and (new) creates the Greek POS payment methods.

### Ψηφιακή Διακίνηση (dispatch)
- ΔΑ types 9.1/9.2/9.3 and ΔΠΠ 10.1/10.2, combined ΤΔΑ/ΠΤΔΑ documents.
- Planned dispatch data, vehicles, movement purpose, reverse delivery (§8.21).
- AADE-direct lifecycle: status polling (30-min cron), recipient confirm/reject.
- ΔΑ → ΤΙΜ and ΔΑ → reverse-ΔΑ follow-up actions.

### Point of Sale
- Every order issued as ΑΛΠ (11.x), ΤΙΜ (1.1) on request, ΠΛΑ (11.4) for refunds.
- Walk-in retail partner, line classification derived server-side.
- Receipt carries MARK, authentication string, provider QR, or the TF-1/TF-2
  pending notice; a failed transmission never blocks the sale.
- Payment methods mapped to AADE §8.12 codes, derived live from the method kind
  (cash→3, card→7, IRIS→8, on-credit→5) with an optional manual override.
- **Α.1155 in the POS**: signature requested at payment, cashier charges the
  terminal and enters the transaction id, document transmitted with signature +
  terminalId + transactionId. Working end-to-end.

### Printing
- Greek box-grid A4 form (ΕΝΙΑΙΟ ΜΗΧΑΝΟΓΡΑΦΙΚΟ ΕΝΤΥΠΟ) with repeating header
  (masthead, document type, counterparty), repeating footer (QR, MARK,
  authentication, page counter), unbreakable totals block, serial numbers
  inline under each line.
- 80 mm thermal form for retail receipts, per-journal form selection and
  paperformat routing.

---

## 3. Left to develop

### Agreed for the next round
1. **Cron give-up for stale documents.** A document with no MARK whose issue date
   has passed can never be accepted (AADE `ER-30`), yet it is retried every
   10 minutes forever. Add an `abandoned` state + a manual re-queue button;
   `offline` (TF-1) documents deliberately keep retrying.
2. **Measurement units.** `measurementUnit` is hardcoded to `1` (τεμάχια) on
   dispatch rows. Map Odoo units → AADE §8.13 (1 τεμ · 2 κιλά · 3 λίτρα ·
   4 μέτρα · 5 τ.μ. · 6 κ.μ. · 7 λοιπές, which also needs
   `otherMeasurementUnitTitle`/`Quantity`). Odoo already ships every needed
   unit — only the mapping and a button to stamp it are missing.

### Open, not yet scheduled
3. **No automated tests.** `gr_mydata._demo()` is a good self-check but is not
   wired into Odoo's test runner. Nothing guards the classification map,
   `partner_class`, payment grouping or the UID algorithm against a future edit.
4. **Paperformat / view DB drift.** Paperformat records and report views ignore
   module updates once touched; margins had to be set by hand three times. A
   migration that force-writes them would stop the next database needing it.
5. **NSP terminal drivers** (Viva, Cardlink, Mellon …) — the POS flow is manual
   entry by design; automatic terminal drive is a separate per-vendor build.
6. **`RegisterTransfer`** (carrier role in Ψηφιακή Διακίνηση) — intentionally
   not built; third-party carriers make that call themselves.
7. **Second provider driver** — the dispatch architecture supports it; only
   ILYDA exists today.
8. **Purchase-side transmission** (13.x/14.x expense classifications) still goes
   through the core `l10n_gr_edi` ERP channel, by design. Revisit only if the
   provider should own that too.
9. **Type 1.5 (Εκκαθάριση Πωλήσεων Τρίτων) — partially supported.** The
   Επισήμανση (§8.15) is modelled on the line, transmitted as
   `invoiceDetailType`, and validated (a 1.5 needs both a «1» sales line and a
   «2» commission line). What is unresolved is the totals rule: ILYDA computes
   the AADE totals from the commission lines only and then rejects the document
   because the EN16931 totals cover every line (`BG-22-MISMATCH`). The likely
   fix — EN16931 lines/totals = commission only, `aadeData` keeps both row
   types, mirroring the 8.2 precedent — was deferred: no 1.5 example exists in
   the bundle, the spec doesn't state the rule, and the business doesn't issue
   these documents. Get a sample payload from ILYDA before implementing.

---

## 4. Operational gotchas (bite on every fresh database)

- **Paperformat "GR Παραστατικό A4" must be set by hand**: Top margin **85**,
  header spacing **80**, bottom **30**. Module updates do not touch it.
- **Report views may need "Reset View → file version"** (Technical → Views) if
  they were ever edited in the UI, otherwise template changes never appear.
- **Printed PDFs are cached as attachments** — delete the attachment or use a
  fresh document when testing form changes.
- **POS caches its JS bundle** — close and reopen the session after asset changes.
- The test database holds old failed documents that can never succeed
  (`ER-30`, `MDP-0001`, `MDP-0110`); they are test-data artifacts, not bugs, and
  item 3.1 above will silence them.

---

## 5. Repository state

Last commit `0396664` (22 July). Uncommitted since then: the A4/80 mm form work,
inline serial numbers, the POS payment-type rework and its migration, the Greek
POS payment methods, the AADE SOAP escaping fix, and the entire untracked
`l10n_gr_provider_pos_eftpos` module. Remote is
`github.com/efstathiosvoulgaris/Odoo19-Community-Modules`; pushes must be run
locally (no credentials in the agent sandbox).
