# Contracts: work hours + notifications — design (short)

**Why:** the owner wants every user told when a contract is expiring/expired/renewed/not renewed, and to see who worked how many hours on each contract. Product rule: sellable, no Project dependency (Project was removed from skarlas on purpose).

**Approaches:** (1) Odoo timesheets — needs Project/hr_timesheet: rejected by the user. (2) own small hours model inside `maintenance_contracts` — **picked**. For notifications: Discuss channel (needs members/management) vs a note posted on the contract that notifies chosen users — **picked** the note.

**Design (maintenance_contracts 1.1, deps unchanged: account, mail):**
- `service.contract.hours`: contract, date (today), user (current user), hours (float_time), description. Users create/edit/delete only their own lines; `account.group_account_manager` all.
- Contract: tab «Ώρες» (editable list), `hours_total` (stored), optional `hours_included` → `hours_left` (red when < 0). No invoicing of hours. Lines are not copied on renewal.
- Menu «Ώρες Εργασίας»: all lines, group by user / contract / month.
- Notifications on: entering «Λήγει σύντομα», entering «Ληγμένο», «Ανανέωση», «Δεν ανανεώνεται». A note in the contract chatter that notifies the company's `contract_notify_user_ids` (setting «Ειδοποίηση σε χρήστες»; empty = all internal users of the company), never the user who pressed the button. Delivery (Inbox/email) follows each user's preference. The responsible's «Ανανέωση συμβολαίου» activity stays.
- Not in: hours billing, Discuss channel.

Approved by the user in chat 2026-11-19.
