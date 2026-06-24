# -*- coding: utf-8 -*-
import hmac
import json
import logging
from datetime import datetime
from xml.etree.ElementTree import Element, SubElement, tostring

from odoo.http import request, route, Response, Controller

_logger = logging.getLogger(__name__)


def _build_product_element(product, default_avail):
    """Build a <product> XML element for a product.template record."""
    p = Element('product')

    def add(tag, value):
        el = SubElement(p, tag)
        el.text = str(value) if value is not None else ''

    # Required
    add('id', product.id)
    add('name', product.name or '')
    add('link', product._get_skroutz_product_url())
    add('image', product._get_image_url())

    for img_url in product._get_additional_image_urls():
        add('additionalimage', img_url)

    add('category', product.skroutz_category_path)
    add('price_with_vat', f"{product._get_skroutz_price_with_vat():.2f}")
    add('vat', f"{product._get_skroutz_vat_rate():.2f}")
    add('availability', product._get_skroutz_availability(default_avail))

    manufacturer = product.brand_id.name if 'brand_id' in product._fields and product.brand_id else 'OEM'
    add('manufacturer', manufacturer)
    add('mpn', product.default_code or '')
    if product.barcode:
        add('ean', product.barcode)
    add('description', product.description_sale or product.description or product.name or '')
    add('quantity', int(max(0, product.qty_available)))

    # Optional
    weight = product._get_skroutz_weight()
    if weight:
        add('weight', weight)
    if product.skroutz_size:
        add('size', product.skroutz_size)
    if product.skroutz_color:
        add('color', product.skroutz_color)
    if product.skroutz_season:
        add('season', product.skroutz_season)
    if product.skroutz_size_fit:
        add('size_fit', product.skroutz_size_fit)
    if product.skroutz_outlet:
        add('outlet', 'Y')
    if product.skroutz_shipping_cost:
        add('shipping_costs', f"{product.skroutz_shipping_cost:.2f}")

    return p


def _generate_xml(products, default_avail):
    """Generate the full Skroutz XML feed string."""
    root = Element('mywebstore')
    created = SubElement(root, 'created_at')
    created.text = datetime.now().strftime('%Y-%m-%d %H:%M')
    products_el = SubElement(root, 'products')

    for product in products:
        try:
            products_el.append(_build_product_element(product, default_avail))
        except Exception as e:
            _logger.warning("Skroutz feed: skipping product %s (%s): %s",
                            product.id, product.name, e)

    xml_body = tostring(root, encoding='unicode')
    return f'<?xml version="1.0" encoding="UTF-8"?>{xml_body}'


class SkroutzFeedController(Controller):

    @route('/skroutz/feed', type='http', auth='public', csrf=False, sitemap=False)
    def skroutz_feed(self, token=None, download=None, **kwargs):
        """Serve the Skroutz XML product feed."""
        config = request.env['ir.config_parameter'].sudo()

        # Token check (optional)
        required_token = config.get_param('skroutz.feed_token', '')
        if required_token and not hmac.compare_digest(token or '', required_token):
            return Response('Unauthorized', status=401, content_type='text/plain')

        include_zero = config.get_param('skroutz.include_zero_stock', 'True').lower() in ('1', 'true', 'yes')

        domain = [('is_published', '=', True), ('default_code', '!=', False)]
        if not include_zero:
            domain.append(('qty_available', '>', 0))

        default_avail = config.get_param('skroutz.default_availability', 'Delivery 1 to 3 days')
        products = request.env['product.template'].sudo().search(domain, order='id')
        xml_content = _generate_xml(products, default_avail)

        headers = {
            'Content-Type': 'application/xml; charset=utf-8',
            'Cache-Control': 'no-cache',
        }
        if download:
            headers['Content-Disposition'] = 'attachment; filename="skroutz_feed.xml"'

        return Response(xml_content, status=200, headers=headers)

    @route(['/skroutz/webhook', '/skroutz/webhook/<string:token>'],
           type='http', auth='public', csrf=False, sitemap=False, methods=['POST'])
    def skroutz_webhook(self, token=None, **kwargs):
        """Receive Skroutz order event notifications.

        Skroutz does not sign webhook requests (the only headers sent are
        Content-Type and User-Agent), so authentication is done via a secret
        token embedded in the URL path: /skroutz/webhook/<secret>.
        Register the full URL (including the secret) in the Skroutz merchant
        panel. If no secret is configured, the plain URL is accepted.
        """
        raw_body = request.httprequest.get_data()

        config = request.env['ir.config_parameter'].sudo()
        webhook_secret = config.get_param('skroutz.webhook_secret', '')
        if webhook_secret and not hmac.compare_digest(token or '', webhook_secret):
            _logger.warning("Skroutz webhook: invalid or missing URL token.")
            return Response('Forbidden', status=403, content_type='text/plain')

        try:
            payload = json.loads(raw_body)
        except (ValueError, TypeError):
            return Response('Bad Request', status=400, content_type='text/plain')

        order_data = payload.get('order') or {}
        order_code = order_data.get('code', '')
        if not order_code:
            return Response('Bad Request: missing order.code', status=400, content_type='text/plain')

        try:
            request.env['skroutz.order'].sudo()._create_or_update_from_webhook(
                order_code, order_data=order_data
            )
        except Exception:
            _logger.exception("Skroutz webhook: error processing order %s", order_code)
            # Return 500 so Skroutz retries the delivery (up to 4 times within 20 minutes).
            return Response('Internal Server Error', status=500, content_type='text/plain')

        return Response('OK', status=200, content_type='text/plain')
