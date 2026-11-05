{
    'name': 'ΕΡΓΑΝΗ — Ψηφιακή Κάρτα Εργασίας',
    'version': '2.1',
    'category': 'Human Resources',
    'summary': 'ΕΡΓΑΝΗ ΙΙ work card: QR gate at Odoo login, «Αποχώρηση», WRKCardSE sender',
    'description': (
        'The employee punches the ΕΡΓΑΝΗ ΙΙ digital work card through Odoo:\n'
        'after login a gate page asks him to scan his own card QR and records the\n'
        '«Προσέλευση»; «Αποχώρηση» in the top bar asks the card again, records\n'
        'the departure and logs him out of this browser. Cards are kept in an\n'
        'append-only, hash-chained log and sent by one cron (WRKCardSE), or\n'
        'only simulated until ΕΡΓΑΝΗ credentials exist. POS and API-key\n'
        'access are never gated. Design: ergani/DESIGN.md (v3.1).\n'
        '\n'
        'Changelog\n'
        '---------\n'
        '1.0 — Initial release.\n'
        '1.1 — Final-review fixes (token expiry, per-employee chain, frozen worker data, '
        'same-day open check-in, no card write ACL, logout of this browser only).\n'
        '1.2 — Weak PINs refused (the PIN also opens quick login); GDPR notice covers '
        'the camera and quick login.\n'
        '1.3 — Κινήσεις και έλεγχος (ergani/PLAN_1.3.md): «Κατάσταση κινήσεων» με φίλτρα σε δύο '
        'ομάδες («Χρειάζεται έλεγχος» χωρίς ανοχή, «Πληροφορία προσωπικού» με ανοχή), λίστα/pivot/'
        'PDF, απέναντι στο ωράριο εργασίας του Odoo (όχι έλεγχος συμμόρφωσης)· «Σήμερα» (kanban, '
        'μόνο υπεύθυνος)· «Αρχείο υποβολών» για κάθε κλήση στο ΕΡΓΑΝΗ (χωρίς κωδικούς/tokens/σώματα '
        'κάρτας)· αποδεικτικό PDF από το ΕΡΓΑΝΗ (λήψη από τον cron)· «Εμπρόθεσμη έως»· ημερομηνία '
        'επιβεβαίωσης ωραρίου με τον λογιστή.\n'
        '1.4 — ΕΡΓΑΝΗ → «Εργαζόμενοι»: λίστα με διακόπτη «Χτυπά κάρτα», σημερινή κατάσταση, στοιχεία '
        'ΕΡΓΑΝΗ· «Συγχρονισμός από ΕΡΓΑΝΗ» (EX_BASE_04, αντιστοίχιση μόνο με ΑΦΜ, επιβεβαίωση πριν από '
        'κάθε αλλαγή, χωρίς αποδοχές/προσωπικά)· παραρτήματα από ΕΡΓΑΝΗ (EX_BASE_02) και παράρτημα ανά '
        'εργαζόμενο στην κάρτα.\n'
        '1.5 — Ενιαίος Οδηγός 01.01.2024 (ergani/GAPS_ENIAIOS_ODIGOS.md): αιτιολογίες εκπρόθεσμης από '
        'το ΕΡΓΑΝΗ (EX_BASE_03 WorkCardDelayReason) σε λίστα· ευέλικτη προσέλευση/διάλειμμα ανά '
        'εργαζόμενο, η ευελιξία μετρά στην κατάσταση κινήσεων· νυχτερινή αποχώρηση έως 11:00 (ρύθμιση)· '
        'f_aitiologia κενό αντί null (Card_v1.xsd)· όρια 50/30 χαρακτήρων στα ονόματα· ειδοποίηση '
        'Επιθεώρησης και στη λήξη της αδυναμίας.\n'
        '2.0 — Αλλαγές ωραρίου από το Odoo (ergani/PLAN_2.0.md): δήλωση WTODaily (άλλη ώρα, σπαστό, '
        'τηλεργασία, ρεπό, μη εργασία) για έναν ή πολλούς εργαζόμενους/μέρες, «Παράταση σήμερα», έλεγχος '
        'προθεσμίας (πριν την έναρξη· μετά μόνο επέκταση) στο κουμπί και ξανά πριν το POST, ίδιος cron και '
        'αρχείο υποβολών· η τελευταία υποβληθείσα αλλαγή γίνεται ωράριο αναφοράς της κατάστασης κινήσεων· '
        'λίστα υπηρεσιών/υποβολών του ΕΡΓΑΝΗ στη «Δοκιμή σύνδεσης»· τύποι από EX_BASE_03 WorkTimeType. '
        'Άδειες: μοντέλο έτοιμο, υποβολή κλειδωμένη έως το trial.\n'
        '2.1 — Κάρτα QR αντί για PIN: η σελίδα χτυπήματος δέχεται μόνο την κάρτα του συνδεδεμένου '
        'εργαζομένου (σκάνερ ή κάμερα)· το QR είναι το Badge ID του Odoo, που δέχεται και η γρήγορη '
        'σύνδεση χωρίς να εξαρτάται κανένα από το άλλο. Εκτύπωση/νέα κάρτα από την καρτέλα ΕΡΓΑΝΗ. '
        'Το PIN ΕΡΓΑΝΗ καταργήθηκε· το κείμενο της γρήγορης σύνδεσης έφυγε από την ενημέρωση GDPR.'
    ),
    'author': 'Efstathios Voulgaris',
    'support': 'efstathiosvoulgaris@gmail.com',
    'license': 'LGPL-3',
    'depends': ['hr', 'web', 'mail'],
    'data': [
        'security/ergani_security.xml',
        'security/ir.model.access.csv',
        'data/ir_cron.xml',
        'data/ergani_worktime_type_data.xml',
        'views/ergani_card_views.xml',
        'views/ergani_submission_views.xml',
        'views/ergani_status_views.xml',
        'report/ergani_status_report.xml',
        'report/ergani_card_report.xml',
        'views/hr_employee_views.xml',
        'views/ergani_employee_views.xml',
        'views/ergani_wto_views.xml',
        'views/res_config_settings_views.xml',
        'views/gate_templates.xml',
        'views/ergani_menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'l10n_gr_ergani_card/static/src/systray/**/*',
        ],
    },
    'installable': True,
    'application': True,
}
