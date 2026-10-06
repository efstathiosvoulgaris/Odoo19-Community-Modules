# -*- coding: utf-8 -*-
from odoo import _, fields, models
from odoo.exceptions import UserError

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

    # Αυτόματη εξόφληση: a document of the back office that gets its MARK is
    # paid with these journals, per declared myDATA payment method. 5 (Επί
    # Πιστώσει) has not been collected and 7 (card) is booked by its terminal,
    # so neither is offered.
    l10n_gr_prov_settle_journal_1_id = fields.Many2one(
        'account.journal', string='1 - Λογαριασμός Πληρωμών Ημεδαπής',
        domain="[('type', 'in', ('bank', 'cash'))]")
    l10n_gr_prov_settle_journal_2_id = fields.Many2one(
        'account.journal', string='2 - Λογαριασμός Πληρωμών Αλλοδαπής',
        domain="[('type', 'in', ('bank', 'cash'))]")
    l10n_gr_prov_settle_journal_3_id = fields.Many2one(
        'account.journal', string='3 - Μετρητά',
        domain="[('type', 'in', ('bank', 'cash'))]")
    l10n_gr_prov_settle_journal_4_id = fields.Many2one(
        'account.journal', string='4 - Επιταγή',
        domain="[('type', 'in', ('bank', 'cash'))]")
    l10n_gr_prov_settle_journal_6_id = fields.Many2one(
        'account.journal', string='6 - Web Banking',
        domain="[('type', 'in', ('bank', 'cash'))]")
    l10n_gr_prov_settle_journal_8_id = fields.Many2one(
        'account.journal', string='8 - IRIS',
        domain="[('type', 'in', ('bank', 'cash'))]")

    def _l10n_gr_prov_settle_journal(self, payment_type):
        """The journal that settles a declared payment method, or empty."""
        self.ensure_one()
        field = f'l10n_gr_prov_settle_journal_{payment_type}_id'
        return self[field] if field in self._fields else self.env['account.journal']

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

    def write(self, vals):
        """Test → production: documents still waiting for a ΜΑΡΚ were made in
        the test environment. Left as they are, the retry cron would send them
        to production and they would get a real ΜΑΡΚ. Refuse until they are
        dealt with (cancelled, or resolved while still on test)."""
        if vals.get('l10n_gr_prov_test_env') is False:
            going_live = self.filtered('l10n_gr_prov_test_env')
            pending = self.env['account.move'].sudo().search([
                ('company_id', 'in', going_live.ids),
                ('state', '=', 'posted'),
                ('l10n_gr_prov_mark', '=', False),
                ('l10n_gr_prov_state', 'in', ('to_send', 'error', 'offline', 'queued')),
            ]) if going_live else self.env['account.move']
            if pending:
                names = ', '.join(pending[:15].mapped('name'))
                more = len(pending) - 15
                raise UserError(_(
                    'Δεν γίνεται μετάβαση σε παραγωγή: %(count)s παραστατικά του '
                    'δοκιμαστικού περιβάλλοντος περιμένουν ακόμη ΜΑΡΚ και θα '
                    'στέλνονταν στην παραγωγή (%(names)s%(more)s). Ακυρώστε τα ή '
                    'ολοκληρώστε τα όσο είστε ακόμη σε δοκιμαστικό.',
                    count=len(pending), names=names,
                    more=_(' και %s ακόμη', more) if more > 0 else ''))
        return super().write(vals)
