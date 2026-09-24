# -*- coding: utf-8 -*-
from odoo import api, fields, models


class PosConfig(models.Model):
    _inherit = 'pos.config'

    l10n_gr_prov_eft_terminal_id = fields.Many2one(
        'l10n.gr.prov.eft.terminal', string='Τερματικό EFT/POS (Α.1155)',
        help='Το προεπιλεγμένο τερματικό κάρτας αυτού του POS. Απαιτείται για '
             'τη λήψη υπογραφής Α.1155.')
    # A shop may have two terminals at one till (or share one between tills):
    # the cashier picks per charge, as Epsilon does.
    l10n_gr_prov_eft_terminal_ids = fields.Many2many(
        'l10n.gr.prov.eft.terminal', 'pos_config_l10n_gr_prov_eft_terminal_rel',
        'config_id', 'terminal_id', string='Επιπλέον Τερματικά',
        help='Άλλα τερματικά που μπορεί να χρησιμοποιήσει αυτό το POS. Με '
             'περισσότερα από ένα, το ταμείο ρωτά σε ποιο θα γίνει η χρέωση.')
    # What the till offers, default first — read by the payment screen.
    l10n_gr_prov_eft_terminal_choices = fields.Json(
        compute='_compute_l10n_gr_prov_eft_terminal_choices')
    l10n_gr_prov_eft_require_signature = fields.Boolean(
        string='Υποχρεωτική Υπογραφή Α.1155', default=False,
        help='Δεν επιτρέπει την ολοκλήρωση πώλησης με κάρτα χωρίς υπογραφή '
             'από το τερματικό. Χωρίς αυτό, ο ταμίας μπορεί να χρεώσει '
             'χειροκίνητα στο τερματικό και να συνεχίσει.')
    l10n_gr_prov_eft_max_installments = fields.Integer(
        string='Μέγιστες Δόσεις', default=0,
        help='0 ή 1 = δεν ζητούνται δόσεις. Με μεγαλύτερη τιμή, το ταμείο '
             'ρωτά πλήθος δόσεων πριν τη χρέωση. Υποστηρίζεται μόνο από όσους '
             'NSP προσφέρουν δόσεις.')


    def _l10n_gr_prov_eft_terminals(self):
        """The terminals this till may charge on, the default first."""
        self.ensure_one()
        return (self.l10n_gr_prov_eft_terminal_id
                | self.l10n_gr_prov_eft_terminal_ids).filtered('active')

    @api.depends('l10n_gr_prov_eft_terminal_id', 'l10n_gr_prov_eft_terminal_ids')
    def _compute_l10n_gr_prov_eft_terminal_choices(self):
        for config in self:
            config.l10n_gr_prov_eft_terminal_choices = [
                {'id': t.id, 'name': t.name}
                for t in config.sudo()._l10n_gr_prov_eft_terminals()]


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    pos_l10n_gr_prov_eft_terminal_id = fields.Many2one(
        related='pos_config_id.l10n_gr_prov_eft_terminal_id', readonly=False)
    pos_l10n_gr_prov_eft_terminal_ids = fields.Many2many(
        related='pos_config_id.l10n_gr_prov_eft_terminal_ids', readonly=False)
    pos_l10n_gr_prov_eft_require_signature = fields.Boolean(
        related='pos_config_id.l10n_gr_prov_eft_require_signature', readonly=False)
    pos_l10n_gr_prov_eft_max_installments = fields.Integer(
        related='pos_config_id.l10n_gr_prov_eft_max_installments', readonly=False)
