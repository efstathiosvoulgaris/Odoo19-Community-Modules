# -*- coding: utf-8 -*-
{
    'name': 'Skroutz Connector',
    'version': '1.0',
    'category': 'eCommerce',
    'summary': 'Skroutz XML feed, order webhook and order management API',
    'description': 'Initial public release.\n\nChangelog\n---------\n* 1.0 — Initial public release.',
    'author': 'Efstathios Voulgaris',
    'publisher': 'Efstathios Voulgaris',
    'support': 'efstathiosvoulgaris@gmail.com',
    'license': 'LGPL-3',
    'application': True,
    'depends': [
        'product',
        'stock',
        'sale',
        'website_sale',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/res_config_data.xml',
        'views/res_config_settings_views.xml',
        'views/product_template_views.xml',
        'views/skroutz_menus.xml',
    ],
    'images': ['static/description/icon.png'],
    'installable': True,
    'auto_install': False,
}
