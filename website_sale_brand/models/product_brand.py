# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ProductBrand(models.Model):
    _name = 'product.brand'
    _description = 'Μάρκα Προϊόντος'
    _inherit = ['image.mixin']
    _order = 'name'
    _rec_name = 'name'

    name = fields.Char(
        string='Μάρκα',
        required=True,
        index=True,
        translate=True,
    )
    description = fields.Html(
        string='Περιγραφή',
        translate=True,
    )
    website_published = fields.Boolean(
        string='Δημοσιευμένο στο Website',
        default=True,
    )
    product_tmpl_ids = fields.One2many(
        comodel_name='product.template',
        inverse_name='brand_id',
        string='Προϊόντα',
    )
    product_count = fields.Integer(
        string='Αριθμός Προϊόντων',
        compute='_compute_product_count',
    )

    @api.depends('product_tmpl_ids')
    def _compute_product_count(self):
        for brand in self:
            brand.product_count = len(brand.product_tmpl_ids)
