# Fresh-database validation checklist

Run this whenever you create a new database, to prove the suite works
out of the box rather than only on a database that grew alongside the code.
Every step states the **expected result** — anything else is a finding worth
fixing before a customer hits it.

_Code audited for fresh-install hazards on 26 July 2026: ACLs complete for all
8 custom models; the serial-number block degrades silently if Inventory isn't
installed; the report action binds its own paperformat._

---

## 1. Create the database and the company

1. Create a new database (no demo data for the realistic case; a second run
   **with** demo data is a useful stress test later).
2. Company: country **Greece**, a valid ΑΦΜ, full address (**city and ZIP are
   mandatory** — the provider rejects documents without them), phone, email.

## 2. Install the modules

Install **`l10n_gr_provider_base`** first: it pulls `l10n_gr_edi`, the Greek
chart (`l10n_gr`) and `l10n_gr_partner` automatically. Then:

| Module | Needed for |
|---|---|
| `l10n_gr_provider_ilyda` | the actual provider API (required) |
| `l10n_gr_provider_eftpos` | Α.1155 card signatures on backend invoices |
| `l10n_gr_provider_pos` | POS issuance (installs `point_of_sale`) |
| `l10n_gr_provider_pos_eftpos` | **auto-installs** once POS + eftpos are both present |
| `aade_vat_lookup` | ΑΦΜ lookup from the AADE registry |
| `l10n_gr_translation_fixes`, `l10n_gr_partner_pos` | optional polish |

**Expected:** no install errors; `l10n_gr_provider_pos_eftpos` appears installed
without being asked for.

## 3. Verify what should be automatic

| Check | Where | Expected |
|---|---|---|
| Greek journals | Accounting → Configuration → Journals | **55** GR journals (32 sale, 23 purchase) — ΤΙΜ, ΑΛΠ, ΔΑ, ΠΙΣΤ, ΤΚ1… |
| Paperformats | Technical → Paper Formats | «GR Παραστατικό A4» **top 85 / header spacing 80 / bottom 30**, and «GR 80mm Απόδειξη» (dpi 96) |
| Report binding | Technical → Reports → «Παραστατικό» | Paper format = **GR Παραστατικό A4** (not the company default) |
| Menu | Accounting top bar | **myDATA** menu present (Ψηφιακή Διακίνηση, Προεπιλογές Χαρακτηρισμού, Οχήματα, Κλειδιά Offline QR, Διαβιβάσεις) |
| Crons | Technical → Scheduled Actions | «process queue» (10 min) and «Poll Delivery Note Status» (30 min), both active |

> If the journals are missing, the chart was loaded **after** the module — the
> button in step 4 creates them, which is the intended recovery.

## 4. Press the setup button once

**Accounting → Configuration → Settings → Ελληνικός Πάροχος → «Τακτοποίηση Καταλόγου Φόρων»**

**Expected notification**, roughly: _N μετονομασίες φόρων, N ενεργοποιήσεις,
N αρχειοθετήσεις, N διορθώσεις νησιωτικών ΦΠΑ, **0 νέα ημερολόγια** (already
created), … **6** μονάδες μέτρησης με κωδικό ΑΑΔΕ, **5** νέοι τρόποι πληρωμής POS._

Then spot-check:
- Taxes renamed to Greek («ΦΠΑ 24%», «24% Αγορές Αγαθών»…).
- Units (Configuration → Units): Units→1, kg→2, L→3, m→4, m²→5, m³→6.
- POS payment methods: IRIS, Web Banking, Επιταγή, 2× Τραπεζική Μεταφορά — each
  with its AADE code, **not** attached to any till.

## 5. Configure what stays manual (by design)

1. **Provider credentials** — Settings → Ελληνικός Πάροχος: provider = ILYDA,
   username/password, **Test environment ON**.
2. **Offline QR key** (TF-1) — myDATA → Κλειδιά Offline QR: issue, then verify.
   Without a *verified* key there is no offline fallback.
3. **POS** — Point of Sale → Configuration → Settings → Πάροχος myDATA:
   ΑΛΠ journal, ΤΙΜ journal, ΠΛΠ journal, walk-in partner («Πελάτης Λιανικής»,
   create the contact first), Α.1155 terminal.
4. **EFT terminal** — myDATA → Τερματικά EFT/POS: terminal id + NSP protocol.
5. Tick which payment methods each till offers.

## 6. Smoke tests (the ones that matter)

| # | Scenario | Expected |
|---|---|---|
| 1 | Post + send a **ΤΙΜ (1.1)** to a B2B customer | MARK, hash, QR on the record |
| 2 | Print it | GR A4 form: header repeats, QR/MARK footer, correct margins |
| 3 | **Credit note (5.1)** from that invoice | references the original MARK |
| 4 | **ΑΛΠ via POS, cash** | receipt shows MARK + QR; payment method **3** in the payload |
| 5 | **POS card** (Α.1155) | signature popup → transaction id → payment type **7** with signature |
| 6 | **ΔΑ (9.3)** with a kg or litre product | accepted; `measurementUnit` = 2 or 3, not 1 |
| 7 | Invoice with a **serial-numbered** product (Inventory + «Display Lots & Serial Numbers on Invoices» on) | `SN: …` row under its line on the A4 |
| 8 | Post an invoice **dated yesterday** and let the cron run | flips to **Abandoned**, no retry loop |

## 7. Record the findings

Note anything that needed a manual step not listed in section 5 — that is a bug
in the out-of-the-box experience, not a configuration task.
