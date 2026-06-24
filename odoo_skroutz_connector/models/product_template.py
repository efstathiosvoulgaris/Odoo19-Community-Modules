# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    # --- Skroutz-specific optional fields ---

    skroutz_mpn = fields.Char(
        string='MPN (Skroutz)',
        help='Manufacturer Part Number sent to Skroutz. Required for feed inclusion.',
    )
    skroutz_color = fields.Char(
        string='Color (Skroutz)',
        help='Product color as shown in product image. Required for fashion categories.',
    )
    skroutz_season = fields.Selection(
        selection=[
            ('winter', 'Winter'),
            ('spring', 'Spring'),
            ('summer', 'Summer'),
            ('autumn', 'Autumn'),
        ],
        string='Season (Skroutz)',
        help='Applicable to fashion and seasonal items.',
    )
    skroutz_size_fit = fields.Selection(
        selection=[
            ('slim', 'Slim'),
            ('regular', 'Regular'),
            ('wide', 'Wide'),
        ],
        string='Size Fit (Skroutz)',
        help='Fit type. Applicable to fashion/apparel items.',
    )
    skroutz_outlet = fields.Boolean(
        string='Outlet (Skroutz)',
        help='Mark this product as an outlet item on Skroutz.',
    )
    skroutz_shipping_cost = fields.Float(
        string='Shipping Cost (Skroutz)',
        digits=(10, 2),
        help='Fixed shipping cost for this product. Leave 0 for free shipping.',
    )
    skroutz_size = fields.Char(
        string='Size(s) (Skroutz)',
        help='Comma-separated list of available sizes, e.g. "S,M,L,XL" or "38,39,40". '
             'Required for fashion and footwear categories.',
    )
    # --- Computed helpers ---

    skroutz_category_path = fields.Char(
        string='Category Path',
        compute='_compute_skroutz_category_path',
        help='Full category breadcrumb path for Skroutz XML.',
    )

    @api.depends('categ_id')
    def _compute_skroutz_category_path(self):
        for tmpl in self:
            if not tmpl.categ_id:
                tmpl.skroutz_category_path = ''
                continue
            parts = []
            categ = tmpl.categ_id
            while categ and categ.name != 'All':
                parts.insert(0, categ.name)
                categ = categ.parent_id
            tmpl.skroutz_category_path = ' > '.join(parts) if parts else tmpl.categ_id.name

    def _get_skroutz_price_with_vat(self):
        """Return list_price with VAT applied."""
        self.ensure_one()
        price = self.list_price
        tax = self.taxes_id[:1]
        if tax and tax.amount_type == 'percent':
            price = price * (1 + tax.amount / 100.0)
        return round(price, 2)

    def _get_skroutz_vat_rate(self):
        """Return VAT percentage (e.g. 24.0)."""
        self.ensure_one()
        tax = self.taxes_id[:1]
        if tax and tax.amount_type == 'percent':
            return round(tax.amount, 2)
        return 0.0

    def _get_skroutz_availability(self, default_avail='Delivery 1 to 3 days'):
        self.ensure_one()
        return 'In stock' if self.qty_available > 0 else default_avail

    def _get_skroutz_weight(self):
        """Return weight in grams (Odoo stores in kg)."""
        self.ensure_one()
        if not self.weight:
            return ''
        return str(int(self.weight * 1000))

    def _get_base_url(self):
        website = self.env['website'].sudo().search([], limit=1)
        return website.get_base_url() if website else self.env['ir.config_parameter'].sudo().get_param('web.base.url')

    def _get_skroutz_product_url(self):
        self.ensure_one()
        slug = self.env['ir.http']._slug(self)
        return f"{self._get_base_url()}/shop/{slug}"

    def _get_image_url(self):
        self.ensure_one()
        return f"{self._get_base_url()}/web/image/product.template/{self.id}/image_1920"

    def _get_additional_image_urls(self):
        self.ensure_one()
        base_url = self._get_base_url()
        return [
            f"{base_url}/web/image/product.image/{img.id}/image_1920"
            for img in self.product_template_image_ids[:15]
        ]
