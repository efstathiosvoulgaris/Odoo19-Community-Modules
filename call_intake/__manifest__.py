{
    'name': 'Αιτήματα Πελατών — Νέο Τηλεφώνημα',
    'version': '1.0',
    'category': 'Services/Project',
    'summary': 'Phone requests to the right employee in a few seconds',
    'description': (
        'A phone icon in the top bar opens «Νέο Τηλεφώνημα» from any screen:\n'
        'type the number, the caller is found among the contacts (or created),\n'
        'write what they want, pick the employee and the deadline. The request\n'
        'becomes a task in the «Αιτήματα Πελατών» project, visible to every\n'
        'employee; the assignee is notified by Odoo as with any task. The\n'
        'caller\'s open requests are shown before saving, to avoid duplicates.\n'
        '\n'
        'Changelog\n'
        '---------\n'
        '1.0 — Initial release.'
    ),
    'author': 'Efstathios Voulgaris',
    'support': 'efstathiosvoulgaris@gmail.com',
    'license': 'LGPL-3',
    'depends': ['project', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'data/call_intake_data.xml',
        'wizard/call_intake_wizard_views.xml',
        'views/res_config_settings_views.xml',
        'views/call_intake_menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'call_intake/static/src/js/call_intake_systray.js',
            'call_intake/static/src/xml/call_intake_systray.xml',
        ],
    },
    'installable': True,
    'application': True,
}
