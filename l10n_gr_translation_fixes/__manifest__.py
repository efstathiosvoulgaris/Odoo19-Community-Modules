# -*- coding: utf-8 -*-
{
    'name': 'Greek Translation Fixes',
    'version': '1.0',
    'category': 'Localization',
    'summary': 'Curated el_GR translation overrides, auto-deployed into core modules via i18n_extra',
    'description': (
        'The shipped Greek translation of Odoo 19 contains out-of-context '
        'mistranslations (Table rendered as database table, receipts as payment '
        'receipts in the warehouse, inverted meanings, Latin letters inside Greek '
        'words, typos) and inconsistent terminology. This module bundles ~676 '
        'reviewed corrections for 9 core modules (purchase, sale, product, stock, '
        'account, point_of_sale, pos_restaurant, base, web) as fixes/<module>/el.po '
        'files and deploys them into each module\'s i18n_extra/ directory, where '
        'Odoo loads them on top of the shipped i18n/el.po.\n\n'
        'Deployment is self-healing: files are re-copied at every registry load, '
        'so the fixes survive Odoo core upgrades that wipe i18n_extra. Database '
        'model terms are reloaded automatically whenever the bundled fixes change. '
        'Code/JS translations are read from the files at server start; restart '
        'the service after updating this module.\n\n'
        'Changelog\n'
        '---------\n'
        '* 1.0 — Initial release: 676 corrections across 9 modules; unified '
        'terminology (Table=Τραπέζι, Floor=Αίθουσα, Bill=Λογαριασμός, '
        'picking=Συλλογή, replenishment=Αναπλήρωση, reconcile=Συμφωνία, '
        'POS Session=Βάρδια, Point of Sale=Σημείο Πώλησης).'
    ),
    'author': 'Efstathios Voulgaris',
    'publisher': 'Efstathios Voulgaris',
    'support': 'efstathiosvoulgaris@gmail.com',
    'license': 'LGPL-3',
    'depends': ['base'],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'auto_install': False,
}
