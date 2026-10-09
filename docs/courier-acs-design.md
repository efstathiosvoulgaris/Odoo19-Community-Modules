# Courier vouchers from Odoo — design (courier_vouchers)

Date: 2026-10-09. Status: approved in chat, awaiting review of this file.

## Goal

Create courier vouchers (shipping labels) from inside Odoo 19, starting with
ACS and built so that Geniki Taxydromiki, BOX NOW, ELTA Courier, Speedex,
Courier Center and others each become one more file in the same addon.

## Decisions taken

| Question | Decision |
|---|---|
| Couriers | All eventually; **ACS first** (credentials available) |
| Where vouchers are made | From a **delivery order**, and **standalone** to any contact (no order) |
| Cash on delivery | Amount filled **automatically** from the order, editable on the voucher |
| Printing | **A4 laser** only (ACS Print_Type=2, 3 labels per page) |
| Volume | **One voucher at a time**; no bulk creation |
| Testing | On the **real ACS account**: create → print → delete the same day; never issue a pickup list in tests |
| Architecture | **Own model `courier.voucher`**, not Odoo's `delivery.carrier` framework (it cannot do standalone vouchers or the ACS lifecycle) |

## Addon

**One addon, `courier_vouchers`.** The shared part (accounts, vouchers,
states, buttons, delivery-order integration, cron, the courier interface)
knows no courier; each courier is one file inside it (`models/courier_acs.py`,
later `courier_geniki.py`, `courier_boxnow.py`, …) plus its credential block
in the account view. Depends on `stock_delivery` (for `carrier_tracking_ref`)
and `mail`.

No dependency on the myDATA provider addons. **Skroutz is left alone
entirely:** Skroutz orders get their vouchers from Skroutz itself; this addon
neither reads nor writes anything of the Skroutz connector.

## Data model (`courier_vouchers`)

### `courier.account` — Αποστολές → Ρυθμίσεις → Λογαριασμοί Courier

- `name`, `courier` (Selection, extended by each courier addon via
  `selection_add`), `company_id`, `active`
- `sender_name` — sender printed on the label
- `default_weight` (kg, default 0.5), `default_charge_type`
  (`sender` / `recipient`)
- Courier-specific credentials are added by the courier addon, shown with
  `password="True"`, restricted to the settings group, filled in by the user.

### `courier.voucher` — Αποστολές → Vouchers (`mail.thread`)

- `name` — the courier's voucher number; empty while draft
- `account_id` (required), `picking_id` (optional), `sale_order_id`
  (related/stored from the picking, optional)
- `partner_id` — recipient: the picking's delivery address, or picked by hand
- Recipient snapshot, copied from the partner on change and editable without
  touching the contact: `recipient_name`, `recipient_company`, `street`,
  `street_number`, `zip`, `city` (area), `phone`, `mobile`, `email`,
  `country_code` (GR only in the first build)
- `weight`, `item_quantity` (parcels, default 1), `cod_amount`, `notes`,
  `reference` (order or delivery number)
- `pickup_date` — today, moved to the next working day on Sunday
- `state`: `draft` → `created` → `printed` → `manifested` / `cancelled`
  → `delivered` / `returned`
- `label_pdf` (attachment), `pickup_list_ref`, `tracking_status` (latest
  text), `tracking_url`

The street number is split from `street` the same way as
`l10n_gr_provider_base` `_l10n_gr_prov_street_number` (explicit
`arithmos_odou`/`street2` first, then trailing number). The helper is copied,
not imported, to keep the dependency out.

### `stock.picking`

- Smart button «Vouchers (n)», header button «Δημιουργία Voucher» (opens a
  new draft voucher prefilled from the picking)
- When a voucher reaches `created`, its number is written to
  `carrier_tracking_ref`; cancelling clears it if it still holds that number.

### Cash on delivery

`sale.order` gets `courier_cod` (Boolean «Αντικαταβολή»). The voucher's
`cod_amount` defaults to the order's `amount_total` when it is set. It is
ticked by hand on the order.

## Courier interface

Methods on `courier.account`, dispatched by `courier`:

| Method | Returns |
|---|---|
| `_courier_create(voucher)` | voucher number |
| `_courier_print(vouchers)` | PDF bytes |
| `_courier_cancel(voucher)` | — |
| `_courier_close_day(date)` | pickup list number + PDF |
| `_courier_track(voucher)` | status code + text |

`courier_vouchers` raises «not implemented for this courier» for an unknown
`courier`.

## Flow

1. **«Αποστολή»** (draft → created): validates first — address, postcode,
   mobile, weight ≥ 0.5 — then calls `_courier_create` and stores the number.
2. **Same click, print** (created → printed): A4 PDF stored as `label_pdf` and
   downloaded. Never split from step 1: ACS refuses the pickup list while any
   voucher is unprinted. «Επανεκτύπωση» until the list is issued.
3. **«Ακύρωση»** (created/printed → cancelled): only before the pickup list.
4. **«Λίστα Παραλαβής Ημέρας»** (list view button, per account): issues and
   prints today's list; the day's printed vouchers → `manifested`.
5. **Tracking**: cron every 3 hours over `manifested` vouchers, plus a
   «Ενημέρωση κατάστασης» button. Delivered → `delivered`; returned →
   `returned`.

## ACS mapping (`models/courier_acs.py`)

Spec: `Desktop\Odoo19\Courier API\ACS\english-acs-web-services-2025.md`.

- One URL `https://webservices.acscourier.net/ACSRestServices/api/ACSAutoRest`,
  POST JSON `{"ACSAlias": ..., "ACSInputParameters": {...}}`, header
  `ACSApiKey`. **No separate test server.**
