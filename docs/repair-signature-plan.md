# Pickup signature — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** «Δεν Επισκευάστηκε» path, and «Παραλήφθηκε» only after the customer signs on an Android phone, with the signature kept on the ticket.

**Architecture:** `repair_shop_tickets` 1.9 gets two wizards, a signing-device model, a request model, three `auth='none'` HTTP routes and one OWL client action that waits on the PC. A separate native Kotlin app polls those routes from a foreground service and shows a full-screen signing view.

**Tech Stack:** Odoo 19 (Python, XML views, OWL), Kotlin + AndroidX, Gradle wrapper, JDK 17, adb over Wi-Fi.

**Spec:** `docs/repair-signature-design.md`

## Global Constraints

- **No automated tests and no scripted DB runs.** The user tests in the Odoo UI (memory: "No DB testing"). Each task's check is: `python -m py_compile` on changed `.py` files, an XML well-formedness check on changed `.xml` files, then a list of **UI checks for the user**.
- **One commit at the end of the day** in `addons/`, not per task (memory: "Commit cadence"). `signature_app/` has its own git repo, same cadence.
- Deploy: copy to `/root/odoo19/extra-addons`; Python changed → `docker restart odoo19` **first**, then upgrade with `docker exec -u odoo odoo19 /entrypoint.sh odoo -d <db> -u repair_shop_tickets --stop-after-init`. Test DB first; skarlas only after the user says so. Shared addons ⇒ upgrade both DBs once released.
- UI text is Greek; code, comments in the existing English style; match the density of `service_ticket.py`.
- Phone payload: customer name, brand, model, sentence. Nothing else.
- Pending request expires after **5 minutes**; pairing code is **8 characters**, valid **10 minutes**; PNG max **300 KB**; phone polls every **2 s**; PC dialog polls every **1.5 s**; app shows «Χωρίς σύνδεση» after **30 s** without contact.
- Android: minSdk 26, AndroidX only, `HttpURLConnection`, no other libraries. Package `gr.eskarlas.signature`.

## Review Focus

1. Two PCs press «Παραλήφθηκε» on different tickets at once → second gets «Η συσκευή υπογραφής περιμένει υπογραφή για το SRV/…», first is untouched. (Task 3 UI check.)
2. Customer signs after the request expired or was cancelled on the PC → answer refused, ticket untouched, phone returns to idle. (Task 4 UI check.)
3. Kanban drag / list edit into «Παραλήφθηκε» → refused for admin too. (Task 3 UI check.)
4. Phone off, Wi-Fi down, or app killed by the vendor's battery manager → PC dialog keeps waiting, can be cancelled, Manager fallback closes the ticket. (Tasks 3, 7 checks.)
5. «Δεν Επισκευάστηκε» on a ticket whose parts already left stock (`repair_consume_on = resolve` then «Επαναφορά» edge) → parts returned, invoice has labour only. (Task 1 UI check.)

---

### Task 1: «Δεν Επισκευάστηκε»

**Files:**
- Modify: `models/service_ticket.py` (fields, `action_resolved`, `action_reset_to_in_progress`, `action_create_invoice`)
- Modify: `models/service_ticket_viber.py` (`action_viber_ready` picks the text)
- Modify: `models/res_company.py`, `models/res_config_settings.py`, `views/res_config_settings_views.xml`
- Create: `wizard/__init__.py`, `wizard/not_repaired_wizard.py`, `wizard/not_repaired_wizard_views.xml`
- Modify: `__init__.py`, `__manifest__.py` (data), `security/ir.model.access.csv`, `views/service_ticket_views.xml`
- Create: `migrations/1.9/post-repair_result.py`

**Interfaces:**
- Produces: `service.ticket.repair_result` Selection `[('repaired','Επισκευάστηκε'), ('not_repaired','Δεν Επισκευάστηκε')]`, `not_repaired_reason` Text, `_set_not_repaired(reason: str, fee: float) -> None`; company field `repair_viber_not_repaired_text` Text.

