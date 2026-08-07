# -*- coding: utf-8 -*-
from odoo import fields, models


class PosConfig(models.Model):
    _inherit = 'pos.config'

    l10n_gr_prov_eft_terminal_id = fields.Many2one(
        'l10n.gr.prov.eft.terminal', string='Τερματικό EFT/POS (Α.1155)',
        help='Τερματικό κάρτας που χρησιμοποιείται για τις πληρωμές με κάρτα '
             'σε αυτό το POS. Απαιτείται για τη λήψη υπογραφής Α.1155.')
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


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    pos_l10n_gr_prov_eft_terminal_id = fields.Many2one(
        related='pos_config_id.l10n_gr_prov_eft_terminal_id', readonly=False)
    pos_l10n_gr_prov_eft_require_signature = fields.Boolean(
        related='pos_config_id.l10n_gr_prov_eft_require_signature', readonly=False)
    pos_l10n_gr_prov_eft_max_installments = fields.Integer(
        related='pos_config_id.l10n_gr_prov_eft_max_installments', readonly=False)
