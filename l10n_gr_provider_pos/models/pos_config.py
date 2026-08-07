# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError

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

    @api.depends('l10n_gr_prov_alp_journal_id',
                 'company_id.l10n_gr_prov_provider')
    def _compute_l10n_gr_prov_enabled(self):
        for config in self:
            config.l10n_gr_prov_enabled = bool(
                config.l10n_gr_prov_alp_journal_id
                and config.company_id._l10n_gr_prov_active())

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

    def action_l10n_gr_prov_tidy_taxes(self):
        """Also create the Greek POS payment methods Odoo doesn't ship (IRIS,
        Web Banking, Επιταγή, τραπεζικές μεταφορές), each carrying its AADE
        §8.12 code."""
        res = super().action_l10n_gr_prov_tidy_taxes()
        created = self.env['pos.payment.method'] \
            ._l10n_gr_prov_create_pos_payment_methods(self.company_id)
        res['params']['message'] += _(
            ' %(created)s νέοι τρόποι πληρωμής POS (από %(total)s ελληνικούς '
            '+ κάρτα) — ενεργοποιήστε όσους θέλετε ανά ταμείο.',
            created=created, total=len(GR_POS_PAYMENT_METHODS))
        return res
