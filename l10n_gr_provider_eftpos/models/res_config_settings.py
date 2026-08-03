# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    l10n_gr_prov_eft_driver_url = fields.Char(
        related='company_id.l10n_gr_prov_eft_driver_url', readonly=False)
    l10n_gr_prov_eft_license_key = fields.Char(
        related='company_id.l10n_gr_prov_eft_license_key', readonly=False)
    l10n_gr_prov_eft_vat = fields.Char(
        related='company_id.l10n_gr_prov_eft_vat', readonly=False)
