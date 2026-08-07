# -*- coding: utf-8 -*-
{
    'name': 'Greece - E-Invoicing Provider (POS EFT/POS Α.1155)',
    'version': '1.5',
    'category': 'Accounting/Localizations',
    'summary': 'Card-terminal payment signatures (Α.1155) inside the Point of Sale',
    'description': (
        'Bridges the Α.1155 EFT/POS signature flow into the Point of Sale.\n'
        '\n'
        'When the cashier pays a POS order with a card method, the software\n'
        'requests the provider signature for the amount, the cashier charges\n'
        'the terminal and types the transaction id back, and the order is\n'
        'transmitted as an ΑΛΠ/ΤΙΜ carrying the type-7 payment with its\n'
        'signature and transactionId — the POS equivalent of the backend\n'
        'eftpos payment window.\n'
        '\n'
        'Terminals wired to the MegEftPos Driver are charged by the software\n'
        'itself and the transaction id comes back automatically; standalone\n'
        'terminals keep the manual flow, where the cashier charges the machine\n'
        'and types the id. A customer paying the IRIS QR on the terminal is\n'
        'the same EFT/POS transaction as a card and transmits as myDATA type 7;\n'
        'IRIS direct (type 8, no terminal) is outside Α.1155 and untouched.\n'
        '\n'
        'A charge that is not followed by a validated order is given back: the\n'
        'terminal is voided and the signature released when a later payment\n'
        'fails, when validation is abandoned, or when the cashier removes a\n'
        'charged line — which now asks first instead of dropping it silently.\n'
        '\n'
        'Returns are signed too: §5.3 makes signature and transactionId\n'
        'mandatory on every type-7 payment line, credit documents included, so\n'
        'a refund to card takes its own signature against the ΠΛΠ (11.4) or\n'
        'ΠΙΣΤ (5.1) series. The refund itself is made on the terminal by the\n'
        'cashier, who types the transaction id back.\n'
        '\n'
        'Two per-till options (POS settings → Πάροχος myDATA): «Υποχρεωτική\n'
        'Υπογραφή Α.1155» refuses a card sale the terminal did not answer for,\n'
        'instead of accepting a hand-typed transaction id; «Μέγιστες Δόσεις»\n'
        'asks the cashier for δόσεις before the charge (0/1 = never asked).\n'
        '\n'
        'Auto-install when both the POS provider and the EFT/POS modules are\n'
        'present.'
    ),
    'author': 'Efstathios Voulgaris',
    'support': 'efstathiosvoulgaris@gmail.com',
    'license': 'LGPL-3',
    'depends': [
        'l10n_gr_provider_pos',
        'l10n_gr_provider_eftpos',
    ],
    'data': [
        'views/pos_config_views.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'l10n_gr_provider_pos_eftpos/static/src/**/*',
        ],
    },
    'application': True,
    'installable': True,
    'auto_install': True,
}
