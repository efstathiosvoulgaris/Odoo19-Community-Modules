# -*- coding: utf-8 -*-
{
    "name": "Greek Partner Fields (myDATA)",
    "summary": "Ελληνικά πεδία επαφών: Επωνυμία, Δραστηριότητα, ΔΟΥ, ΓΕΜΗ, Νομική Μορφή, Αριθμός Οδού, Κινητό, τύπος myDATA, παράρτημα",
    "description": """
Greek Partner Fields (myDATA)
=============================
Επεκτείνει το μοντέλο res.partner με ελληνικά εμπορικά/φορολογικά πεδία:

* Επωνυμία (eponymia)
* Δραστηριότητα / ΚΑΔ (drastiriotita)
* Νομική Μορφή (Α.Ε., Ε.Π.Ε., Ι.Κ.Ε., Ο.Ε., Ε.Ε., Ατομική, Συνεταιρισμός, Άλλη)
* Δ.Ο.Υ. (doy)
* ΓΕΜΗ (gemh)
* Τύπος Οντότητας myDATA (Φυσικό / Νομικό / Δημόσιο)
* Αριθμός Παραρτήματος (branch_number)
* Αριθμός οδού ως ξεχωριστό πεδίο μέσα στο address widget (arithmos_odou)
* Κινητό τηλέφωνο (kinito) — η Odoo 19 αφαίρεσε το πεδίο mobile από το res.partner

Προσαρμογές προβολών:

* Φόρμα:

  - Ελληνικά πεδία σε δύο ισορροπημένες κολόνες πάνω από τις καρτέλες
  - «Αριθμός» οδού ενσωματωμένος στο address widget με ίδιο styling
  - «Κινητό» κάτω από το «Σταθερό» με icon κινητού, ίδιο widget (phone)

* Λίστα: επιπλέον στήλες (Επωνυμία, Δραστηριότητα, ΔΟΥ, Αριθμός, Τ.Κ., Κινητό)

Changelog
---------

* 1.0 — Initial public release.
""",
    "version": "1.0",
    "author": "Efstathios Voulgaris",
    "publisher": "Efstathios Voulgaris",
    "website": "https://github.com/efstathiosvoulgaris",
    "category": "Localization/Greece",
    "license": "LGPL-3",
    "depends": ["contacts", "l10n_gr"],
    "data": [
        "views/res_partner_views.xml",
    ],
    "images": ["static/description/icon.png"],
    "installable": True,
    "application": True,
    "auto_install": False,
}
