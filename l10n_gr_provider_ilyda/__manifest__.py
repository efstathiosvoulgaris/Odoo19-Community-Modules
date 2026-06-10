# -*- coding: utf-8 -*-
{
    'name': 'Greece - E-Invoicing Provider: ILYDA',
    'version': '1.1',
    'category': 'Accounting/Localizations',
    'summary': 'ILYDA (vs.gr) driver for the Greek e-invoicing provider base',
    'description': (
        'Driver implementing the ILYDA Y.PA.H.E.S. eInvoicing API (v1.0.6):\n'
        'POST /api/invoice (submit and mark via myDATA), POST /api/invoice/upload\n'
        '(upload the legal PDF), GET /api/invoice/status (B2G Peppol status).\n'
        '\n'
        'Authentication via X-Auth-Key header. Test endpoint: test.vs.gr.\n'
        'Payload is built from the myDATA data maintained by l10n_gr_edi\n'
        '(document type, income classifications, VAT categories).\n'
        '\n'
        'Changelog\n'
        '---------\n'
        '1.1 — Fixed VAT category: now derived from the tax rate exactly like\n'
        'l10n_gr_edi (24/13/6/17/9/4/0 to categories 1-7, no-tax 8); exemption\n'
        'category required only for genuine 0 percent lines. Series/serial now\n'
        'follow the l10n_gr_edi myDATA convention (INV/2026/00042 becomes\n'
        'INV_2026 + 00042), also in credit-note preceding references. B2G\n'
        'payload: projectReference from budget type+id, purchaseOrderReference,\n'
        'buyer Peppol routing address (9933:VAT), delivery details from the\n'
        'shipping address, CPV per line (BT-158, scheme STI) with validation.\n'
        '\n'
        '1.0 — Initial release: B2B/B2C/B2G submit, marking ingestion\n'
        '(MARK, verification hash, identifier, QR), PDF upload, B2G status\n'
        'polling, credit-note preceding invoice reference.'
    ),
    'author': 'Efstathios Voulgaris',
    'support': 'efstathiosvoulgaris@gmail.com',
    'license': 'LGPL-3',
    'depends': [
        'l10n_gr_provider_base',
    ],
    'data': [
        'views/res_config_settings_views.xml',
    ],
    'installable': True,
    'auto_install': False,
}
