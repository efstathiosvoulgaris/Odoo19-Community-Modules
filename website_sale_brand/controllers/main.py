# -*- coding: utf-8 -*-
from odoo.http import request, route
from odoo.fields import Domain
from odoo.addons.website_sale.controllers.main import WebsiteSale


class WebsiteSaleBrand(WebsiteSale):

    def _get_shop_domain(self, search, category, attribute_value_dict, search_in_description=True):
        """Extend shop domain to filter by selected brands."""
        domain = super()._get_shop_domain(
            search, category, attribute_value_dict, search_in_description
        )
        brand_ids = request.session.get('wsale_brand_ids', [])
        if brand_ids:
            domain &= Domain('brand_id', 'in', brand_ids)
        return domain

    @route()
    def shop(self, page=0, category=None, search='', min_price=0.0, max_price=0.0, tags='', **post):
        """Extend shop controller to handle brand filter."""
        brands_param = request.httprequest.args.get('brands', '')
        if brands_param:
            brand_ids = [int(b) for b in brands_param.split(',') if b.isdigit()]
            request.session['wsale_brand_ids'] = brand_ids
            post['brands'] = brands_param
        else:
            brand_ids = []
            request.session.pop('wsale_brand_ids', None)

        response = super().shop(
            page=page, category=category, search=search,
            min_price=min_price, max_price=max_price, tags=tags, **post
        )

        if hasattr(response, 'qcontext'):
            ProductBrand = request.env['product.brand']
            search_product = response.qcontext.get('search_product')

            if search_product is not None and len(search_product):
                all_brands = ProductBrand.search([
                    ('website_published', '=', True),
                    ('product_tmpl_ids.is_published', '=', True),
                ])
            else:
                all_brands = ProductBrand.browse()

            response.qcontext.update({
                'all_brands': all_brands,
                'active_brand_ids': set(brand_ids),
            })

        return response

    @route('/brands', type='http', auth='public', website=True, sitemap=True)
    def brands_page(self, **kwargs):
        """Public page listing all published brands."""
        brands = request.env['product.brand'].search([
            ('website_published', '=', True),
        ])
        return request.render('website_sale_brand.brands_page', {
            'brands': brands,
            
        })
