# -*- coding: utf-8 -*-
from odoo import fields, models


class PosConfig(models.Model):
    _inherit = 'pos.config'

    l10n_gr_prov_eft_terminal_id = fields.Many2one(
        'l10n.gr.prov.eft.terminal', string='Τερματικό EFT/POS (Α.1155)',
        help='Τερματικό κάρτας που χρησιμοποιείται για τις πληρωμές με κάρτα '
             'σε αυτό το POS. Απαιτείται για τη λήψη υπογραφής Α.1155.')


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    pos_l10n_gr_prov_eft_terminal_id = fields.Many2one(
        related='pos_config_id.l10n_gr_prov_eft_terminal_id', readonly=False)
