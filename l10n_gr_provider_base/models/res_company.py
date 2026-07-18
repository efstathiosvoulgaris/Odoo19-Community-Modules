# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    l10n_gr_prov_provider = fields.Selection(
        selection=[('none', 'None')],
        string='E-Invoicing Provider',
        default='none',
        help='Licensed Greek e-invoicing provider (Y.PA.H.E.S.) used to issue '
             'documents. Driver modules add options to this list.',
    )
    l10n_gr_prov_test_env = fields.Boolean(
        string='Provider Test Environment',
        default=True,
        help='Submit documents to the provider\'s test environment instead of production.',
    )
    l10n_gr_prov_auto_send = fields.Boolean(
        string='Auto-send on Post',
        default=False,
        help='If enabled, posted invoices are queued and transmitted automatically '
             'by the scheduled job. Otherwise use the "Send to Provider" button or '
             'the Send & Print flow.',
    )

    l10n_gr_prov_guard_tax = fields.Boolean(
        string='Έλεγχος Φόρων στην Καταχώριση',
        default=True,
        help='Μπλοκάρει την καταχώριση παραστατικού με λάθος φόρους: γραμμή '
             'χωρίς ΦΠΑ, φόρο εκτός των επιτρεπτών για το είδος παραστατικού, '
             '0% χωρίς αιτία απαλλαγής, ή γραμμή χωρίς χαρακτηρισμό myDATA. '
             'Χωρίς τον έλεγχο, τα λάθη εμφανίζονται μόνο κατά την αποστολή '
             'στον πάροχο.',
    )
    l10n_gr_prov_guard_island = fields.Boolean(
        string='Έλεγχος Νησιωτικών Συντελεστών',
        default=True,
        help='Μπλοκάρει μειωμένους νησιωτικούς συντελεστές (17/9/4%) σε πελάτες '
             'χωρίς καθεστώς Νησιών Αιγαίου, και πλήρεις συντελεστές (24/13/6%) '
             'σε πελάτες με το καθεστώς.',
    )

    def _l10n_gr_prov_active(self):
        self.ensure_one()
        return bool(self.l10n_gr_prov_provider and self.l10n_gr_prov_provider != 'none')
