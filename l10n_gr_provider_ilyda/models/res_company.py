# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    l10n_gr_prov_provider = fields.Selection(
        selection_add=[('ilyda', 'ILYDA (vs.gr)')],
    )
    l10n_gr_prov_ilyda_username = fields.Char(
        string='ILYDA Username',
        groups='base.group_system',
    )
    l10n_gr_prov_ilyda_password = fields.Char(
        string='ILYDA Password',
        groups='base.group_system',
    )
