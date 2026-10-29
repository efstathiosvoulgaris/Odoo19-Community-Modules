# Customer signature on pickup — design (repair_shop_tickets + Android app)

Date: 2026-10-29. Status: approved by the user 2026-10-29 («οκ παμε»), defaults below accepted.

## Why

When a customer collects a device — repaired or not — the shop wants proof
that they took it back. Today «Παραλήφθηκε» is a single click with nothing
from the customer. From now on the customer signs on an Android phone at the
till, and the signature is kept on the ticket as the record.

## The flow (approved)

```
Νέο ─► Σε εξέλιξη ◄─► Αναμονή ανταλλακτικών
            │
     ┌──────┴───────────────┐
  Επίλυση            Δεν Επισκευάστηκε  (new, reason required)
     └──────┬───────────────┘
        Επιλύθηκε  (notify / Viber / optional invoice / pickup reminder)
            │  «Παραλήφθηκε»
     Αίτημα υπογραφής → phone  (new)
        ├─ ΟΚ    → Παραλήφθηκε, signature stored on the ticket
        └─ Άκυρο → stays Επιλύθηκε
Ακύρωση: only for tickets that should not exist (wrong entry etc.)
```

## Goals

1. «Δεν Επισκευάστηκε»: unrepaired devices follow the same road as repaired
   ones up to pickup, instead of ending as «Ακύρωση».
2. «Παραλήφθηκε» sends a signature request to the phone; the ticket only
   reaches «Παραλήφθηκε» when the customer signs and presses ΟΚ.
3. The signature, when, and who sent the request are kept on the ticket.

## Non-goals

- No signature at intake (only at pickup).
- No legal e-signature scheme (no certificates, no hashing of the document).
  It is a picture of a signature with a timestamp — the same value as a
  signature on paper.
- No change to invoicing, myDATA, stock rules for repaired devices.
- No Play Store publication.

## Anti-goals (would make this a failure even if it works)

- A ticket stuck forever because the phone is off, broken or lost.
- The phone signing for the wrong ticket (two PCs, one phone).
- Anyone on the internet able to fetch customer names or push fake signatures.
- The phone showing anything beyond name, brand, model.

## Part 1 — «Δεν Επισκευάστηκε» (repair_shop_tickets)

- New field `repair_result`: `repaired` / `not_repaired`, set by the two
  buttons, shown on form, list, kanban and as a search filter.
- New field `not_repaired_reason` (Text). Button «Δεν Επισκευάστηκε» on tickets
  in `in_progress` / `waiting_for_parts` opens a small wizard asking for it
  (required), then sets state `resolved`, `resolved_date`, `repair_result =
  not_repaired`.
- Stock: an unrepaired ticket consumes no parts. If parts were already
  consumed, they are returned (`_reverse_stock`, as «Επαναφορά» does).
  `repair_consume_on == 'invoice'` must also skip unrepaired tickets.
- Invoice stays optional, labour only (a diagnostic fee). Parts lines are not
  invoiced on an unrepaired ticket. The wizard also asks «Χρέωση ελέγχου»
  (default 0) and writes it to `labor_price`, so a repair quote left in that
  field is never invoiced by mistake. *(My call.)*
- Viber: a second text in Settings, «Κείμενο Viber: Δεν Επισκευάστηκε»
  (default «…η συσκευή σας είναι διαθέσιμη για παραλαβή…»), used by the
  existing Viber button when `repair_result == 'not_repaired'`.
- «Επαναφορά» clears `repair_result` and the reason.
- Pickup reminder cron: unchanged, it already works on `resolved`.
- Existing tickets: `repair_result` is set to `repaired` for tickets already
  `resolved` / `picked_up` (migration). Cancelled ones from the v13 import
  (`not_solved`) stay cancelled.

## Part 2 — signature request (repair_shop_tickets)

### Signing device

New model `service.signature.device` (Manager only), following the
`shop_quick_login` device pattern: name, `active`, `token_hash` (sha256 of the
device token, the token itself never stored), `last_seen`, pairing code hash +
expiry, paired at / by.

Pairing: Manager opens the device record → «Σύζευξη» → Odoo shows a one-time
8-character code valid 10 minutes. On the phone the setup screen asks for the
server address and that code; the app calls `/service_sign/pair` and receives
its token. «Αποσύνδεση» on the record wipes the token (lost phone).

Which device gets a request: the company setting «Συσκευή υπογραφής». One
phone now; the setting makes a second one a configuration change. *(My call.)*

### Request

New model `service.signature.request`: ticket, device, `state`
(`pending` / `signed` / `declined` / `cancelled` / `expired`), requested by
(user), requested at, answered at, `kind` (repaired / not_repaired, copied
from the ticket so the phone shows the right sentence).

- «Παραλήφθηκε» on a `resolved` ticket creates a `pending` request and opens a
  dialog on the PC: «Αναμονή υπογραφής πελάτη…» with «Ακύρωση αιτήματος».
- One `pending` request per device at a time. If the other PC already has one
  open, the second gets a clear message («Η συσκευή υπογραφής περιμένει
  υπογραφή για το SRV/0123») instead of replacing it. *(My call.)*
- A pending request expires after 5 minutes (checked when read, no cron
  needed).
