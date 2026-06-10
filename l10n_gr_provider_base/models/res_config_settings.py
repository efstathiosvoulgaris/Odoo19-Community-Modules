# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    l10n_gr_prov_provider = fields.Selection(
        related='company_id.l10n_gr_prov_provider', readonly=False)
    l10n_gr_prov_test_env = fields.Boolean(
        related='company_id.l10n_gr_prov_test_env', readonly=False)
    l10n_gr_prov_auto_send = fields.Boolean(
        related='company_id.l10n_gr_prov_auto_send', readonly=False)
