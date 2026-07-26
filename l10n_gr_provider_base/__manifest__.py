# -*- coding: utf-8 -*-
{
    'name': 'Greece - E-Invoicing Provider (Base)',
    'version': '2.7',
    'category': 'Accounting/Localizations',
    'summary': 'Issue invoices through a licensed Greek e-invoicing provider (Y.PA.H.E.S.)',
    'description': (
        'Provider-agnostic base for issuing documents through a licensed Greek\n'
        'e-invoicing provider, as required by the 2026 B2B e-invoicing mandate.\n'
        '\n'
        'Adds to invoices: MARK, verification hash (authentication string),\n'
        'invoice identifier, provider QR code, submission state and retry queue.\n'
        'Suppresses the l10n_gr_edi ERP-channel transmission for documents routed\n'
        'through the provider (one channel per document).\n'
        '\n'
        'A driver module (e.g. l10n_gr_provider_ilyda) implements the actual API.\n'
        '\n'
        'Changelog\n'
        '---------\n'
        '2.7 — Journal setup hardened: Odoo translates the sales journal\n'
        'code «INV» to «ΤΙΜ» in Greek, silently taking the code the 1.1\n'
        'journal needs — the chart journal is now moved to «ΠΩΛ» and left\n'
        'otherwise untouched. Journals are created after the chart loads\n'
        '(they used to be rewritten by the chart loader), carry an explicit\n'
        'sequence so the picker follows myDATA order, are repaired when\n'
        'their code or type drifts, and collisions are logged instead of\n'
        'passing in silence.\n'
        '\n'
        '2.6 — AADE measurement units (§8.13) on uom.uom, stamped on the\n'
        'standard units by the settings button; Επισήμανση (§8.15) on\n'
        'invoice lines for Εκκαθάριση Πωλήσεων Τρίτων; the «Παραστατικό»\n'
        'report binds its own paperformat instead of falling back to the\n'
        'company default.\n'
        '\n'
        '2.5 — Serial numbers print inline under the invoice line they\n'
        'belong to; invoice lines created off the onchange path (sale\n'
        'invoicing, imports, POS) derive their myDATA classification and\n'
        'cross-border 0%% tax at create.\n'
        '\n'
        '2.4 — The retry cron gives up on documents whose issue date has\n'
        'passed (AADE ER-30 makes them unacceptable) with a new «abandoned»\n'
        'state, while TF-1 offline documents keep retrying; GR A4 form with\n'
        'repeating header and footer, unbreakable totals block and page\n'
        'counter, plus the 80mm retail form.\n'
        '\n'
        '2.3 — 8.2 Ειδικό Στοιχείο Τέλους Διαμονής (ΤΔΙ): «Ειδικό Στοιχείο\n'
        '(ΤΔΙ)» button on marked invoices builds the fee document server-side\n'
        '(8.2 journal, correlation, zero line, category1_95, fee = fixed € ×\n'
        'nights from the stay document). Journal default for the property\'s\n'
        'fee category; 8.2 lines auto-zero price and VAT via the compute\n'
        'chain; per-night amount recomputed from category/correlation.\n'
        '\n'
        '2.2 — «Διαβιβάσεις» log under the myDATA menu: every provider-routed\n'
        'document in one list (state badge, MARK, send date, PDF-uploaded\n'
        'flag, error) with filters for pending / errors / PDF backlog and\n'
        'grouping by state, journal or month — month-end checking at a\n'
        'glance.\n'
        '\n'
        '2.1 — Consolidated «myDATA» menu in the Accounting top bar: all\n'
        'module screens and options (Ψηφιακή Διακίνηση, Προεπιλογές\n'
        'Χαρακτηρισμού, Οχήματα, Κλειδιά Offline QR, provider settings link)\n'
        'in one place instead of scattered through the stock configuration\n'
        'lists. Vehicles get their own management screen.\n'
        'Tax guards (admin-toggleable, default on): posting blocks with a\n'
        'clear error list on wrong-tax documents — line without VAT, tax\n'
        'outside the allowed set for the document type, 0%% without an\n'
        'exemption reason, missing myDATA classification — and on island-rate\n'
        'inconsistencies (17/9/4%% without the Aegean regime, 24/13/6%% with\n'
        'it). The Ρυθμίσεις myDATA submenu is visible to Accounting managers\n'
        'only.\n'
        'Τακτοποίηση Καταλόγου Φόρων (settings button): self-explanatory Greek\n'
        'tax names («24% Αγορές Αγαθών» / «24% Λήψη Υπηρεσιών» instead of the\n'
        'chart\'s cryptic G/S/IG suffixes) and archiving of the unused «EU\n'
        'Other» variants; internal tax matching switched from names to chart\n'
        'xmlids so renames are safe.\n'
        '\n'
        '2.0 — TF-1 offline QR (Α.1112/2025): offline signing keys\n'
        '(issue/verify/revoke via the provider), automatic fallback to a\n'
        'locally signed JWS QR when the provider is unreachable, new "offline"\n'
        'state with forced retries and 1-day deadline warning, offline notice\n'
        'on the PDF. Send button hidden while queued (TF-2).\n'
        '\n'
        '1.9 — Provider search & reconciliation: "Ανάκτηση από Πάροχο" action\n'
        'and myDATA UID field; duplicate guard looks a failed document up at\n'
        'the provider before any retry resend. New "queued" state for TF-2\n'
        '(provider accepted, AADE offline): the PDF prints the provider QR with\n'
        'a waiting notice, and the cron polls the queue until the MARK arrives.\n'
        '\n'
        '1.1 — Extended B2G per the national format: budget type and identifier\n'
        '(BT-11, sent as "type|id"), purchase order reference (BT-13), buyer\n'
        'reference (BT-10) auto-defaulted from the customer name and its AAHT\n'
        'code. New AAHT field on contacts (MAAHT registry code) and CPV code\n'
        'field on products (BT-158, scheme STI). View fixes: CPV placement on\n'
        'the product form, AAHT label and anchor on the contact form, BT-12 in\n'
        'the contract reference label.\n'
        '\n'
        '1.0 — Initial release: provider fields on account.move, send-on-demand\n'
        'plus cron retry queue, legal markings block on the invoice PDF,\n'
        'l10n_gr_edi suppression, B2G reference fields.'
    ),
    'author': 'Efstathios Voulgaris',
    'support': 'efstathiosvoulgaris@gmail.com',
    'license': 'LGPL-3',
    'depends': [
        'account',
        'purchase',
        'uom',
        'l10n_gr_edi',
        'l10n_gr_partner',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/account_journal_views.xml',
        'views/account_move_views.xml',
        'views/cls_default_views.xml',
        'views/offline_key_views.xml',
        'views/dispatch_views.xml',
        'views/suppress_l10n_gr_edi_views.xml',
        'views/res_partner_views.xml',
        'views/product_template_views.xml',
        'views/uom_uom_views.xml',
        'views/res_config_settings_views.xml',
        'report/report_invoice.xml',
        'report/report_gr_invoice.xml',
        'data/ir_cron.xml',
        'data/suppress_l10n_gr_edi.xml',
        'views/menus.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'application': True,
    'installable': True,
    'auto_install': False,
}
