# -*- coding: utf-8 -*-
{
    'name': 'Greece - E-Invoicing Provider (EFT/POS Α.1155)',
    'version': '1.2',
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
