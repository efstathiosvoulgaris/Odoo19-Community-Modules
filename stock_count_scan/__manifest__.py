# -*- coding: utf-8 -*-
{
    'name': 'Απογραφή με σκανάρισμα',
    'version': '1.0',
    'category': 'Inventory/Inventory',
    'summary': 'Full stock count with a barcode gun: +1 per scan, accounting date, unscanned items to 0',
    'description': (
        'A count session for one location (and its sub-locations) with an accounting date '
        '(e.g. 31/12). Several PCs scan at the same time; every scan adds 1. Closing the '
        'session sets every product to what was scanned and everything not scanned to 0, '
        'with stock moves dated at the end of the accounting date. Counting may happen '
        'after that date while selling: each product is compared with its stock at the '
        'moment it was last scanned. Lot/serial products are left to Physical Inventory.\n\n'
        'Changelog\n'
        '---------\n'
        '* 1.0 — First version.'
    ),
    'author': 'Efstathios Voulgaris',
    'publisher': 'Efstathios Voulgaris',
    'support': 'efstathiosvoulgaris@gmail.com',
    'license': 'LGPL-3',
    'depends': ['stock', 'barcodes', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'security/security.xml',
        'views/stock_count_session_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'stock_count_scan/static/src/count_scan.js',
            'stock_count_scan/static/src/count_scan.xml',
        ],
    },
    'installable': True,
    'application': False,
}
