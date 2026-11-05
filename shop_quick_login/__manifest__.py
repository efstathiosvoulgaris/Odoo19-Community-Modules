{
    'name': 'Γρήγορη σύνδεση (PIN / κάρτα QR) και αποσύνδεση αδράνειας',
    'version': '1.2',
    'category': 'Hidden/Tools',
    'summary': 'Quick login with card + PIN on enrolled shop PCs, and idle logout',
    'description': (
        'Quick login on enrolled shop computers: pick your name or scan your QR card (Badge ID), then '
        'your quick-login PIN. Goes through Odoo\'s own authenticate() (session rotation, 2FA, cooldown). '
        'Idle logout after N minutes of inactivity in any Odoo tab, never while a POS tab is open. '
        'Design: quick_login/DESIGN.md (v2, security council).\n\n'
        'Changelog\n---------\n* 1.0 — First version.\n'
        '* 1.1 — «Νέα κάρτα QR» from the app menu; Access Rights managers excluded.\n'
        '* 1.2 — Independent of ERGANI: own PIN set by the administrator («Ορισμός PIN»), the QR card '
        'is the employee Badge ID (the same card ERGANI accepts); the old QL1 cards are gone. '
        'Existing ERGANI PINs are carried over once.'
    ),
    'author': 'Efstathios Voulgaris',
    'support': 'efstathiosvoulgaris@gmail.com',
    'license': 'LGPL-3',
    'depends': ['hr', 'web', 'mail', 'auth_totp', 'point_of_sale'],
    'external_dependencies': {'python': ['passlib']},
    'data': [
        'security/ir.model.access.csv',
        'data/ir_cron.xml',
        'report/card_report.xml',
        'views/login_templates.xml',
        'views/views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'shop_quick_login/static/src/idle/idle_service.js',
            'shop_quick_login/static/src/idle/idle.scss',
        ],
        'point_of_sale._assets_pos': [
            'shop_quick_login/static/src/pos/heartbeat.js',
        ],
    },
    'application': True,
    'installable': True,
}
