# -*- coding: utf-8 -*-
{
    'name': 'Greece - E-Invoicing Provider (Base)',
    'version': '1.6',
    'category': 'Accounting/Localizations',
    'summary': 'Issue invoices through a licensed Greek e-invoicing provider (Y.PA.H.E.S.)',
    'description': (
        'Provider-agnostic base for issuing documents through a licensed Greek\n'
        'e-invoicing provider, as required by the 2026 B2B e-invoicing mandate.\n'
        '\n'
        'Adds to invoices: MARK, verification hash (authentication string),\n'
        'invoice identifier, provider QR code, submission state and retry queue.\n'
        'Suppresses the l10n_gr_edi ERP-channel transmission for documents routed\n'
        'through the provider (one channel per document).\n'
        '\n'
        'A driver module (e.g. l10n_gr_provider_ilyda) implements the actual API.\n'
        '\n'
        'Changelog\n'
        '---------\n'
        '1.1 — Extended B2G per the national format: budget type and identifier\n'
        '(BT-11, sent as "type|id"), purchase order reference (BT-13), buyer\n'
        'reference (BT-10) auto-defaulted from the customer name and its AAHT\n'
        'code. New AAHT field on contacts (MAAHT registry code) and CPV code\n'
        'field on products (BT-158, scheme STI). View fixes: CPV placement on\n'
        'the product form, AAHT label and anchor on the contact form, BT-12 in\n'
        'the contract reference label.\n'
        '\n'
        '1.0 — Initial release: provider fields on account.move, send-on-demand\n'
        'plus cron retry queue, legal markings block on the invoice PDF,\n'
        'l10n_gr_edi suppression, B2G reference fields.'
    ),
    'author': 'Efstathios Voulgaris',
    'support': 'efstathiosvoulgaris@gmail.com',
    'license': 'LGPL-3',
    'depends': [
        'account',
        'l10n_gr_edi',
        'l10n_gr_partner',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/account_journal_views.xml',
        'views/account_move_views.xml',
        'views/cls_default_views.xml',
        'views/suppress_l10n_gr_edi_views.xml',
        'views/res_partner_views.xml',
        'views/product_template_views.xml',
        'views/res_config_settings_views.xml',
        'report/report_invoice.xml',
        'data/ir_cron.xml',
        'data/suppress_l10n_gr_edi.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'auto_install': False,
}
