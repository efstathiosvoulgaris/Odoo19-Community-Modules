# -*- coding: utf-8 -*-
{
    'name': 'Skroutz Connector',
    'version': '1.1',
    'category': 'eCommerce',
    'summary': 'Skroutz XML feed, order webhook and order management API',
    'description': (
        'Changelog\n'
        '---------\n'
        '* 1.1 — Fixed API base URL and endpoint paths (api.skroutz.gr/merchants/ecommerce/orders).\n'
        '        Replaced OAuth2 client_credentials flow with static Bearer token auth.\n'
        '        Added Accept wizard with live pickup_location/pickup_window options from API.\n'
        '        Fixed reject payload to use rejection_reason_other (no order wrapper).\n'
        '        Fixed dispatch endpoint: POST /tracking_details with courier + tracking_code (FBM only).\n'
        '        Added courier Selection field to ship wizard.\n'
        '        Fixed skroutz_line_id from Integer to Char (Skroutz uses string IDs).\n'
        '        Added skroutz_size field on product.template for fashion/footwear feed.\n'
        '        XML feed: skip <ean> when barcode empty, description fallback to product name.\n'
        '        API errors now surface as readable UserError with Skroutz response body.\n'
        '        Order code field editable on new records (readonly after save).\n'
        '* 1.0 — Initial public release.'
    ),
    'author': 'Efstathios Voulgaris',
    'publisher': 'Efstathios Voulgaris',
    'support': 'efstathiosvoulgaris@gmail.com',
    'license': 'LGPL-3',
    'application': True,
    'depends': [
        'mail',
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
        'views/skroutz_order_views.xml',
        'views/skroutz_accept_wizard_views.xml',
        'views/skroutz_reject_wizard_views.xml',
        'views/skroutz_ship_wizard_views.xml',
        'views/skroutz_menus.xml',
    ],
    'images': ['static/description/icon.png'],
    'installable': True,
    'auto_install': False,
}