- [ ] **Step 1:** Add the two ticket fields (both `copy=False`, `tracking=True` on `repair_result`). `action_resolved` also writes `repair_result='repaired'`. `action_reset_to_in_progress` clears both.
- [ ] **Step 2:** Implement `_set_not_repaired(reason, fee)`: reverse stock if `stock_consumed`; write `state='resolved'`, `resolved_date=now`, `repair_result='not_repaired'`, `not_repaired_reason=reason`, `labor_price=fee`.
- [ ] **Step 3:** Transient `service.ticket.not.repaired.wizard` (`ticket_id`, `reason` Text required, `fee` Float default 0, label «Χρέωση ελέγχου»); `action_confirm()` calls `_set_not_repaired`. Button «Δεν Επισκευάστηκε» in the header, visible in `in_progress`/`waiting_for_parts`, opens it. Access: `base.group_user` 1,1,1,1.
- [ ] **Step 4:** `action_create_invoice`: when `repair_result == 'not_repaired'` skip `line_ids` and skip `_consume_stock`; labour only.
- [ ] **Step 5:** Company text `repair_viber_not_repaired_text`, string «Viber: Δεν Επισκευάστηκε», default «Καλησπέρα σας. Η συσκευή σας {device} (δελτίο {ticket}) είναι διαθέσιμη για παραλαβή. {company}», same help as the ready text; settings related field and view. `action_viber_ready` uses it when `repair_result == 'not_repaired'`.
- [ ] **Step 6:** Show `repair_result` (badge) and reason on the form; `repair_result` in list and kanban card; search filters «Επισκευάστηκε» / «Δεν Επισκευάστηκε».
- [ ] **Step 7:** Migration `post-repair_result.py`: SQL `UPDATE service_ticket SET repair_result='repaired' WHERE state IN ('resolved','picked_up') AND repair_result IS NULL`.
- [ ] **Step 8:** Compile and XML checks pass. **UI checks for the user** (test DB): ticket with consumed parts → «Δεν Επισκευάστηκε», reason empty refused, with reason → Επιλύθηκε + badge, stock returned; invoice shows only «Εργασία» with the fee; Viber opens with the not-repaired text; «Επαναφορά» clears the badge; old resolved tickets show «Επισκευάστηκε».

### Task 2: Signing device and pairing

**Files:**
- Create: `models/signature_device.py`, `views/signature_device_views.xml`
- Modify: `models/__init__.py`, `models/res_company.py`, `models/res_config_settings.py`, `views/res_config_settings_views.xml`, `views/service_ticket_menus.xml`, `security/ir.model.access.csv`, `__manifest__.py`

**Interfaces:**
- Produces: model `service.signature.device` with `name`, `active`, `token_hash`, `pair_code_hash`, `pair_until`, `pair_failures` Integer, `paired_at`, `paired_by`, `last_seen`; `action_pair() -> dict` (sticky notification showing the code), `action_unpair() -> None`, `@api.model _pair(code: str) -> str | False` (returns the token), `@api.model _from_token(token: str) -> record` (empty if unknown/inactive); module function `token_hash(token) -> str` (sha256, copy from `shop_quick_login/models/device.py`).
- Produces: company fields `repair_signature_device_id` M2o, `repair_sign_text_repaired` Char default «Παρέλαβα τη συσκευή μου.», `repair_sign_text_not_repaired` Char default «Παρέλαβα τη συσκευή μου χωρίς επισκευή.».

- [ ] **Step 1:** Model and Manager-only access (`group_service_ticket_manager` 1,1,1,1; no user access — requests read it with `sudo()`). Menu Service → Configuration → «Συσκευές Υπογραφής».
- [ ] **Step 2:** `action_pair`: code from `secrets.choice` over `ABCDEFGHJKLMNPQRSTUVWXYZ23456789`, 8 chars; store hash, `pair_until = now + 10 min`, `pair_failures = 0`; return a sticky `display_notification` with the code.
- [ ] **Step 3:** `_pair(code)`: find a device with `pair_until > now` and matching hash (`hmac.compare_digest`); on a miss, increment `pair_failures` on every device with a live code and wipe the code once it reaches 5; on a hit, new `secrets.token_urlsafe(32)`, store its hash, clear the code, set `paired_at`. `action_unpair` clears `token_hash`.
- [ ] **Step 4:** Settings block «Υπογραφή Παραλαβής»: device, two sentences.
- [ ] **Step 5:** Checks pass. **UI checks:** create device, «Σύζευξη» shows a code; second press replaces it; non-manager cannot open the menu.

### Task 3: Request, guarded pickup, fallback

**Files:**
- Create: `models/signature_request.py`, `wizard/pickup_unsigned_wizard.py`, `wizard/pickup_unsigned_wizard_views.xml`
- Modify: `models/service_ticket.py` (`write`, `action_picked_up`, new fields), `views/service_ticket_views.xml`, `security/ir.model.access.csv`, `__manifest__.py`

