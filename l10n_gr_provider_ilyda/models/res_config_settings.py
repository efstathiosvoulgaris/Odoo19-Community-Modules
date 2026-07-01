# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    l10n_gr_prov_ilyda_username = fields.Char(
        related='company_id.l10n_gr_prov_ilyda_username', readonly=False)
    l10n_gr_prov_ilyda_password = fields.Char(
        related='company_id.l10n_gr_prov_ilyda_password', readonly=False)
