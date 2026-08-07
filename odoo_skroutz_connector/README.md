# Skroutz Connector for Odoo 19

**Version:** 1.7 | **Odoo:** 19 | **License:** LGPL-3

Connects Odoo 19 to the [Skroutz Marketplace](https://www.skroutz.gr) via:
- XML product feed (for Skroutz to crawl)
- Order webhook (Skroutz pushes order events to Odoo)
- Order management API (accept, reject, dispatch)

## Features

### XML Feed
- Serves a Skroutz-compatible XML feed at `/skroutz/feed`
- Optional feed token: `/skroutz/feed?token=YOUR_TOKEN`
- Products included when **published on the website** and have a non-empty **MPN** (set on the Skroutz tab)
- Configurable zero-stock inclusion and default availability label
- Supports optional Skroutz fields per product: size, color, season, size fit, outlet flag, per-product shipping cost

### Order Webhook
- Receives order events at `/skroutz/webhook` or `/skroutz/webhook/<secret>`
- Skroutz does not sign webhook requests — authentication is via URL token
- Returns HTTP 500 on processing error so Skroutz retries (up to 4 times in 20 minutes)
- Creates or updates `skroutz.order` records from webhook payloads

### Order Management
- **Accept**: opens wizard with live pickup location/window options fetched from Skroutz API
- **Reject**: selection of rejection reason, sent as human-readable text
- **Dispatch** (FBM only): sends courier + tracking code(s) to Skroutz
- **Sync**: re-fetches order state from Skroutz API on demand
- Optionally auto-creates a linked Odoo Sale Order on acceptance

## Configuration

Go to **Settings → Skroutz**:

| Setting | Description |
|---|---|
| Feed Token | Optional secret appended to feed URL (`?token=…`) |
| Default Availability | Availability label for 0-stock products |
| Include 0-stock products | Keep out-of-stock products in the feed |
| API Token | Bearer token from Skroutz merchant panel |
| Webhook Secret | Optional token embedded in the webhook URL path |
| Auto-create Sale Order | Create a Sale Order automatically when an order is accepted |

### Webhook URL
Register the full URL in your Skroutz merchant panel:
- Without secret: `https://yourdomain.com/skroutz/webhook`
- With secret: `https://yourdomain.com/skroutz/webhook/YOUR_SECRET`

### Public Feed (Docker / multi-DB)
Set `db_name` in `odoo.conf` (or the container's config) so the public feed route resolves without a database selector:
```ini
db_name = your_database_name
```

## Product Setup

On each product's **Skroutz** tab:
- **Feed Status** group: set the **MPN** here (editable), EAN and category path shown for reference
- **Optional Skroutz Fields**: size, color, season, size fit, outlet, per-product shipping cost

The product is included in the feed when it is **published on the website** and has a non-empty **MPN**.

## Optional Integration

If the [`l10n_gr_partner`](https://github.com/) addon is installed, the street number from the shipping address is written to the partner's `arithmos_odou` field instead of being concatenated into the street name.

## Changelog

### 1.7
- Dispatch with no tracking codes at all no longer raises (`list(None)`).
- Dropped `notify_by_email=False` from the order chatter post — Odoo 19 removed
  the argument, so every notification raised instead of being posted.

### 1.6
- Skroutz menu moved from Website → eCommerce to Sales.
- «Create Sale Order» moved into the header, next to Accept / Reject / Sync.

### 1.5
- Manual «Create Sale Order» button replaces auto-creation on accept.
- Accept skips the wizard for standard orders (the API offers no pickup options
  for them); standard orders dispatch through `/dispatched`, FBS orders through
  `/tracking_details`.
- `fulfilled_by_skroutz` stored from the webhook payload; Origin column on the
  sale order list; public read access on `product.brand` for website visitors.
- `pickup_location` / `pickup_window` are Char — Skroutz uses string ids.

### 1.4
- Added dedicated `skroutz_mpn` field on products; `default_code` (Internal Reference) is no longer used as MPN

### 1.3
- Security: feed token uses `hmac.compare_digest` (timing-safe)
- Accept API sends `pickup_location`/`pickup_window` as integers
- Sale order creation is idempotent (no duplicate on double-submit)
- Sale order creation failure no longer rolls back the accepted state (savepoint)
- Fee amounts handle string values from API (e.g. `"2.50"`)
- Unknown Skroutz states logged as warning instead of silently ignored
- l10n_gr_partner detected via module install state
- Webhook line items not rebuilt on retry when payload unchanged
- Feed domain simplified; `include_zero` param comparison case-insensitive
- State map replaced with frozenset; name/street joins deduplicated

### 1.2
- Webhook auth changed from HMAC body signing to URL token
- Webhook returns HTTP 500 on error so Skroutz retries
- Datetime parsing fixed: timestamps converted to UTC
- Partner deduplication via Skroutz customer ID (`SKROUTZ-<id>` in partner ref)
- Order total includes Skroutz fees; fees stored in `payment_cost`
- Shipping recipient name populated from customer data
- Wizards restricted to Sales Managers
- Added couriers: Speedex, ELTA, Courier Center, Easy Mail, BOX NOW, UPS, TNT, FedEx
- Street number stored separately (`ship_street_number`)

### 1.1
- Fixed API base URL and endpoint paths
- Replaced OAuth2 with static Bearer token auth
- Accept wizard with live pickup location/window options from API
- Fixed reject payload (`rejection_reason_other`, no wrapper)
- Fixed dispatch: POST `/tracking_details` with courier + tracking code
- Fixed `skroutz_line_id` from Integer to Char
- API errors surface as readable `UserError`

### 1.0
- Initial public release

## License

LGPL-3 — © Efstathios Voulgaris <efstathiosvoulgaris@gmail.com>
