# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    aade_username = fields.Char(
        related="company_id.aade_username",
        readonly=False,
    )
    aade_password = fields.Char(
        related="company_id.aade_password",
        readonly=False,
    )
