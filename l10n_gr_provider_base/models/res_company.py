# -*- coding: utf-8 -*-
from odoo import fields, models

from .gr_mydata import OTHER_TAXES_CATEGORY_FIXED, OTHER_TAXES_CATEGORY_SELECTION

STAY_FEE_CATEGORY_SELECTION = [
    s for s in OTHER_TAXES_CATEGORY_SELECTION if s[0] in OTHER_TAXES_CATEGORY_FIXED]


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

    # ponytail: one special category so far; add values (and what they unlock)
    # here when the next sector-specific document shows up.
    l10n_gr_prov_business_type = fields.Selection(
        selection=[
            ('general', 'Γενική επιχείρηση'),
            ('accommodation', 'Κατάλυμα (Τέλος Διαμονής)'),
        ],
        string='Κατηγορία Επιχείρησης',
        default='general', required=True,
        help='Ενεργοποιεί τα παραστατικά που αφορούν μόνο τον κλάδο. Κατάλυμα: '
             'το Ειδικό Στοιχείο Τέλους Διαμονής (8.2, ΤΔΙ) και το κουμπί '
             'έκδοσής του στις αποδείξεις/τιμολόγια.',
    )
    l10n_gr_prov_stay_fee_category = fields.Selection(
        selection=STAY_FEE_CATEGORY_SELECTION,
        string='Κατηγορία Τέλους Διαμονής',
        help='Η κατηγορία του καταλύματος (π.χ. Ξενοδοχείο 3 αστέρων). Ορίζει '
             'το πάγιο ποσό ανά διανυκτέρευση στο Ειδικό Στοιχείο (8.2). Αν το '
             'ημερολόγιο ΤΔΙ έχει δική του προεπιλογή, υπερισχύει εκείνη.',
    )

    def _l10n_gr_prov_active(self):
        self.ensure_one()
        return bool(self.l10n_gr_prov_provider and self.l10n_gr_prov_provider != 'none')
