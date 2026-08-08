# -*- coding: utf-8 -*-
{
    'name': 'Greece - E-Invoicing Provider (Point of Sale)',
    'version': '1.9',
    'category': 'Accounting/Localizations',
    'summary': 'POS receipts (ΑΛΠ) and invoices (ΤΙΜ) through the e-invoicing provider',
    'description': (
        'Issues every Point of Sale order through the licensed e-invoicing\n'
        'provider (Υ.ΠΑ.Η.Ε.Σ.), riding the existing provider workflow.\n'
        '\n'
        'Every validated POS order becomes a posted invoice on the proper\n'
        'Greek journal and is transmitted synchronously:\n'
        '\n'
        '- ΑΛΠ (11.1) by default — with the selected client as partner, or\n'
        '  the walk-in retail partner when none is selected.\n'
        '- ΤΙΜ (1.1) when the cashier explicitly requests an invoice.\n'
        '- ΠΛΑ (11.4) for refunds of retail receipts.\n'
        '\n'
        'The printed receipt carries the legal markings (MARK,\n'
        'authentication code, provider QR) or the TF-2/TF-1 fallback notice;\n'
        'a failed transmission never blocks the sale — the document lands in\n'
        'the provider retry queue and the receipt says so.\n'
        '\n'
        'POS payment methods map to myDATA payment types (§8.12).\n'
        '\n'
        'Changelog\n'
        '---------\n'
        '1.9 — Κάθε νέο ταμείο αποκτά τρόπο πληρωμής «Μετρητά». Το Odoo\n'
        'δημιουργεί ημερολόγιο και τρόπο μετρητών μόνο όταν η εταιρεία δεν\n'
        'έχει ΚΑΝΕΝΑΝ τρόπο πληρωμής, και προσφέρει υπάρχοντα μόνο αν δεν τον\n'
        'έχει δεσμεύσει άλλο ταμείο· οι ελληνικοί τρόποι πληρωμής που σπέρνει\n'
        'το module ικανοποιούν τον πρώτο έλεγχο, οπότε το δεύτερο ταμείο\n'
        'δημιουργούνταν με όλες τις κάρτες και καμία επιλογή μετρητών — και\n'
        'χωρίς μετρητά δεν υπάρχει ούτε έλεγχος ταμείου (άνοιγμα/κλείσιμο).\n'
        'Ίδια αστοχία με την «Κάρτα-POS» της 1.4, σε άλλο κλάδο.\n'
        '\n'
        'Ο «Τύπος Πληρωμής myDATA» δηλώνεται πλέον ρητά σε κάθε τραπεζικό\n'
        'τρόπο πληρωμής: η Odoo βλέπει κάρτα, IRIS, Web Banking, επιταγή και\n'
        'έμβασμα ως ίδια, οπότε ένα κενό πεδίο κατέληγε σιωπηλά σε τύπο 7 —\n'
        'δήλωνε στην ΑΑΔΕ πληρωμή με κάρτα και ζητούσε υπογραφή Α.1155 από το\n'
        'τερματικό. Το κουμπί ρυθμίσεων πλέον ΔΙΟΡΘΩΝΕΙ τον τύπο στους\n'
        'τρόπους πληρωμής που δημιούργησε (όπως ήδη διορθώνει τα ημερολόγια)\n'
        'και αναφέρει όσους δεν έχουν δηλωμένο τύπο. Το ημερολόγιο δεν\n'
        'πειράζεται: είναι λογιστική επιλογή, δεν διαβιβάζεται στο myDATA.\n'
        '\n'
        '1.8 — Επιστροφή: το «Τιμολόγιο» ακολουθεί το αρχικό παραστατικό. Το\n'
        'Odoo ενεργοποιεί το to_invoice σε κάθε επιστροφή τιμολογημένης\n'
        'παραγγελίας και κλειδώνει το κουμπί — και επειδή κάθε παραγγελία\n'
        'μέσω παρόχου τιμολογείται, ΚΑΘΕ επιστροφή έφτανε ως ΤΙΜ: πήγαινε στο\n'
        'ημερολόγιο ΠΙΣΤ 5.1 αντί για ΠΛΠ 11.4 και απορριπτόταν επειδή ο\n'
        'πελάτης λιανικής δεν έχει ΑΦΜ. Το είδος του πιστωτικού καθορίζεται\n'
        'πλέον από το παραστατικό που ακυρώνει.\n'
        '\n'
        '1.7 — Per-till options in POS settings, every default reproducing the\n'
        'previous behaviour: what the till prints (legal document / receipt\n'
        'with ΜΑΡΚ / both), whether the «Τιμολόγιο» button is offered (a bar\n'
        'invoicing a company), and what a failed transmission costs (queue and\n'
        'continue / warn the cashier / refuse the sale). A ΤΙΜ now demands a\n'
        'partner with ΑΦΜ instead of silently falling back to the walk-in\n'
        'customer.\n'
        '\n'
        '1.6 — The till prints the LEGAL DOCUMENT, not an Odoo receipt: the\n'
        'posted account.move rendered on the journal\'s Greek form (ΑΛΠ 80mm,\n'
        'ΤΙΜ A4) with ΜΑΡΚ, provider QR and authentication code. The thermal\n'
        'receipt remains only where there is no document to print — an order\n'
        'that never reached the provider — and the restaurant «Λογαριασμός»\n'
        'now prints «ΔΕΝ ΑΠΟΤΕΛΕΙ ΦΟΡΟΛΟΓΙΚΟ ΣΤΟΙΧΕΙΟ».\n'
        '\n'
        '1.5 — The receipt markings block is gated on the till, not on the\n'
        'document state. A send that failed at validation left the state empty,\n'
        'which hid the whole block — including its own «ΔΕΝ ΔΙΑΒΙΒΑΣΤΗΚΕ»\n'
        'fallback — so the customer got a plain receipt indistinguishable from\n'
        'a legal one.\n'
        '\n'
        '1.4 — Seeds the card method («Κάρτα-POS», myDATA type 7) as well.\n'
        'Odoo creates its own only while the company has no bank-journal\n'
        'payment method at all, so seeding the Greek ones first suppressed it\n'
        'permanently — leaving tills with no card method, and the Α.1155\n'
        'signature flow with nothing to act on.\n'
        '\n'
        '1.0 — Phase A: ΑΛΠ/ΤΙΜ/ΠΛΑ issuance, synchronous send, receipt\n'
        'markings, payment type mapping. (Phase B: Α.1155 EFT signatures in\n'
        'the payment screen.)'
    ),
    'author': 'Efstathios Voulgaris',
    'support': 'efstathiosvoulgaris@gmail.com',
    'license': 'LGPL-3',
    'depends': [
        'point_of_sale',
        'l10n_gr_provider_base',
        'l10n_gr_provider_ilyda',
    ],
    'data': [
        'views/pos_views.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'l10n_gr_provider_pos/static/src/**/*',
        ],
    },
    'application': True,
    'installable': True,
    'auto_install': False,
}
