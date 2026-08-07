# -*- coding: utf-8 -*-
{
    "name": "AADE VAT Lookup",
    "summary": "Άντληση στοιχείων επιχείρησης από την ΑΑΔΕ μέσω ΑΦΜ (RgWsPublic2)",
    "description": """
AADE VAT Lookup
===============
Προσθέτει κουμπί δίπλα στο πεδίο ΑΦΜ στις επαφές το οποίο καλεί τη
διαδικτυακή υπηρεσία της ΑΑΔΕ «Αναζήτηση Βασικών Στοιχείων Μητρώου
Επιχειρήσεων» (RgWsPublic2) και συμπληρώνει αυτόματα:

* Επωνυμία / Διακριτικός τίτλος (`name`, `eponymia`)
* ΔΟΥ (`doy`)
* Διεύθυνση: Οδός, Αριθμός, Τ.Κ., Πόλη
* Κύρια δραστηριότητα / ΚΑΔ (`drastiriotita`)
* Τύπος οντότητας myDATA — Φυσικό/Νομικό πρόσωπο (`mydata_entity_type`)
* Νομική μορφή — fuzzy matching από το `legal_status_descr` (`legal_form`)
* Χώρα → Ελλάδα
* `is_company = True`

Λειτουργικά χαρακτηριστικά:

* Το κουμπί εμφανίζεται μόνο όταν η χώρα είναι Ελλάδα ή κενή.
* Δουλεύει και σε **νέες, μη αποθηκευμένες** επαφές. Δεν απαιτείται
  να έχει συμπληρωθεί το «Όνομα» ή το save πριν την κλήση — η ενημέρωση
  των πεδίων γίνεται client-side μέσω custom Owl widget.
* Αν ο ΑΦΜ είναι ανενεργός στην ΑΑΔΕ, εμφανίζεται προειδοποίηση.
* Αν επιστραφεί σφάλμα από την υπηρεσία (π.χ. λάθος ΑΦΜ, λάθος
  credentials, υπέρβαση ορίου κλήσεων), εμφανίζεται user-friendly
  μήνυμα.
* Τα credentials TaxisNet ρυθμίζονται **ανά εταιρεία** στις Ρυθμίσεις
  (Settings → AADE VAT Lookup).
* Το ΑΦΜ αποθηκεύεται ως 9 ψηφία χωρίς prefix «EL» — συμβατό με myDATA
  και άλλα ελληνικά ERP.

Τεχνικές λεπτομέρειες:

* Endpoint: `https://www1.gsis.gr/wsaade/RgWsPublic2/RgWsPublic2`
* Πρωτόκολλο: SOAP 1.2 με WS-Security UsernameToken
* Δεν εισάγει εξωτερικές εξαρτήσεις (requests + lxml είναι ήδη
  εξαρτήσεις του Odoo)

Changelog
---------
* 1.1 — Τα credentials και ο ΑΦΜ περνούν από XML escaping πριν μπουν στο
  SOAP envelope· ένας χαρακτήρας `&` στον κωδικό TaxisNet χαλούσε το αίτημα.
* 1.0 — Initial public release.
""",
    "version": "1.1",
    "author": "Efstathios Voulgaris",
    "publisher": "Efstathios Voulgaris",
    "category": "Localization/Greece",
    "license": "LGPL-3",
    "depends": ["l10n_gr_partner"],
    "data": [
        "views/res_config_settings_views.xml",
        "views/res_partner_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "aade_vat_lookup/static/src/aade_lookup_button.js",
            "aade_vat_lookup/static/src/aade_lookup_button.xml",
        ],
        "point_of_sale._assets_pos": [
            "aade_vat_lookup/static/src/aade_lookup_button.js",
            "aade_vat_lookup/static/src/aade_lookup_button.xml",
        ],
    },
    "images": ["static/description/icon.png"],
    "installable": True,
    "application": True,
    "auto_install": False,
}
