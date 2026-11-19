# Greek accounting setup fixes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the «Αυτόματη Ρύθμιση Λογιστικής (myDATA)» button leave a correct Greek chart on any database, then clean the leftovers that exist only in eskarlas, and settle the rest with the accountant.

**Architecture:** Every fix that a clean install would also need goes into the existing button (`action_l10n_gr_prov_tidy_taxes`, `l10n_gr_provider_base/models/res_config_settings.py:37`), idempotent and counted in its notification, resolved by chart xmlid via `gr_tax(env, company, template_id)` (`gr_mydata.py:1250`), never by name or code. Leftovers that exist only in eskarlas are one-off ORM scripts run with the user's approval. Choices of account (which code a shop uses) wait for the accountant.

**Tech Stack:** Odoo 19, Python, `odoo shell` on the server (`docker exec -u odoo odoo19 /entrypoint.sh odoo shell -d <db> --no-http`).

**Spec:** audit of 2026-11-18 — memory `coa-audit-2026-11-18.md`, and the export `scratchpad/coa/coa_test.json` (test ≈ skarlas).

## Global Constraints

- Product rule: no eskarlas ids, names, codes or URLs in addon code. Resolve accounts and taxes by chart xmlid (`account.{company.id}_l10n_gr_…`); work per `company`; must run on a clean DB.
- User rule overrides TDD: **no new test files, no scripted test runs.** Verification is (a) a read-only `odoo shell` check whose output I compare, (b) the user pressing the button and testing in the Odoo UI on `test`.
- Never overwrite a value the user chose: change only values still equal to the chart/Odoo default, or empty.
- Server: upload + `docker restart odoo19` (Python changed) + `-u` on `test` first; `skarlas` only after the user confirms. No DB edits outside the button without asking.
- Commit once at end of day, when the user asks.
- After code changes: `graphify update .`.

## Review Focus

1. Company set to prices **excluding** tax (`account_price_include = 'tax_excluded'`) — purchase fix must change nothing.
2. A purchase tax the user explicitly set `price_include_override = 'tax_included'` — keep it.
3. POS receivable already set by the user to some other receivable account — keep it; only a non-receivable (cash) account is repaired.
4. Journal default account changed by the user — keep it; only the generic chart default (70.01.01) is moved.
5. Pressing the button twice — second run reports 0 changes for every new counter.

---

### Task 1: Purchase taxes priced excluding VAT

Company setting «prices include tax» (right for retail sales) makes every purchase tax price-included, so vendor bills split VAT out of a net price.

**Files:** Modify `l10n_gr_provider_base/models/res_config_settings.py` (inside `action_l10n_gr_prov_tidy_taxes`, before the notification is built).

- [ ] **Step 1:** Add `_l10n_gr_prov_purchase_tax_excluded(self, company) -> int` on `res.config.settings`: purchase taxes of `company` (`active_test=False`) where `price_include` is True **and** `price_include_override` is empty → write `price_include_override = 'tax_excluded'`; return the count.
- [ ] **Step 2:** Call it from the button; add `purchase_excl` to the message: «%(n)s φόροι αγορών ορίστηκαν χωρίς ΦΠΑ στην τιμή».
- [ ] **Step 3 (verify, read-only shell):** after the button on `test`, `env['account.tax'].search([('type_tax_use','=','purchase'),('active','=',True)]).mapped('price_include')` → all False; sale taxes unchanged (all True). Second press → counter 0.
- [ ] **Step 4 (user, UI):** vendor bill, product with 24% Αγορές Αγαθών, unit 100 → net 100, VAT 24, total 124.

### Task 2: POS receivable on a receivable account

The chart sets `account_default_pos_receivable_account_id` to 38.01 Ταμείο; the button only fills it when empty (`res_config_settings.py:93-96`).

**Files:** Modify `l10n_gr_provider_base/models/res_config_settings.py:93-96`.

- [ ] **Step 1:** Change the condition to «empty **or** `account_type != 'asset_receivable'`»; the target stays `gr_tax(env, company, 'l10n_gr_30_01_01_01')`; update the comment (the chart does set it, to a cash account).
- [ ] **Step 2 (verify):** `env.company.account_default_pos_receivable_account_id.code` → `30.01.01.01`; second press → `pos_receivable` 0.
- [ ] **Step 3 (user, UI):** new POS session, one cash + one card + one «Επί Πιστώσει» sale, close the session → entries go through 30.01.01.01, cash journal balance = only the cash.
- Note: old closed sessions keep their entries on 38.01; no rewrite (accountant decides if a correcting entry is needed).

### Task 3: Service journals default to service income

All sale journals get 70.01.01 (`_GR_JOURNAL_DEFAULT_ACCOUNT`, `account_journal.py:144`), including services.

