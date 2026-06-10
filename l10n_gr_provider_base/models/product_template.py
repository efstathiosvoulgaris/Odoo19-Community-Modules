# -*- coding: utf-8 -*-
from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    l10n_gr_prov_cpv = fields.Char(
        string='CPV Code',
        help='Common Procurement Vocabulary code (EC Reg. 213/2008), e.g. '
             '30237200-1. Required on lines of B2G invoices (BT-158, scheme STI). '
             'If no exact CPV exists, use the closest parent code.',
    )
