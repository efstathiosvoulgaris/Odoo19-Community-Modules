# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    # What a customer asks for at the counter is often the manufacturer's code
    # («TK-18») or the supplier's, not our name or barcode. The till searches
    # name/default_code/barcode only; this carries the rest to it.
    pos_search_extra = fields.Char(compute='_compute_pos_search_extra')

    @api.depends('seller_ids.product_code', 'seller_ids.product_name')
    def _compute_pos_search_extra(self):
        # skroutz_mpn exists only with odoo_skroutz_connector installed.
        has_mpn = 'skroutz_mpn' in self._fields
        for template in self:
            parts = [template.skroutz_mpn] if has_mpn else []
            for seller in template.seller_ids:
                parts += [seller.product_code, seller.product_name]
            template.pos_search_extra = ' '.join(dict.fromkeys(p for p in parts if p))

    @api.model
    def _load_pos_data_fields(self, config):
        fields_ = super()._load_pos_data_fields(config)
        # qty_available: stock at the time the till loads, for the badge on
        # the product card. Not live — reload the till to refresh it.
        return fields_ + [f for f in ('pos_search_extra', 'qty_available')
                          if f not in fields_]
