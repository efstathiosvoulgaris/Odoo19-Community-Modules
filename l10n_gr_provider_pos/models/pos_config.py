# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

from .pos_payment_method import GR_POS_PAYMENT_METHODS


class PosConfig(models.Model):
    _inherit = 'pos.config'

    l10n_gr_prov_alp_journal_id = fields.Many2one(
        'account.journal', string='Ημερολόγιο ΑΛΠ (11.x)',
        domain="[('type', '=', 'sale'), ('l10n_gr_edi_inv_type_default', 'in', ('11.1', '11.2', '11.3', '11.5'))]",
        help='Κάθε παραγγελία POS εκδίδεται ως ΑΛΠ σε αυτό το ημερολόγιο και '
             'διαβιβάζεται στον πάροχο. Χωρίς ημερολόγιο εδώ, το POS δουλεύει '
             'όπως το στάνταρ Odoo (χωρίς πάροχο).')
    l10n_gr_prov_tim_journal_id = fields.Many2one(
        'account.journal', string='Ημερολόγιο ΤΙΜ (1.1)',
        domain="[('type', '=', 'sale'), ('l10n_gr_edi_inv_type_default', '=', '1.1')]",
        help='Όταν ο χειριστής ζητήσει Τιμολόγιο (πελάτης με ΑΦΜ).')
    l10n_gr_prov_pla_journal_id = fields.Many2one(
        'account.journal', string='Ημερολόγιο ΠΛΠ (11.4)',
        domain="[('type', '=', 'sale'), ('l10n_gr_edi_inv_type_default', '=', '11.4')]",
        help='Επιστροφές λιανικής (πιστωτικό στοιχείο 11.4).')
    l10n_gr_prov_walkin_partner_id = fields.Many2one(
        'res.partner', string='Πελάτης Λιανικής',
        help='Χρησιμοποιείται στις ΑΛΠ όταν δεν έχει επιλεγεί πελάτης. '
             'Δημιουργήστε μία επαφή «Πελάτης Λιανικής» και επιλέξτε την εδώ.')

    # account.journal is not among the models the POS loads, so the journal
    # many2ones above cannot be evaluated in the front end — a plain boolean is
    # the only reliable signal there that this till issues through the provider.
    l10n_gr_prov_enabled = fields.Boolean(
        string='Έκδοση μέσω Παρόχου',
        compute='_compute_l10n_gr_prov_enabled')

    l10n_gr_prov_print_mode = fields.Selection([
        ('legal', 'Νόμιμο παραστατικό (ΑΛΠ 80mm / ΤΙΜ A4)'),
        ('receipt', 'Απόδειξη ταμείου με ΜΑΡΚ και QR'),
        ('both', 'Και τα δύο'),
    ], string='Τι Εκτυπώνει το Ταμείο', default='legal', required=True,
        help='Το νόμιμο παραστατικό είναι το εκτυπωμένο account.move στη '
             'φόρμα του ημερολογίου — ό,τι ακριβώς δίνει και το λογιστήριο. '
             'Η απόδειξη ταμείου είναι το θερμικό δελτίο του Odoo με τα '
             'στοιχεία διαβίβασης (ΜΑΡΚ, QR, Συμβ. Αυθεντικοποίησης).')
    l10n_gr_prov_allow_tim = fields.Boolean(
        string='Έκδοση Τιμολογίου (ΤΙΜ) από το Ταμείο', default=True,
        help='Εμφανίζει το κουμπί «Τιμολόγιο» στην οθόνη πληρωμής, για πελάτη '
             'που ζητά τιμολόγιο αντί για απόδειξη. Απαιτεί ημερολόγιο ΤΙΜ και '
             'επιλεγμένο πελάτη με ΑΦΜ.')
    l10n_gr_prov_send_failure = fields.Selection([
        ('ignore', 'Συνέχεια — το παραστατικό μπαίνει σε ουρά επανάληψης'),
        ('warn', 'Συνέχεια με προειδοποίηση στον ταμία'),
        ('block', 'Διακοπή της πώλησης'),
    ], string='Αποτυχία Διαβίβασης', default='ignore', required=True,
        help='Τι γίνεται όταν η διαβίβαση στον πάροχο αποτύχει τη στιγμή της '
             'πληρωμής. Η διακοπή επιστρέφει την παραγγελία στο ταμείο '
             'ΑΚΥΡΩΤΗ: κατάλληλη για κατάστημα που δεν επιτρέπεται να δώσει '
             'αδιαβίβαστο παραστατικό, ακατάλληλη για εστίαση με κίνηση.')

    @api.model
    def _default_payment_methods(self):
        """A new till must be able to take cash.

        Core creates the cash journal and its method only when the company has
        NO payment method at all, and otherwise offers an existing cash method
        only if no other till has claimed it (`_default_payment_methods`).
        Seeding the Greek bank methods satisfies the first test, and the first
        till owns the only cash method — so the second till on a provider
        database was created with every card and bank method and no cash at
        all. No cash method also means no cash control: no opening or closing
        count.

        Same failure as the missing «Κάρτα-POS» fixed in 1.4, one branch over.
        """
        methods = super()._default_payment_methods()
        if not methods.filtered('is_cash_count'):
            cash = self._create_cash_payment_method()
            cash.name = _('Μετρητά')
            methods |= cash
        return methods

    @api.depends('l10n_gr_prov_alp_journal_id',
                 'company_id.l10n_gr_prov_provider')
    def _compute_l10n_gr_prov_enabled(self):
        for config in self:
            config.l10n_gr_prov_enabled = bool(
                config.l10n_gr_prov_alp_journal_id
                and config.company_id._l10n_gr_prov_active())

    @api.constrains('l10n_gr_prov_allow_tim', 'l10n_gr_prov_tim_journal_id')
    def _check_l10n_gr_prov_allow_tim(self):
        for config in self:
            if (config.l10n_gr_prov_allow_tim
                    and config.l10n_gr_prov_alp_journal_id
                    and not config.l10n_gr_prov_tim_journal_id):
                raise ValidationError(_(
                    'Για να εκδίδει το ταμείο Τιμολόγιο (ΤΙΜ) πρέπει πρώτα να '
                    'οριστεί το «Ημερολόγιο ΤΙΜ (1.1)» στις ρυθμίσεις του POS.'))

    def _l10n_gr_prov_get_walkin_partner(self):
        """The retail walk-in partner is created once by the user (a normal
        contact, e.g. «Πελάτης Λιανικής») and selected in the POS settings."""
        self.ensure_one()
        if not self.l10n_gr_prov_walkin_partner_id:
            raise UserError(_(
                'Ορίστε τον «Πελάτη Λιανικής» στις ρυθμίσεις του POS '
                '(ενότητα Πάροχος myDATA): δημιουργήστε μία επαφή '
                '«Πελάτης Λιανικής» και επιλέξτε την — χρησιμοποιείται στις '
                'ΑΛΠ όταν δεν έχει επιλεγεί πελάτης.'))
        return self.l10n_gr_prov_walkin_partner_id


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    pos_l10n_gr_prov_alp_journal_id = fields.Many2one(
        related='pos_config_id.l10n_gr_prov_alp_journal_id', readonly=False)
    pos_l10n_gr_prov_tim_journal_id = fields.Many2one(
        related='pos_config_id.l10n_gr_prov_tim_journal_id', readonly=False)
    pos_l10n_gr_prov_pla_journal_id = fields.Many2one(
        related='pos_config_id.l10n_gr_prov_pla_journal_id', readonly=False)
    pos_l10n_gr_prov_walkin_partner_id = fields.Many2one(
        related='pos_config_id.l10n_gr_prov_walkin_partner_id', readonly=False)
    pos_l10n_gr_prov_print_mode = fields.Selection(
        related='pos_config_id.l10n_gr_prov_print_mode', readonly=False)
    pos_l10n_gr_prov_allow_tim = fields.Boolean(
        related='pos_config_id.l10n_gr_prov_allow_tim', readonly=False)
    pos_l10n_gr_prov_send_failure = fields.Selection(
        related='pos_config_id.l10n_gr_prov_send_failure', readonly=False)

    def action_l10n_gr_prov_tidy_taxes(self):
        """Also create the Greek POS payment methods Odoo doesn't ship (IRIS,
        Web Banking, Επιταγή, τραπεζικές μεταφορές), each carrying its AADE
        §8.12 code."""
        res = super().action_l10n_gr_prov_tidy_taxes()
        counts = self.env['pos.payment.method'] \
            ._l10n_gr_prov_create_pos_payment_methods(self.company_id)
        res['params']['message'] += _(
            ' %(created)s νέοι τρόποι πληρωμής POS (από %(total)s ελληνικούς '
            '+ κάρτα), %(repaired)s διορθώθηκαν — ενεργοποιήστε όσους θέλετε '
            'ανά ταμείο.',
            created=counts['created'], repaired=counts['repaired'],
            total=len(GR_POS_PAYMENT_METHODS))
        if counts['undeclared']:
            res['params']['message'] += _(
                ' ΠΡΟΣΟΧΗ: %(undeclared)s τραπεζικοί τρόποι πληρωμής δεν έχουν '
                'δηλωμένο τύπο myDATA και διαβιβάζονται ως κάρτα (τύπος 7). '
                'Ορίστε τον τύπο τους.',
                undeclared=counts['undeclared'])
        return res
