{
    'name': 'ΔΙΑΣ RF – Κωδικοί Πληρωμής',
    'version': '1.0',
    'category': 'Accounting/Accounting',
    'summary': 'Κωδικοί πληρωμής RF (ΔΙΑΣ DCT Creditor) και αυτόματη καταχώρηση πληρωμών',
    'description': (
        'Port to Odoo 19 of lam_dias_rf (v13). DIAS DCT Creditor (DIAS-ORG02): RF codes on '
        'invoices, quotations/orders and a fixed code per customer; webhook /dias/online/<db> '
        '(DPG_ONRequest validates only, DPG_ON books); PNO files over the File Transfer REST API; '
        'automatic customer payments and reconciliation. Design: rf/DESIGN.md (v2).\n\n'
        'Changelog\n---------\n* 1.0 — First Odoo 19 version.'
    ),
    'author': 'Efstathios Voulgaris',
    'support': 'efstathiosvoulgaris@gmail.com',
    'license': 'LGPL-3',
    'depends': ['account', 'sale', 'mail', 'l10n_gr_provider_base', 'l10n_gr_provider_ilyda'],
    'external_dependencies': {'python': ['passlib', 'requests']},
    'data': [
        'security/ir.model.access.csv',
        'data/ir_cron.xml',
        'views/dias_views.xml',
        'views/document_views.xml',
        'views/res_config_settings_views.xml',
        'views/menus.xml',
        'report/report_templates.xml',
    ],
    'application': True,
    'installable': True,
}
