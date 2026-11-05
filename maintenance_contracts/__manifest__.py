{
    'name': 'Συμβόλαια Συντήρησης',
    'version': '1.0',
    'category': 'Sales',
    'summary': 'Yearly maintenance contracts: expiry reminders, renewal, draft invoice',
    'description': (
        'Maintenance contracts with customers: start / end (one year by\n'
        'default), amount, responsible employee, notes and the signed PDF in\n'
        'the chatter. Every morning a cron gives the responsible a «Ανανέωση\n'
        'συμβολαίου» activity N days before the end (once per contract).\n'
        '«Ανανέωση» creates next year\'s contract; «Δημιουργία Προτιμολογίου»\n'
        'creates a DRAFT customer invoice in the configured journal, which\n'
        'the user confirms — nothing reaches myDATA before that.\n'
        '\n'
        'Changelog\n'
        '---------\n'
        '1.0 — Initial release.'
    ),
    'author': 'Efstathios Voulgaris',
    'support': 'efstathiosvoulgaris@gmail.com',
    'license': 'LGPL-3',
    'depends': ['account', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'data/service_contract_data.xml',
        'views/service_contract_views.xml',
        'views/res_partner_views.xml',
        'views/res_config_settings_views.xml',
        'views/service_contract_menus.xml',
    ],
    'installable': True,
    'application': True,
}
