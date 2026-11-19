# Contract hours + notifications — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans. Steps use `- [ ]`.

**Goal:** maintenance_contracts 1.1 — work-hours log per contract and notifications to chosen users on expiry/renewal.
**Architecture:** one new model + fields on `service.contract`/`res.company`; notifications are `message_post` notes with `partner_ids`.
**Tech Stack:** Odoo 19. **Spec:** `docs/superpowers/specs/2026-11-19-contract-hours-notifications-design.md`

## Global Constraints
- No new dependencies (account, mail only). No eskarlas data in code; per company.
- User rule: no new test files / scripted runs — verify by `-u` on `test` without errors + user UI checks.
- Deploy: upload, `docker restart odoo19`, `-u maintenance_contracts` on `test`, then skarlas after the user's OK.

## Review Focus
1. A user editing another user's hours → refused (record rule); manager → allowed.
2. Renewal → new contract has 0 hours, old keeps its lines.
3. Cron run twice in a day → each transition notifies once (notify only on state change).
4. Empty notify setting → all internal users of the contract's company, not other companies' users, never the acting user.
5. `hours_included` = 0 → «απομένουν» hidden, no red.

### Task 1: Hours model
Files: create `models/service_contract_hours.py`, `security/service_contract_security.xml`; modify `models/__init__.py`, `security/ir.model.access.csv`, `models/service_contract.py`, `__manifest__.py`.
- [ ] `service.contract.hours` (`_order = 'date desc, id desc'`): `contract_id` (required, cascade, index), `date` (required, today), `user_id` (required, current user, internal only), `hours` (Float), `name` (Char «Τι έγινε»), `company_id` related stored.
- [ ] Contract: `hour_ids` (copy=False), `hours_total` (compute stored on `hour_ids.hours`), `hours_included` (Float, tracking), `hours_left` = included − total.
- [ ] Access: user rwc+unlink, manager all. Rules: `base.group_user` write/create/unlink only `user_id = user.id`; `account.group_account_manager` all.

### Task 2: Views + menu
Files: `views/service_contract_views.xml`, `views/service_contract_menus.xml`.
- [ ] Form: `hours_included`, `hours_total`, `hours_left` (invisible when not included, red when < 0); page «Ώρες» editable bottom list (date, user, hours float_time sum, name).
- [ ] List: `hours_total` optional show.
- [ ] Hours list/search/action + menu «Ώρες Εργασίας» (group by user, contract, `date:month`; filter «Δικές μου», «Αυτός ο μήνας»).

### Task 3: Notifications
Files: `models/res_company.py`, `models/res_config_settings.py`, `views/res_config_settings_views.xml`, `models/service_contract.py`.
- [ ] `res.company.contract_notify_user_ids` (m2m res.users) + related setting «Ειδοποίηση σε χρήστες» (help: κενό = όλοι οι εσωτερικοί χρήστες).
- [ ] `service.contract._notify_users(body)`: recipients = setting or internal active users of `company_id`, minus `env.user`; `message_post(body, subtype_xmlid='mail.mt_note', partner_ids=…)`.
- [ ] Call it: in `_refresh_state` when a contract changes to `expiring` / `expired`; in `action_renew`, `action_not_renewed`.

### Task 4: Ship
- [ ] Version 1.1 + changelog; deploy to `test`; logs clean; user checks (own vs other's hours, renew, not renewed, notification in Inbox); then skarlas; `graphify update .`; memory.
