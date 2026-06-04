# -*- coding: utf-8 -*-
from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    brand_id = fields.Many2one(
        comodel_name='product.brand',
        string='Μάρκα',
        index=True,
        ondelete='set null',
    )
