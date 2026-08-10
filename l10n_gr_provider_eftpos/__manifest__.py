# -*- coding: utf-8 -*-
{
    'name': 'Greece - E-Invoicing Provider (EFT/POS Α.1155)',
    'version': '1.10',
    'category': 'Accounting/Localizations',
    'summary': 'Card-terminal payment signatures per Α.1155/2023 through the e-invoicing provider',
    'description': (
        'Α.1155/2023 interconnection of card terminals (EFT/POS) with the\n'
        'e-invoicing provider (Υ.ΠΑ.Η.Ε.Σ.).\n'
        '\n'
        'Terminal registry (terminalId + NSP protocol), provider payment\n'
        'signatures on card payments, and both legal flows:\n'
        '\n'
        '- Real-time: signature before issue, charge, then submit the\n'
        '  document with the type-7 payment carrying signature and\n'
        '  transactionId.\n'
        '- Retrograde: document already marked, signature by MARK, charge,\n'
        '  then sendPaymentMethods — stores the paymentMethodMark.\n'
        '\n'
        'Signature cancellation with the AADE reason codes.\n'
        '\n'
        'Terminals can be driven automatically through the ILYDA MegEftPos\n'
        'Driver — one local REST service covering every NSP (Cardlink, Viva,\n'
        'Mellon, ePay, Nexi, Worldline, Attica, EDPS, INSS). Odoo then charges\n'
        'the card itself and reads back the transaction id. Terminals without\n'
        'a driver protocol keep the manual flow: the cashier charges the\n'
        'standalone terminal and types the transaction id back.\n'
        '\n'
        'Changelog\n'
        '---------\n'
        '1.10 — Η διεύθυνση του MegEftPos Driver ορίζεται πλέον ΑΝΑ ΤΕΡΜΑΤΙΚΟ.\n'
        'Ο driver είναι υπηρεσία στο PC του ταμείου και η Odoo τον καλεί από\n'
        'τον server, όχι από τον browser — οπότε μία διεύθυνση ανά εταιρεία\n'
        'δούλευε μόνο σε εγκατάσταση με ΕΝΑ ταμείο και την Odoo στο ίδιο\n'
        'μηχάνημα. Με δεύτερο ταμείο, ή με την Odoo σε server, τα ταμεία\n'
        'μοιράζονταν αναγκαστικά τον ίδιο driver. Το πεδίο της εταιρείας\n'
        'παραμένει ως προεπιλογή, οπότε οι υπάρχουσες εγκαταστάσεις δεν\n'
        'αλλάζουν συμπεριφορά.\n'
        '\n'
        '1.9 — Odoo 19 dropped _sql_constraints, so the CHECK that keeps an EFT\n'
        'payment amount positive was never created in the database. Ported to\n'
        'models.Constraint.\n'
        '\n'
        '1.8 — Driver 2.1.10 leftovers: instalments (δόσεις) on the card\n'
        'charge, and Viva Cloud «ελεύθερο refund» — a credit note on a Viva\n'
        'terminal no longer needs the original charge.\n'
        '\n'
        '1.6 — Corrects 1.4: IRIS at an EFT/POS is a settlement mode inside the\n'
        'terminal transaction, so it transmits as myDATA type 7 like any card.\n'
        'Type 8 is IRIS direct, which never touches a terminal and is outside\n'
        'Α.1155. The payment method survives as a terminal preselection.\n'
        '\n'
        '1.5 — The signature now records what it was issued for, and a payment\n'
        'that exceeds it or whose document changed after signing is refused\n'
        "(Α.1155 §5.3). The terminal's paidAmount is recorded and adopted, so\n"
        'the amount transmitted to AADE is the one actually charged.\n'
        '\n'
        '1.4 — IRIS: the payment carries the requested payment method and\n'
        'honours what the terminal reports back. (This release also made IRIS\n'
        'transmit as myDATA type 8, which was wrong — see 1.6.) An expired\n'
        'provider signature can no longer be charged or transmitted (§5.3).\n'
        '\n'
        '1.3 — Driver 2.1.10: corrected the request field names tipAmount and\n'
        'bankAuthorizationCode (the v2.1.5 PDF misspells both, which broke\n'
        'tips and made Refund/Void fail), providerUid now carries the uidHash,\n'
        'signatureTimestamp is computed as UTC, Nexi SoftPOS Web ECR protocol,\n'
        'and optional Basic Auth against the REST wrapper.\n'
        '\n'
        '1.2 — MegEftPos Driver integration: automatic sale, refund on credit\n'
        'notes, void when a charged payment is cancelled, and recovery of\n'
        'interrupted transactions.\n'
        '\n'
        '1.0 — Initial release: terminals, EFT payments menu, payment window\n'
        'on the invoice, real-time and retrograde flows, signature\n'
        'cancellation.'
    ),
    'author': 'Efstathios Voulgaris',
    'support': 'efstathiosvoulgaris@gmail.com',
    'license': 'LGPL-3',
    'depends': [
        'l10n_gr_provider_base',
        'l10n_gr_provider_ilyda',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/res_config_settings_views.xml',
        'views/eft_views.xml',
        'views/pos_receipt_wizard_views.xml',
    ],
    'application': True,
    'installable': True,
    'auto_install': False,
}
