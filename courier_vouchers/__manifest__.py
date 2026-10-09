{
    'name': 'Courier Vouchers',
    'version': '1.4',
    'category': 'Inventory/Delivery',
    'summary': 'Courier vouchers from delivery orders or standalone',
    'description': (
        'Courier integrations: courier accounts, vouchers with the courier\n'
        'lifecycle (create, print, cancel, pickup list, tracking), from a\n'
        'delivery order or standalone to any contact. Each courier is one\n'
        'file inside this addon (models/courier_acs.py, ...).\n'
        '\n'
        'Changelog\n'
        '---------\n'
        '1.4 — Γενική Ταχυδρομική (Web API V2, SOAP): δημιουργία, εκτύπωση A4\n'
        '(Flyer), ακύρωση, «Οριστικοποίηση Ημέρας» (ClosePendingJobsByDate από\n'
        'την τελευταία οριστικοποίηση), παρακολούθηση, αντικαταβολή (ΑΜ),\n'
        'χρέωση παραλήπτη (ΧΠ), δοκιμαστικό περιβάλλον. Το τέλος ημέρας της\n'
        'βάσης δέχεται courier χωρίς έγγραφο και κλείνει όσα δηλώνει εκείνος.\n'
        '\n'
        '1.3 —Η φόρμα λογαριασμού δείχνει μόνο τα πεδία του επιλεγμένου\n'
        'courier: κοινά μένουν όνομα, courier, εταιρεία, αποστολέας· οι\n'
        'καρτέλες «Σύνδεση» και «Προεπιλογές Αποστολής» γεμίζουν ανά courier\n'
        '(ACS: βάρος, χρέωση, λίστα παραλαβής· BOX NOW: μέγεθος θυρίδας, βάρος).\n'
        '\n'
        '1.2 —BOX NOW (Partner API, OAuth): παράδοση σε locker από AnyAPM\n'
        '(τα δέματα τα αφήνετε εσείς σε οποιοδήποτε locker). Πίνακας lockers\n'
        '(κουμπί + εβδομαδιαίο cron), αυτόματη πρόταση του κοντινότερου locker\n'
        'στη διεύθυνση του παραλήπτη, μέγεθος θυρίδας, αντικαταβολή, ετικέτα\n'
        'PDF, ακύρωση, παρακολούθηση από την εκτύπωση (χωρίς λίστα\n'
        'παραλαβής). Sandbox. Τα στοιχεία διεύθυνσης ελέγχονται ανά courier.\n'
        '\n'
        '1.1 —Δική του εφαρμογή «Courier» στην αρχική (Vouchers,\n'
        'Διαμόρφωση → Ρυθμίσεις / Λογαριασμοί Courier) και σελίδα «Courier»\n'
        'στις Ρυθμίσεις με προεπιλεγμένο λογαριασμό. Τίποτα πλέον στο μενού\n'
        'της Αποθήκης. Χρέωση αποστολέα/παραλήπτη επιλέγεται σε κάθε voucher\n'
        '(ο λογαριασμός δίνει μόνο την προεπιλογή). Κουμπί «Έλεγχος Σύνδεσης»\n'
        'στον λογαριασμό: μόνο κλήσεις ανάγνωσης (ACS: περιοχή Τ.Κ. και\n'
        'τιμολόγηση), ελέγχει API key, στοιχεία χρήστη και Κωδικό Χρέωσης.\n'
        '\n'
        '1.0 — Initial release. ACS (ACS Web Services): create, A4 print,\n'
        'delete voucher, daily pickup list, tracking summary. Vouchers from\n'
        'a delivery order (tracking number into the delivery) or standalone;\n'
        'cash on delivery from the «Αντικαταβολή» box on the sale order.'
    ),
    'author': 'Efstathios Voulgaris',
    'support': 'efstathiosvoulgaris@gmail.com',
    'license': 'LGPL-3',
    'depends': ['stock_delivery', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_cron.xml',
        'views/courier_account_views.xml',
        'views/courier_acs_views.xml',
        'views/courier_voucher_views.xml',
        'views/stock_picking_views.xml',
        'views/sale_order_views.xml',
        'views/res_config_settings_views.xml',
        'views/courier_menus.xml',
        'views/courier_boxnow_views.xml',
        'views/courier_geniki_views.xml',
    ],
    'installable': True,
    'application': True,
}
