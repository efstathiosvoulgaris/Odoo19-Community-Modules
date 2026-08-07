# l10n_gr_partner — Greek partner fields (myDATA)

**Version:** 1.0 | **Odoo:** 19 | **License:** LGPL-3

Extends `res.partner` with the Greek commercial and tax fields the rest of the
localisation stack reads. It is the base every other module here depends on for
partner data — `l10n_gr_provider_base`, `aade_vat_lookup`, `l10n_gr_partner_pos`.

---

## Fields

| Field | Label | Notes |
|-------|-------|-------|
| `eponymia` | Επωνυμία | Legal name, distinct from the display name |
| `drastiriotita` | Δραστηριότητα / ΚΑΔ | |
| `legal_form` | Νομική Μορφή | Α.Ε., Ε.Π.Ε., Ι.Κ.Ε., Ο.Ε., Ε.Ε., Ατομική, Συνεταιρισμός, Άλλη |
| `doy` | Δ.Ο.Υ. | |
| `gemh` | ΓΕΜΗ | Printed on the Greek invoice forms |
| `mydata_entity_type` | Τύπος Οντότητας myDATA | Φυσικό / Νομικό / Δημόσιο |
| `branch_number` | Αριθμός Παραρτήματος | |
| `arithmos_odou` | Αριθμός (οδού) | A separate field inside the address widget |
| `kinito` | Κινητό | Odoo 19 removed `mobile` from `res.partner` |

---

## View changes

- **Form**: the Greek fields in two balanced columns above the tabs; «Αριθμός»
  embedded in the address widget with matching styling; «Κινητό» under
  «Σταθερό», same phone widget and a mobile icon.
- **List**: extra columns — Επωνυμία, Δραστηριότητα, ΔΟΥ, Αριθμός, Τ.Κ., Κινητό.

---

## Changelog

### 1.0
- Initial public release.