**Files:** Modify `l10n_gr_provider_base/models/account_journal.py:144-180` (`_l10n_gr_prov_journal_defaults`).

- [ ] **Step 1:** Service document types (`l10n_gr_edi_inv_type_default` in `2.1, 2.2, 2.3, 2.4, 11.2`) default to `l10n_gr_70_07_01`.
- [ ] **Step 2:** For our own journals (xmlid in `l10n_gr_provider_base`) of those types whose `default_account_id` is still the generic `l10n_gr_70_01_01`, move it to 70.07.01; count as `service_income`; others untouched.
- [ ] **Step 3 (verify):** ΑΠΥ, ΤΠΥ… → 70.07.01; ΑΛΠ, ΤΙΜ → 70.01.01. Second press → 0.
- Note: lines with a product take the product/category income account, not the journal's; per-category services wait for Task 6.

### Task 4: Greek names for the chart accounts Odoo mislabels

From Odoo's own chart: `l10n_gr_64_14` and `l10n_gr_71_06` are both «εισόδημα από διαφορά μετρητών»; `transfer_account_id`, `account_journal_payment_debit_account_id`, `account_journal_payment_credit_account_id` are English only.

**Files:** Modify `l10n_gr_provider_base/models/gr_mydata.py` (new `ACCOUNT_RENAME_MAP` next to `TAX_RENAME_MAP`, ~1260) and the button.

- [ ] **Step 1:** `ACCOUNT_RENAME_MAP = {template_id: (greek_name, names_it_may_still_have)}`:
  - `l10n_gr_64_14` → «Ζημιές από διαφορές ταμείου»
  - `l10n_gr_71_06` → «Κέρδη από διαφορές ταμείου»
  - `transfer_account_id` → «Μεταφορές ρευστότητας»
  - `account_journal_payment_debit_account_id` → «Εισπράξεις υπό εκκαθάριση»
  - `account_journal_payment_credit_account_id` → «Πληρωμές υπό εκκαθάριση»
- [ ] **Step 2:** Rename in el_GR only when the current el_GR name is the shipped one (or equals the en_US name); count `accounts_renamed`. Codes are not changed (accountant, Task 6).
- [ ] **Step 3 (verify):** the five names as above; second press → 0.

### Task 5: eskarlas leftovers (one-off, approval per item)

Not in the addon — these exist only in this DB. Script per DB, `test` first.

- [ ] **5a «Μετρητά Εστίασης»** (Assbar, hand-made, bank type on BNK1, 4 payments): give Assbar its own cash journal and switch the method to it. Needs: user OK, Assbar session closed.
- [ ] **5b journal `CASH`** (sale type, no account, 0 moves, no xmlid): archive.
- [ ] **5c** keep `ΠΩΛ`: it is the cutover target for open v13 invoices (`migration/CUTOVER_2026-10.md`).
- [ ] **Verify:** read-only shell lists before/after; user opens Assbar POS and takes one cash sale.

### Task 6: Accountant decisions (question sheet)

**Files:** Create `docs/accountant_questions_2026-11.md` (Greek, one page).

- [ ] Questions, each with current value and proposed answer:
  1. Purchases: 20.02.00 Αγορές εμπορευμάτων (periodic inventory) or stock valuation accounts (perpetual)? Today everything goes to 64.01.01.01.
  2. Services income: 70.07.01 for repair/service products (category)?
  3. Cash/bank: keep Odoo's 38.00.01 Τράπεζα / 38.00.02 Μετρητά or move journals to 38.02.00 / 38.01.00?
  4. Old POS entries already on 38.01: correcting entry or not?
  5. Cash-difference codes 64.14 / 71.06: fine, or other accounts?
  6. Reduced-rate intra-EU acquisitions (13/6%) and the island fiscal position: activate?
  7. 54.02.03 Καταβληθείς ΦΠΑ typed as payable: change?
- [ ] After answers: a follow-up plan; settled values go into the button as defaults (product rule).

### Task 7: Deploy and hand over

- [ ] Bump `l10n_gr_provider_base` version + changelog line; upload; `docker restart odoo19`; `-u l10n_gr_provider_base` on `test`; read logs.
- [ ] User presses the button on `test`, runs Task 1–3 UI checks.
- [ ] On the user's OK: `-u` on `skarlas`, user presses the button there.
- [ ] `graphify update .`; memory update; commit when asked.

Not in scope (checked, no change needed): 0% exemption reason — cross-border journals already set it (`INV_TYPE_ZERO_TAX`), domestic exemptions depend on the article so no single default fits. Pure delivery notes (9.x/10.x) — zero-priced lines, no posted ones carry value in `test` (only ΤΔΑ = invoice+delivery, correctly valued).
