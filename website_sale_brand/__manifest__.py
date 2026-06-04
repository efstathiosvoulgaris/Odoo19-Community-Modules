# -*- coding: utf-8 -*-
{
    'name': 'Website Sale Brands',
    'version': '1.0',
    'category': 'Website/eCommerce',
    'summary': 'Adds Brands to products with image, website page, shop filter and import support',
    'description': 'Initial public release.\n\nChangelog\n---------\n* 1.0 — Initial public release.',
    'author': 'Efstathios Voulgaris',
    'publisher': 'Efstathios Voulgaris',
    'support': 'efstathiosvoulgaris@gmail.com',
    'license': 'LGPL-3',
    'depends': [
        'website_sale',
        'stock',
        'base_import',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/product_brand_views.xml',
        'views/product_template_views.xml',
        'views/website_sale_brand_templates.xml',
        'views/website_sale_brand_menus.xml',
        'data/data.xml',
    ],
    'images': ['static/description/icon.png'],
    'installable': True,
    'application': True,
    'auto_install': False,
}
