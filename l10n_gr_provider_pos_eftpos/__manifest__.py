# -*- coding: utf-8 -*-
{
    'name': 'Greece - E-Invoicing Provider (POS EFT/POS Α.1155)',
    'version': '1.0',
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
        'Phase 1: manual terminal driver (cashier types the transaction id).\n'
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
    'installable': True,
    'auto_install': True,
}
