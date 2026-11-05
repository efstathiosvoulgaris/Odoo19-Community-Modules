# -*- coding: utf-8 -*-
{
    'name': 'Odoo 19: Μικρές Διορθώσεις (QoL)',
    'version': '1.6',
    'category': 'Productivity',
    'summary': 'Small quality-of-life fixes for Odoo 19, always on',
    'description': (
        'A collection of small, independent fixes for things Odoo 19 removed '
        'or made awkward. No settings: every fix is always on. One file per '
        'area under views/ (and models/ when Python is needed); each fix is '
        'listed in README.md.\n\n'
        'Changelog\n'
        '---------\n'
        '* 1.0 — Create Bill button on the purchase order (moved from '
        'purchase_create_bill_button 1.0).\n'
        '* 1.1 — Vendor Reference column shown by default in the purchase '
        'order lists.\n'
        '* 1.2 — Viber button next to the contact mobile.\n'
        '* 1.3 — Eshop follows stock: products with stock are published, without stock withdrawn.\n'
        '* 1.4 — Contacts found by mobile or phone in every contact field.\n'
        '* 1.5 — The eshop cron is noupdate: an upgrade no longer switches it off.\n'
        '* 1.6 — Listed as an application (own icon), so Apps shows it without '
        'clearing the «Apps» filter. No menu: the fixes live in the screens they fix.'
    ),
    'author': 'Efstathios Voulgaris',
    'publisher': 'Efstathios Voulgaris',
    'support': 'efstathiosvoulgaris@gmail.com',
    'license': 'LGPL-3',
    'depends': ['purchase', 'l10n_gr_partner', 'stock', 'website_sale'],
    'data': [
        'views/purchase_order_views.xml',
        'views/purchase_order_list_views.xml',
        'views/res_partner_views.xml',
        'views/product_template_views.xml',
        'data/ir_cron.xml',
    ],
    'assets': {
        'web.assets_backend': ['qol_fixes/static/src/open_external_url.js'],
    },
    'images': ['static/description/icon.png'],
    'application': True,
    'installable': True,
    'auto_install': False,
}
