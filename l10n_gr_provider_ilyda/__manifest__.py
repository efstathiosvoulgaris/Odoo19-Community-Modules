# -*- coding: utf-8 -*-
{
    'name': 'Greece - E-Invoicing Provider: ILYDA',
    'version': '2.4',
    'category': 'Accounting/Localizations',
    'summary': 'ILYDA (vs.gr) driver for the Greek e-invoicing provider base',
    'description': (
        'Driver implementing the ILYDA Y.PA.H.E.S. eInvoicing API (v1.0.6):\n'
        'POST /api/invoice (submit and mark via myDATA), POST /api/invoice/upload\n'
        '(upload the legal PDF), GET /api/invoice/status (B2G Peppol status).\n'
        '\n'
        'Authentication via X-Auth-Key header. Test endpoint: test.vs.gr.\n'
        'Payload is built from the myDATA data maintained by l10n_gr_edi\n'
        '(document type, income classifications, VAT categories).\n'
        '\n'
        'Changelog\n'
        '---------\n'
        '2.4 — A refund on the ΠΟΣΕ journal transmits as 8.5 instead of\n'
        'being turned into a 5.x credit note.\n'
        '\n'
        '2.3 — measurementUnit is the real unit of the line (§8.13) instead of a\n'
        'hardcoded 1, unmapped units going as 7 with their name and count;\n'
        '9.2 transmits the generic counterpart ΑΦΜ 000000000 and no longer\n'
        'demands a VAT on the partner; invoiceDetailType per line, with a\n'
        '1.5 blocked before sending unless both line kinds are present.\n'
        '\n'
        '2.2 — Retail refunds on the ΠΛΑ journal submit as 11.4.\n'
        '\n'
        '2.1 — 8.2 Ειδικό Στοιχείο Τέλους Διαμονής payload shape.\n'
        '\n'
        '2.0 — TF-1 offline QR: /api/offline-qr key lifecycle (issue, verify\n'
        'installation, revoke), connection failures on submit now raise a\n'
        'typed unreachable error that triggers the offline fallback, offline\n'
        'JWS payload built from the same sources as the submit payload.\n'
        'Recovered documents without a provider invoiceId get a chatter note\n'
        'that the PDF must be uploaded manually.\n'
        '\n'
        '1.9 — Search & reconciliation: UID lookups (by-uid, by-mark,\n'
        'by-authentication-code) and the TF-2 pending queue (pending/by-uid).\n'
        'Recovery operation adopts a MARK issued during a lost-response\n'
        'submission instead of resending (duplicate guard). TF-2 responses\n'
        '(MQ001/MQ002 + I9999/I0004) now store the identifier/QR and mark the\n'
        'document as queued instead of rejected; I0008 re-issues adopt the\n'
        'original marking. Local myDATA UID computation (SHA-1/ISO-8859-7)\n'
        'with a self-check against provider-returned identifiers.\n'
        '\n'
        '1.1 — Fixed VAT category: now derived from the tax rate exactly like\n'
        'l10n_gr_edi (24/13/6/17/9/4/0 to categories 1-7, no-tax 8); exemption\n'
        'category required only for genuine 0 percent lines. Series/serial now\n'
        'follow the l10n_gr_edi myDATA convention (INV/2026/00042 becomes\n'
        'INV_2026 + 00042), also in credit-note preceding references. B2G\n'
        'payload: projectReference from budget type+id, purchaseOrderReference,\n'
        'buyer Peppol routing address (9933:VAT), delivery details from the\n'
        'shipping address, CPV per line (BT-158, scheme STI) with validation.\n'
        '\n'
        '1.0 — Initial release: B2B/B2C/B2G submit, marking ingestion\n'
        '(MARK, verification hash, identifier, QR), PDF upload, B2G status\n'
        'polling, credit-note preceding invoice reference.'
    ),
    'author': 'Efstathios Voulgaris',
    'support': 'efstathiosvoulgaris@gmail.com',
    'license': 'LGPL-3',
    'depends': [
        'l10n_gr_provider_base',
    ],
    'data': [
        'views/res_config_settings_views.xml',
    ],
    'application': True,
    'installable': True,
    'auto_install': False,
}