**Interfaces:**
- Consumes: Task 1 `repair_result`; Task 2 `repair_signature_device_id`, sentences.
- Produces: model `service.signature.request` — `ticket_id`, `device_id`, `kind` (`repaired`/`not_repaired`), `state` (`pending`/`signed`/`declined`/`cancelled`/`expired`), `requested_by`, `answered_at`; `EXPIRE_MINUTES = 5`; `_expire_stale() -> None`; `_payload() -> dict` `{id, customer, brand, model, sentence}`; `action_cancel()`; `_answer(decision: str, png: bytes) -> bool`.
- Produces: ticket fields `pickup_signature` Binary(attachment=True), `pickup_signed_at`, `pickup_request_id`, `pickup_unsigned_reason` Text; `_mark_picked_up(**vals)` (writes `state='picked_up'` with context `repair_pickup_ok=True`); `action_picked_up()` returns `{'type': 'ir.actions.client', 'tag': 'repair_shop_tickets.signature_wait', 'params': {'request_id': id}}`.

- [ ] **Step 1:** `service.ticket.write`: if `vals.get('state') == 'picked_up'` and not `self.env.context.get('repair_pickup_ok')` → `UserError('Η παραλαβή ολοκληρώνεται μόνο με υπογραφή πελάτη.')`.
- [ ] **Step 2:** `action_picked_up`: requires `state == 'resolved'` and a configured device (else UserError naming the setting); `_expire_stale()`; a pending request on the device for another ticket → UserError «Η συσκευή υπογραφής περιμένει υπογραφή για το %s.»; a pending one for this ticket is reused; else create. Return the client action.
- [ ] **Step 3:** `_answer`: only if `state == 'pending'` and not expired; `ok` → store PNG on ticket, `pickup_signed_at`, `pickup_request_id`, `message_post` with the PNG as attachment, `_mark_picked_up()`, state `signed`; `decline` → state `declined`, chatter line. Returns False when refused.
- [ ] **Step 4:** Wizard «Παραλήφθηκε χωρίς υπογραφή» (reason required) → `_mark_picked_up(pickup_unsigned_reason=reason)` + chatter. Button visible to `group_service_ticket_manager` in `resolved`. Access user-group read only on requests; manager full.
- [ ] **Step 5:** Form group «Παραλαβή»: signature image, date, `pickup_request_id.requested_by`, unsigned reason. Kanban: `records_draggable` stays, the write guard refuses.
- [ ] **Step 6:** Checks pass. **UI checks:** drag a card to Παραλήφθηκε → error (as admin too); fallback as manager works, hidden for user; second ticket while one pending → busy message.

### Task 4: Phone endpoints

**Files:**
- Create: `controllers/__init__.py`, `controllers/signature.py`
- Modify: `__init__.py`

**Interfaces:**
- Consumes: Task 2 `_pair`, `_from_token`; Task 3 `_expire_stale`, `_payload`, `_answer`.
- Produces (all `type='http'`, `auth='none'`, `csrf=False`, JSON in/out, `Cache-Control: no-store`, every call carries `db`):
  - `POST /service_sign/pair` body `{db, code}` → `{token}` or `{error}` 
  - `GET /service_sign/poll?db=` header `Authorization: Bearer <token>` → `{request: {...}|null}`; sets `last_seen`
  - `POST /service_sign/answer` body `{db, id, decision: "ok"|"decline", png: base64}` → `{ok: bool}`; 401 on bad token.

- [ ] **Step 1:** First confirm in the Odoo 19 image (`odoo/http.py`, `_get_session_and_dbname`) how a `db` query parameter selects the database for `auth='none'`. If it is honoured, pass `?db=` on every route (POSTs too); if not, open `odoo.modules.registry.Registry(db)` explicitly and check `db` against `http.db_filter`. Write the chosen mechanism as one comment at the top of the controller.
- [ ] **Step 2:** Implement the three routes; `answer` rejects non-PNG (`\x89PNG` magic), > 300 KB, or a request not belonging to the device.
- [ ] **Step 3:** Checks pass. Manual curl from this PC against the test host (pair with a real code, poll, answer decline) — this hits HTTP only, no DB script. **UI check:** decline on a pending ticket leaves it Επιλύθηκε; answer after 5 min is refused.

### Task 5: PC waiting dialog

**Files:**
- Create: `static/src/signature_wait.js`, `static/src/signature_wait.xml`
- Modify: `__manifest__.py` (assets), `models/signature_request.py` (`read_status` RPC)

**Interfaces:**
- Consumes: client action tag `repair_shop_tickets.signature_wait`, `params.request_id`.
- Produces: `service.signature.request.read_status() -> {'state': str, 'ticket': str}` (calls `_expire_stale` first).

