# -*- coding: utf-8 -*-
{
    'name': 'Purchase: Create Bill button',
    'version': '1.0',
    'category': 'Inventory/Purchase',
    'summary': 'Restore the Create Bill button on the purchase order form (removed in Odoo 19)',
    'description': (
        'Odoo 19 removed the "Create Bill" button from the purchase order form, '
        'leaving only the "Upload Bill" digitization widget. This module restores '
        'a one-click Create Bill button next to Upload Bill. It calls the same '
        'standard action (action_create_invoice) and appears only when the order '
        'has something billable (invoice status "to invoice"), for users with '
        'billing access rights. Greek translation included.\n\n'
        'Changelog\n'
        '---------\n'
        '* 1.0 — Initial release.'
    ),
    'author': 'Efstathios Voulgaris',
    'publisher': 'Efstathios Voulgaris',
    'support': 'efstathiosvoulgaris@gmail.com',
    'license': 'LGPL-3',
    'depends': ['purchase'],
    'data': [
        'views/purchase_order_views.xml',
    ],
    'installable': True,
    'auto_install': False,
}
