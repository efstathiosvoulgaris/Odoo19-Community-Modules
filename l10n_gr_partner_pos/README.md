# l10n_gr_partner_pos — Greek partner fields in the POS

**Version:** 1.0 | **Odoo:** 19 | **License:** LGPL-3

Bridge module: makes the `l10n_gr_partner` fields usable from the till.
Auto-installs when both `l10n_gr_partner` and `point_of_sale` are present.

---

## What it does

- **Loads** `eponymia`, `kinito`, `doy` and `drastiriotita` into POS memory
  (`_load_pos_data_fields`), so they can be displayed and searched offline.
- **Client-side search**: the customer list matches on those fields too — most
  usefully the mobile number, which is how staff actually look people up.
- **Server-side search** (`search_fields`): when the term matches nobody among
  the already-loaded customers, the server searches the Greek fields as well
  instead of coming back empty.

That is the whole module. Nothing is written, no field is added.

---

## Changelog

### 1.0
- Initial public release.
