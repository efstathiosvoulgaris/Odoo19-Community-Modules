# -*- coding: utf-8 -*-
{
    'name': 'Greece - E-Invoicing Provider (Restaurant Order Notes 8.6)',
    'version': '1.1',
    'category': 'Accounting/Localizations',
    'summary': 'Δελτίο Παραγγελίας Εστίασης (8.6) from the restaurant Point of Sale',
    'description': (
        'Transmits Δελτία Παραγγελίας Εστίασης (AADE type 8.6) for restaurant\n'
        'tables and closes them with the retail receipt.\n'
        '\n'
        'Every round the waiter sends to the kitchen becomes one 8.6 carrying\n'
        'the table number, the items and their VAT, classified as 1.95\n'
        '(Λοιπά Πληροφοριακά Στοιχεία Εσόδων). When the table is paid, the ΑΛΠ\n'
        'closes the open notes: it is transmitted with the MARKs of every note\n'
        'in multipleConnectedMarks and the mandatory «Συναλλαγές Εστίασης»\n'
        'flag (aadeSpecialInvoiceCategory 12).\n'
        '\n'
        'An order note is informational, not a document of value: it is stored\n'
        'in its own model and never creates an accounting entry — only the\n'
        'closing receipt does.\n'
        '\n'
        'Legal note: a note left unclosed for 24 hours obliges the provider to\n'
        'suspend transmission for the whole entity (Α.1138/2020 as amended by\n'
        'Α.1170/2023), so open notes are visible under the myDATA menu.\n'
        '\n'
        'Changelog\n'
        '---------\n'
        '1.1 — Cancellation, both routes of §4. Removing an already-sent item\n'
        'issues an «αρνητικό» note (rows with recType 7, priced from the note\n'
        'that transmitted them, so a deleted orderline is still credited);\n'
        'cancelling the order issues a «Καθολική Ακύρωση 8.6» — a zero-value\n'
        'note with totalCancelDeliveryOrders and the cancelled MARKs in\n'
        'multipleConnectedMarks. Same action on the back-office list for notes\n'
        'left open by an offline till.\n'
        '\n'
        '1.0 — Phase 1: issue 8.6 on send-to-kitchen, close the table with the\n'
        'ΑΛΠ carrying the connected marks.'
    ),
    'author': 'Efstathios Voulgaris',
    'support': 'efstathiosvoulgaris@gmail.com',
    'license': 'LGPL-3',
    'depends': [
        'l10n_gr_provider_pos',
        'pos_restaurant',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/catering_order_views.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'l10n_gr_provider_pos_restaurant/static/src/**/*',
        ],
    },
    'application': True,
    'installable': True,
    'auto_install': True,
}
