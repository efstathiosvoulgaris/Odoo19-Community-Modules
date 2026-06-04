# -*- coding: utf-8 -*-
{
    "name": "Greek Partner Fields – POS bridge",
    "summary": "Φόρτωση και αναζήτηση ελληνικών πεδίων (Επωνυμία, Κινητό, ΔΟΥ, Δραστηριότητα) στο POS",
    "description": """
Greek Partner Fields – POS bridge
=================================
Bridge module που ενσωματώνει τα πεδία του ``l10n_gr_partner`` στην
Εντατική Λιανική (Point of Sale):

* Επεκτείνει το ``_load_pos_data_fields`` για να φορτώνονται στη
  μνήμη του POS: ``eponymia``, ``kinito``, ``doy``, ``drastiriotita``.
* Επεκτείνει την client-side αναζήτηση πελατών ώστε να βρίσκει
  αποτελέσματα και βάσει αυτών των πεδίων (συμπεριλαμβανομένου του
  κινητού).
* Επεκτείνει την server-side αναζήτηση (``search_fields``) ώστε όταν
  ο χρήστης πληκτρολογεί όρο που δεν βρίσκεται στους ήδη φορτωμένους
  πελάτες, ο διακομιστής να ψάχνει και στα ελληνικά πεδία.

Εγκαθίσταται αυτόματα όταν είναι εγκατεστημένα και τα δύο
``l10n_gr_partner`` και ``point_of_sale``.

Changelog
---------
* 1.0 — Initial public release.
""",
    "version": "1.0",
    "author": "Efstathios Voulgaris",
    "publisher": "Efstathios Voulgaris",
    "category": "Localization/Greece",
    "license": "LGPL-3",
    "depends": ["l10n_gr_partner", "point_of_sale"],
    "assets": {
        "point_of_sale._assets_pos": [
            "l10n_gr_partner_pos/static/src/models/res_partner.js",
            "l10n_gr_partner_pos/static/src/screens/partner_list.js",
            "l10n_gr_partner_pos/static/src/screens/partner_line.xml",
        ],
    },
    "images": ["static/description/icon.png"],
    "installable": True,
    "application": True,
    "auto_install": True,
}
