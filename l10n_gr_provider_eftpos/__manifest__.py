# -*- coding: utf-8 -*-
{
    'name': 'Greece - E-Invoicing Provider (EFT/POS Α.1155)',
    'version': '1.0',
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
        'Phase 1 uses the manual terminal driver: the cashier charges the\n'
        'standalone terminal (the signature reaches it through its NSP) and\n'
        'types the transaction id back. NSP cloud drivers (Viva, Cardlink,\n'
        '...) can be added per terminal later.\n'
        '\n'
        'Changelog\n'
        '---------\n'
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
        'views/eft_views.xml',
    ],
    'installable': True,
    'auto_install': False,
}
