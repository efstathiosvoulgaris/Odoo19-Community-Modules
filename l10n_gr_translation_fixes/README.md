# Greek Translation Fixes (l10n_gr_translation_fixes)

Curated corrections for the Greek (el_GR) translation of Odoo 19 Community,
packaged as a self-deploying module.

## The problem

The shipped Greek translation is partly missing and partly wrong — often
translated out of context:

| English | Shipped Greek | Corrected |
|---|---|---|
| Table (POS restaurant) | Πίνακας (database table!) | Τραπέζι |
| Future Receipts (warehouse) | Μελλοντικές Αποδείξεις | Μελλοντικές Παραλαβές |
| Outbound (payment) | Εξερχόμενη Κλήση (a phone call!) | Εξερχόμενη |
| Orders | Ταξινομήσεις (sortings) | Παραγγελίες |
| Restrict price modifications to managers | (inverted meaning) | Τροποποίηση τιμών μόνο από διαχειριστές |
| Drop Shipping | Ακύρωση Αποστολής | Απευθείας Παράδοση σε Πελάτη |

Plus typos (Εικέτα, Δημσιουργήστε, Χωριτικότητα), Latin letters hidden inside
Greek words (Tιμολόγια, Aντιστοίχιση — they break search), and three different
renderings of the same concept (picking, replenishment, reconcile, backorder…).

This module bundles **~676 reviewed corrections across 9 modules**: `purchase`,
`sale`, `product`, `stock`, `account`, `point_of_sale`, `pos_restaurant`,
`base`, `web`.

## How it works

Odoo loads each module's `i18n_extra/el.po` **after** the shipped `i18n/el.po`,
and later entries win — for both code/JS translations and database model terms.
Code translations are looked up strictly per-module, so a separate addon cannot
override them directly; instead this module acts as a deployer:

- Corrections live inside the module as `fixes/<module>/el.po` (standard
  gettext PO files keyed by the English source text).
- On install and at **every registry load** (`_register_hook`) the files are
  copied into each target module's `i18n_extra/` directory — only for modules
  present in the addons path, only when missing or outdated. This makes the
  deployment **self-healing**: an Odoo core upgrade that wipes `i18n_extra` is
  repaired at the next server start.
- When the bundled fixes change (hash-tracked in `ir.config_parameter`),
  database model terms are reloaded automatically with overwrite for `el_GR`.

## Installation

1. Copy the module to your addons path (Windows, Linux and Docker all work —
   the deployer is pure Python).
2. Make sure the Greek language (el_GR) is installed on the database.
3. Install **Greek Translation Fixes** via Apps.
4. Restart the Odoo service once (code/JS translations are read at startup)
   and hard-refresh the browser.

- Odoo version: 19.0 (Community)
- Dependencies: `base` (corrections apply only to target modules that are
  actually installed)

### Docker note

In the official Odoo image the core addons under
`/usr/lib/python3/dist-packages/odoo/addons` are owned by **root**, while Odoo
runs as the `odoo` user — the deployer then logs
`cannot deploy translation fixes ... Permission denied` and nothing is applied.
Grant write access to the `i18n_extra` directories once, then restart:

```bash
docker exec -u root <odoo-container> bash -c \
  'for m in purchase sale product stock account point_of_sale pos_restaurant base web; do
     d=/usr/lib/python3/dist-packages/odoo/addons/$m/i18n_extra
     mkdir -p "$d" && chown odoo "$d"
   done'
docker restart <odoo-container>
```

On the next start the module deploys the files and reloads the database terms
automatically (look for `Greek translation fixes deployed for: ...` in the
logs). The directories persist as long as the container does; if you recreate
the container from the image, run the command again.

## Unified terminology

Table=Τραπέζι, Floor=Αίθουσα, Bill=Λογαριασμός Προμηθευτή, Order=Παραγγελία,
picking=Συλλογή, Package=Συσκευασία, replenishment=Αναπλήρωση,
reordering=Αναπαραγγελία, backorder=Εκκρεμής Παραγγελία, scrap=Απόρριψη,
reconcile=Συμφωνία, Journal Entry=Λογιστική Εγγραφή, Draft=Πρόχειρο,
reversal=Αντιλογισμός, bank Statement=Κατάσταση, Point of Sale=Σημείο Πώλησης,
POS Session=Βάρδια. Context-sensitive: Receipt=Παραλαβή (warehouse) /
Απόδειξη (accounting & POS).

## Updating the fixes

Replace or edit the PO files under `fixes/<module>/` and upgrade the module
(or simply restart the server — the deployer detects the change). Entries whose
English source text no longer exists in a future Odoo version are ignored
harmlessly.