- On ΟΚ from the phone: the signature PNG is stored on the ticket
  (`pickup_signature`, Binary attachment; `pickup_signed_at`;
  `pickup_signature_request_id`), posted in the chatter as an image, and the
  ticket goes to `picked_up` in the same transaction.
- On Άκυρο: request `declined`, ticket untouched, PC dialog says so.
- The PC dialog polls the request every ~1.5 s and closes / reloads the form
  when it is answered. *(My call: polling, not the bus — fewer moving parts.)*

### No way around the signature *(my call)*

`picked_up` is reachable only through a signed request or the fallback below.
The server refuses any other write of `state = 'picked_up'` (kanban drag,
list edit, import), for every user including admin; the two legitimate paths
pass a context flag. Migration scripts that need it pass the same flag.

### Fallback when the phone is unavailable

Manager-only button «Παραλήφθηκε χωρίς υπογραφή» with a required reason,
logged in the chatter. Without it a dead phone blocks every pickup.
*(My call — see "Open for the user".)*

### Endpoints (auth='none', device token in `Authorization: Bearer`)

| Route | Does |
|---|---|
| `POST /service_sign/pair` `{code}` | → `{token}`; wrong/expired code → error, rate-limited |
| `GET /service_sign/poll` | → the device's pending request `{id, customer, brand, model, sentence}` or nothing; updates `last_seen` |
| `POST /service_sign/answer` `{id, decision, png}` | `decision` ok/decline; png base64, max ~300 KB, must be a PNG |

- Only the device's own pending, unexpired request can be answered.
- Payload to the phone: customer name, brand, model, the sentence. No phone
  number, no address, no prices.
- HTTPS only (through nginx, as everything else). The app stores server
  address **and database name**, and sends `db` on every call (no session
  cookie with `auth='none'`). One phone serves one database at a time; moving
  it from `test` to `skarlas` means unpair + pair again. *(My call.)*

### Sentence above the signature

Two settings with defaults *(my call — the user did not decide)*:
- repaired: «Παρέλαβα τη συσκευή μου.»
- not repaired: «Παρέλαβα τη συσκευή μου χωρίς επισκευή.»

### Where the signature is seen

Ticket form: a «Παραλαβή» group showing the signature image, date, who sent
the request. Chatter: the image. Printout: not in this change. *(My call.)*

## Part 3 — Android app

Native APK, decided by the user (over a PWA) so it can wake the screen and run
by itself.

- Kotlin, single module, AndroidX only, `HttpURLConnection` — no other
  libraries. minSdk 26 (Android 8); target the current SDK.
- The phone is a **dedicated device** at the till, always on the charger.
  Foreground-service type, full-screen-intent permission and vendor battery
  settings are chosen for the actual model and Android version (read over
  adb before building); setup steps for that model go in the app README.
- **Foreground service** polls `/service_sign/poll` every 2 s (persistent
  notification «Υπογραφές Service — ενεργό»). Starts at boot
  (`BOOT_COMPLETED`) and when the app opens. Asks for the battery-optimisation
  exemption on first run.
- On a request: opens the signing activity full screen, turning the screen on
  and showing over the lock screen (`setTurnScreenOn`, `setShowWhenLocked`).
- Signing screen: customer name (large), brand + model, the sentence, a
  white signing area, buttons «Καθαρισμός», «Άκυρο», «ΟΚ» (ΟΚ disabled until
  something is drawn). Landscape. On ΟΚ: PNG of the area, cropped, sent;
  «Ευχαριστούμε» for 2 s, then back to idle.
- If the request is cancelled/expired on the PC side while open, the next poll
  closes the screen.
- Idle screen: «Έτοιμο — αναμονή…», server, device name, last contact; a
  hidden long-press opens setup (server address, pairing code, unpair).
- Token kept in app-private storage.
- Network errors: keep retrying quietly; the idle screen shows «Χωρίς
  σύνδεση» after 30 s without contact.

### Source, build, install

- Source in `Desktop\Odoo19\signature_app\` — its own git repo, not inside
  `addons\` (that folder is uploaded to the server). *(My call.)*
- Toolchain to install on this PC: JDK 17, Android command-line tools,
  platform + build-tools (~3–4 GB). Gradle wrapper in the project.
- Signed with one release keystore kept outside git
  (`signature_app\keystore\`, gitignored, password in Windows Credential
  Manager). Same key forever or updates will not install over the old app.
- Installed with `adb install -r` over Wi-Fi on the user's test phone.

## Rollout

`repair_shop_tickets` → 1.9 (changelog in manifest). Test DB first, the user
tests in the Odoo UI with the phone; then skarlas. Shared addons ⇒ upgrade both
DBs on schema change.

## Left to the builder

Code structure, wizard vs inline field for the reason, exact field and route
names, the PC dialog implementation (client action / OWL dialog), the
signature view in the app (custom `View` with `Path`), poll interval tuning,
rate-limit details.

## Still to settle

- Phone make / Android version: read over adb when the user connects it,
  before the Android service is written.
- Fallback «Παραλήφθηκε χωρίς υπογραφή»: kept, Service Managers only
  (default accepted; widen if pickups get stuck without a manager).