- Credentials: API key, `Company_ID`, `Company_Password`, `User_ID`,
  `User_Password`, `Billing_Code`.
- Create: `ACS_Create_Voucher`. `Charge_Type` 2 (sender) / 4 (recipient).
  COD: `Acs_Delivery_Products='COD'`, `Cod_Ammount`, `Cod_Payment_Way=0`.
  `Reference_Key1` = reference. `Language` null (Greek). Numbers unquoted,
  decimals with a dot.
- Print: `ACS_Print_Voucher`, `Print_Type=2`, `Start_Position=1`.
- Cancel: `ACS_Delete_Voucher` — refused once in a pickup list.
- Close day: `ACS_Issue_Pickup_List` (`Pickup_Date` = the vouchers' date,
  `MyData` null) then `ACS_Print_Pickup_List` with `Mass_Number`. If it
  reports unprinted vouchers, show their numbers.
- Track: `ACS_Trackingsummary`. `shipment_status` 4 → delivered; 6/7 or
  `returned_flag` 1 → returned; otherwise keep `delivery_info` as text.

## Errors

- Nothing is written to the voucher unless the courier returned a number.
- HTTP 403 → «Λάθος API key ACS»; 406 → «Πάρα πολλές κλήσεις, ξαναδοκιμάστε».
- `ACSExecution_HasError` or a non-empty `Error_Message` → UserError with
  ACS's own text; the voucher stays where it was.
- Every call is logged to the voucher's chatter (alias + result). Credentials
  never appear in chatter or logs.

## Testing (in the browser on `test`, by Claude, no scripted DB writes)

1. User fills in the ACS credentials on the account.
2. Standalone voucher to a contact → create → label PDF correct → delete.
3. Voucher from a delivery order → number in `carrier_tracking_ref` →
   delete → field cleared.
4. COD voucher → amount on the label → delete.
5. Errors: bad postcode, no mobile, wrong API key (user changes it) →
   clear message, voucher stays draft.
6. **Not tested until the first real shipment:** pickup list, tracking.

## Out of scope for this build

Other couriers, bulk vouchers, thermal printing, ACS SmartPoint/lockers,
price calculation, COD settlement tracking, Cyprus, anything Skroutz.

## BOX NOW (`models/courier_boxnow.py`, version 1.2, agreed 2026-10-09)

Spec: `Courier API/BOXNOW/BoxNow API Manual (v.7.2).md`.

- **Auth:** OAuth2 client credentials (`/api/v1/auth-sessions`), token 1 h,
  cached on the account and refreshed automatically; one retry on 401.
  Account fields: Client ID, Client Secret, API URL (given by BOX NOW),
  «Δοκιμαστικό (Sandbox)». Stage exists → **everything is tested in sandbox**.
- **Origin: AnyAPM only** (`locationId "2"`) — the business drops parcels at
  any locker. Compartment size (1/2/3) mandatory. Sender contact = company
  phone + email, name = account sender name.
- **Destination: a locker** (`courier.boxnow.locker`, synced from the
  location API `/destinations?locationType=apm` by a button and a weekly
  cron). Choosing the recipient proposes the **closest locker**
  (`/api/v2/delivery-requests:checkAddressDelivery`); the user can pick
  another by postcode/name, or press «Κοντινότερο» again.
- **Checks before sending:** locker, mobile (normalised to +30…), email,
  compartment size; company phone and email.
- **Create:** `POST /delivery-requests`, `orderNumber` = reference + voucher
  id (unique), one item per parcel, weight in grams, COD →
  `paymentMode cod` + `amountToBeCollected`. Voucher number = first parcel id.
- **Label:** `labels:search` with A4 first; if refused, BOX NOW's own label.
- **Cancel:** `parcels/{id}:cancel`, only while the parcel is «new».
- **No pickup list** — button hidden; tracking (`GET /parcels?parcelId=`)
  starts once printed: delivered / returned / cancelled map to the voucher
  states, the last event is kept as text.
- Pickup date and sender/recipient charge are hidden on BOX NOW vouchers.

## Geniki Taxydromiki (`models/courier_geniki.py`, version 1.4, agreed 2026-10-09)

Spec: `Courier API/GENIKI/jobservicesapiv2.md`. SOAP via `odoo.tools.zeep`.

- **Auth:** `Authenticate(username, password, application key)` → key kept
  on the account; result 11 (invalid key) → authenticate once and retry.
  «Δοκιμαστικό» toggles `testvoucher.taxydromiki.gr`.
- **Create:** `CreateJob(Voucher)`: address = street + number in one field,
  mobile +30…, `Services` `ΑΜ` for COD and `ΧΠ` for recipient pays,
  `ReceivedDate` = pickup date. Job id stored on the voucher for cancelling.
- **Print:** `GetVouchersPdf` over HTTP GET, format `Flyer` (A4).
- **Cancel:** `CancelJob(jobId, true)` — refused (code 4) once finalised.
- **Finalise («Οριστικοποίηση Ημέρας», replaces the pickup-list button for
  Geniki):** `ClosePendingJobsByDate(last finalisation → now)`, as Geniki
  recommends; no document. The base close-day now accepts a courier that
  returns no PDF and closes only the vouchers the courier reports.
- **Track:** `TrackAndTrace`: `DELIVERED` → delivered, delivered at
  `RETURN TO SENDER` → returned; last checkpoint as text.
- **Later:** locker (`ΠΘ`) and shop (`ΒΡ`) delivery.
- Geniki issues production credentials only after confirming authenticate,
  create, print, cancel and finalise work — the test round covers exactly
  those.