- [ ] **Step 1:** OWL dialog «Αναμονή υπογραφής πελάτη…» with ticket name and «Ακύρωση αιτήματος»; polls `read_status` every 1.5 s; on `signed` → success notification, close, reload the form (`soft_reload` / `restore`); `declined` → warning «Ο πελάτης πάτησε Άκυρο», close; `expired`/`cancelled` → close with info. Cancel button calls `action_cancel`. Pattern: `open_viber.js`.
- [ ] **Step 2:** Checks pass; deploy to test (restart, upgrade). **UI checks:** dialog appears, cancel works, curl `answer ok` from Task 4 closes it and the ticket is Παραλήφθηκε with the image.

### Task 6: Android toolchain (needs the user's OK — downloads ~3–4 GB)

- [ ] **Step 1:** Ask the user before downloading: Temurin JDK 17 (adoptium.net), Android command-line tools (developer.android.com). Install under `C:\Android\` (SDK) and the JDK default path.
- [ ] **Step 2:** `sdkmanager "platform-tools" "platforms;android-35" "build-tools;35.0.0"`, accept licences only after the user agrees.
- [ ] **Step 3:** With the user's phone on adb Wi-Fi: `adb shell getprop ro.product.manufacturer`, `ro.product.model`, `ro.build.version.sdk`. Record them in the design's "Still to settle" and pick the foreground-service type (`specialUse` on API 34+) and vendor setup steps.

### Task 7: Android app

**Files (`Desktop\Odoo19\signature_app\`, `git init`):**
- `settings.gradle.kts`, `build.gradle.kts`, `app/build.gradle.kts`, Gradle wrapper, `.gitignore` (`keystore/`, `build/`, `local.properties`), `README.md` (pairing + vendor battery steps)
- `app/src/main/AndroidManifest.xml`
- `app/src/main/java/gr/eskarlas/signature/`: `Prefs.kt`, `Api.kt`, `PollService.kt`, `BootReceiver.kt`, `MainActivity.kt`, `SignActivity.kt`, `SignatureView.kt`

**Interfaces:**
- Consumes: Task 4 routes.
- Produces: `Api.pair(server, db, code): String`, `Api.poll(): Request?` (`data class Request(id: Int, customer: String, brand: String, model: String, sentence: String)`), `Api.answer(id: Int, ok: Boolean, png: ByteArray?): Boolean`; `SignatureView.isEmpty(): Boolean`, `.toPng(): ByteArray` (cropped to the ink bounds + margin, white background), `.clear()`.

- [ ] **Step 1:** Project skeleton, release keystore in `keystore/` (password into Credential Manager as `eskarlas-signature-keystore`), `assembleRelease` builds an empty app.
- [ ] **Step 2:** `MainActivity`: idle screen «Έτοιμο — αναμονή…», server, device, last contact, «Χωρίς σύνδεση» after 30 s; long-press on the title opens setup (server URL, db, code, «Αποσύνδεση»). Starts `PollService`; asks for battery-optimisation exemption and notification / full-screen-intent permission on first run.
- [ ] **Step 3:** `PollService`: foreground, notification «Υπογραφές Service — ενεργό», polls every 2 s; on a new request id launches `SignActivity` via a full-screen-intent notification (works from background and lock screen); broadcasts "request gone" when the poll returns null for the open id. `BootReceiver` starts it.
- [ ] **Step 4:** `SignActivity`: landscape, `setShowWhenLocked(true)`, `setTurnScreenOn(true)`, keep screen on; customer large, brand + model, sentence, `SignatureView`, «Καθαρισμός» «Άκυρο» «ΟΚ» (ΟΚ disabled while empty); on ΟΚ send PNG, show «Ευχαριστούμε» 2 s, finish; on Άκυρο send decline; closes itself on "request gone"; back button = Άκυρο.
- [ ] **Step 5:** `adb install -r app-release.apk`; pair against the test DB. **Checks with the user:** screen off + locked → request wakes it; ΟΚ closes the PC dialog and the ticket shows the signature; Άκυρο; cancel on the PC closes the phone screen; Wi-Fi off 30 s → «Χωρίς σύνδεση», back on → recovers; reboot phone → service back without opening the app.

### Task 8: Release

- [ ] **Step 1:** Manifest `1.9` changelog entry (one paragraph, existing style); README section for pairing; update memory `repair-viber-messages.md`.
- [ ] **Step 2:** End-of-day commit in `addons/` and `signature_app/`.
- [ ] **Step 3:** After the user's go: deploy to skarlas (restart, upgrade), pair the shop phone against skarlas.
