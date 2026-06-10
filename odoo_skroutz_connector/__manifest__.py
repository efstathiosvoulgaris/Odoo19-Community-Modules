# -*- coding: utf-8 -*-
{
    'name': 'Skroutz Connector',
    'version': '1.2',
    'category': 'eCommerce',
    'summary': 'Skroutz XML feed, order webhook and order management API',
    'description': (
        'Changelog\n'
        '---------\n'
        '* 1.2 — Webhook: removed HMAC signature check (Skroutz sends no signature header; '
        'it blocked all webhooks when a secret was set). Secret is now a URL token: /skroutz/webhook/<secret>.\n'
        '        Webhook failures now return HTTP 500 so Skroutz retries delivery.\n'
        '        Fixed datetime parsing: timestamps converted to UTC (were stored 2-3 h off).\n'
        '        Partner deduplication via Skroutz customer ID (stored in partner ref as SKROUTZ-<id>); '
        'the API exposes no customer email/phone.\n'
        '        Order total now includes Skroutz fees; payment_cost stores the fees total.\n'
        '        Shipping recipient name populated from customer data.\n'
        '        Wizards restricted to Sales Managers (matching skroutz.order write rights).\n'
        '        Added Speedex, ELTA, Courier Center, Easy Mail, BOX NOW, UPS, TNT, FedEx couriers.\n'
        '        Raw Data tab uses the "code" widget; feed URL preview reflects unsaved token.\n'
        '        Street number stored separately (ship_street_number); written to the partner\'s '
        'arithmos_odou field when l10n_gr_partner is installed.\n'
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
