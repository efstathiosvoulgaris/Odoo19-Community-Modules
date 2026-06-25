# -*- coding: utf-8 -*-
import json
import logging
from datetime import datetime, timezone

import requests
from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

SKROUTZ_API_BASE = 'https://api.skroutz.gr'

ORDER_STATES = [
    ('open', 'Open'),
    ('accepted', 'Accepted'),
    ('rejected', 'Rejected'),
    ('dispatched', 'Dispatched'),
    ('delivered', 'Delivered'),
    ('cancelled', 'Cancelled'),
    ('expired', 'Expired'),
    ('returned', 'Returned'),
    ('partially_returned', 'Partially Returned'),
    ('for_return', 'For Return'),
    ('partially_delivered', 'Partially Delivered'),
]

_SKROUTZ_VALID_STATES = frozenset(k for k, _ in ORDER_STATES[:])

REJECTION_REASONS = [
    ('out_of_stock', 'Out of Stock'),
    ('wrong_price', 'Wrong Price'),
    ('undeliverable', 'Cannot Deliver to Address'),
    ('shipping_delay', 'Shipping Delay'),
    ('other', 'Other'),
]


class SkroutzApiClient:
    """Thin HTTP client for the Skroutz Merchant API v3."""

    def __init__(self, api_token):
        self._api_token = api_token

    def _headers(self):
        return {
            'Authorization': f'Bearer {self._api_token}',
            'Accept': 'application/vnd.skroutz+json; version=3.0',
            'Content-Type': 'application/json',
        }

    def _request(self, method, path, **kwargs):
        url = f"{SKROUTZ_API_BASE}{path}"
        resp = requests.request(method, url, headers=self._headers(), timeout=15, **kwargs)
        if not resp.ok:
            try:
                body = resp.json()
                messages = []
                for err in body.get('errors', []):
                    messages.extend(err.get('messages', []))
                detail = '; '.join(messages) if messages else resp.text
            except Exception:
                detail = resp.text
            raise UserError(f"Skroutz API error {resp.status_code}: {detail}")
        return resp.json() if resp.content else {}

    def get_order(self, order_code):
        return self._request('GET', f'/merchants/ecommerce/orders/{order_code}')

    def accept_order(self, order_code, pickup_location=None, pickup_window=None, number_of_parcels=1):
        body = {'number_of_parcels': number_of_parcels}
        if pickup_location is not None:
            body['pickup_location'] = pickup_location
        if pickup_window is not None:
            body['pickup_window'] = pickup_window
        return self._request('POST', f'/merchants/ecommerce/orders/{order_code}/accept', json=body)

    def reject_order(self, order_code, rejection_reason_other):
        return self._request('POST', f'/merchants/ecommerce/orders/{order_code}/reject', json={
            'rejection_reason_other': rejection_reason_other,
        })

    def update_tracking(self, order_code, courier=None, tracking_codes=None, fulfilled_by_skroutz=False):
        if isinstance(tracking_codes, str):
            codes = [c.strip() for c in tracking_codes.split(',') if c.strip()]
        else:
            codes = list(tracking_codes)
        if fulfilled_by_skroutz:
            # FBS orders: send courier + tracking to Skroutz
            return self._request('POST', f'/merchants/ecommerce/orders/{order_code}/tracking_details', json={
                'tracking_details': [{'courier': courier, 'tracking_code': code} for code in codes],
            })
        else:
            # Standard orders: just mark as dispatched; courier info is local only
            return self._request('POST', f'/merchants/ecommerce/orders/{order_code}/dispatched')


class SkroutzOrder(models.Model):
    _name = 'skroutz.order'
    _description = 'Skroutz Order'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'code'
    _order = 'created_at desc, id desc'

    code = fields.Char(string='Skroutz Code', required=True, index=True, copy=False)
    state = fields.Selection(ORDER_STATES, string='State', default='open', index=True, tracking=True)
    odoo_order_id = fields.Many2one('sale.order', string='Sale Order', copy=False, ondelete='set null')

    # Customer
    customer_name = fields.Char(string='Customer Name', compute='_compute_customer_name', store=True)
    customer_skroutz_id = fields.Char(string='Skroutz Customer ID', index=True)
    customer_first_name = fields.Char(string='First Name')
    customer_last_name = fields.Char(string='Last Name')
    customer_email = fields.Char(string='Email')
    customer_phone = fields.Char(string='Phone')

    # Shipping address
    ship_first_name = fields.Char(string='First Name')
    ship_last_name = fields.Char(string='Last Name')
    ship_street = fields.Char(string='Street')
    ship_street_number = fields.Char(string='Street Number')
    ship_city = fields.Char(string='City')
    ship_zip = fields.Char(string='ZIP')
    ship_region = fields.Char(string='Region')
    ship_country_code = fields.Char(string='Country', default='GR')
    ship_phone = fields.Char(string='Phone')
    ship_mobile = fields.Char(string='Mobile')

    # Order details
    comments = fields.Text(string='Customer Comments')
    payment_method = fields.Char(string='Payment Method')
    courier = fields.Char(string='Courier')
    courier_voucher = fields.Char(string='Courier Voucher URL')
    courier_tracking_codes = fields.Char(string='Tracking Codes')
    fulfilled_by_skroutz = fields.Boolean(string='Fulfilled by Skroutz (FBS)', default=False)
    set_as_ready_required = fields.Boolean(string='Set as Ready Required', default=False)
    is_ready_for_dispatch = fields.Boolean(string='Ready for Dispatch', default=False)

    # Financials
    total_price = fields.Float(string='Total Price', digits=(10, 2))
    shipping_cost = fields.Float(string='Shipping Cost', digits=(10, 2))
    payment_cost = fields.Float(
        string='Fees (Skroutz)', digits=(10, 2),
        help='Total of Skroutz fees on this order (handling, installments, etc.).',
    )

    # Dates
    created_at = fields.Datetime(string='Placed At')
    expires_at = fields.Datetime(string='Expires At')
    dispatch_until = fields.Datetime(string='Dispatch Until')

    # Raw payload for debugging
    skroutz_data = fields.Text(string='Raw API Data')

    line_ids = fields.One2many('skroutz.order.line', 'order_id', string='Order Lines')

    @staticmethod
    def _join_parts(*parts):
        return ' '.join(p for p in parts if p)

    @api.depends('customer_first_name', 'customer_last_name')
    def _compute_customer_name(self):
        for rec in self:
            rec.customer_name = self._join_parts(rec.customer_first_name, rec.customer_last_name)

    # ── API client factory ────────────────────────────────────────────────────

    def _get_api_client(self):
        config = self.env['ir.config_parameter'].sudo()
        api_token = config.get_param('skroutz.api_token', '')
        if not api_token:
            raise UserError(
                'Skroutz API token is not configured.\n'
                'Go to Settings > Skroutz > Order Management and enter your API token.'
            )
        return SkroutzApiClient(api_token)

    # ── Actions ───────────────────────────────────────────────────────────────

    def action_sync_from_skroutz(self):
        """Re-fetch this order from the Skroutz API."""
        self.ensure_one()
        client = self._get_api_client()
        data = client.get_order(self.code)
        self._apply_skroutz_data(data.get('order', {}))

    def action_accept(self):
        self.ensure_one()
        if self.state != 'open':
            raise UserError('Only open orders can be accepted.')
        # Check if the API returns accept_options; if not, accept directly.
        try:
            client = self._get_api_client()
            data = client.get_order(self.code)
            opts = (data.get('order') or {}).get('accept_options') or {}
            has_options = bool(opts.get('pickup_location') or opts.get('pickup_window'))
        except Exception:
            has_options = False
        if not has_options:
            client = self._get_api_client()
            client.accept_order(self.code)
            self.state = 'accepted'
            return {'type': 'ir.actions.act_window_close'}
        return {
            'type': 'ir.actions.act_window',
            'name': 'Accept Order',
            'res_model': 'skroutz.accept.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_order_id': self.id},
        }

    def action_create_sale_order(self):
        self.ensure_one()
        self._create_sale_order()
        return {'type': 'ir.actions.act_window_close'}

    def action_reject(self):
        self.ensure_one()
        if self.state != 'open':
            raise UserError('Only open orders can be rejected.')
        return {
            'type': 'ir.actions.act_window',
            'name': 'Reject Order',
            'res_model': 'skroutz.reject.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_order_id': self.id},
        }

    def action_ship(self):
        self.ensure_one()
        if self.state != 'accepted':
            raise UserError('Only accepted orders can be marked as dispatched.')
        if self.fulfilled_by_skroutz:
            # FBS: need courier + tracking codes — open wizard
            return {
                'type': 'ir.actions.act_window',
                'name': 'Mark as Shipped',
                'res_model': 'skroutz.ship.wizard',
                'view_mode': 'form',
                'target': 'new',
                'context': {'default_order_id': self.id},
            }
        # Standard order: courier/tracking already set by Skroutz, just dispatch
        client = self._get_api_client()
        client.update_tracking(self.code, fulfilled_by_skroutz=False)
        self.state = 'dispatched'
        return {'type': 'ir.actions.act_window_close'}

    def action_view_sale_order(self):
        self.ensure_one()
        if not self.odoo_order_id:
            raise UserError('No sale order is linked to this Skroutz order.')
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'res_id': self.odoo_order_id.id,
            'view_mode': 'form',
        }

    # ── Sale order creation ───────────────────────────────────────────────────

    def _create_sale_order(self):
        if self.odoo_order_id:
            return self.odoo_order_id
        partner = self._find_or_create_partner()
        lines = []
        for line in self.line_ids:
            if not line.product_id:
                _logger.warning("Skroutz order %s: no product matched for MPN '%s', skipping line.", self.code, line.shop_uid)
                continue
            lines.append((0, 0, {
                'product_id': line.product_id.id,
                'product_uom_qty': line.quantity,
                'price_unit': line.unit_price,
                'name': line.product_name or line.product_id.name,
            }))
        sale_order = self.env['sale.order'].create({
            'partner_id': partner.id,
            'origin': f'Skroutz {self.code}',
            'note': self.comments or '',
            'order_line': lines,
        })
        self.odoo_order_id = sale_order
        return sale_order

    def _find_or_create_partner(self):
        """Find an existing partner for this order's customer, or create one.

        The Skroutz API does not expose the customer's email or phone, so
        deduplication relies on the stable Skroutz customer ID, stored in the
        partner's Reference (ref) field as 'SKROUTZ-<id>'.
        """
        Partner = self.env['res.partner']
        ref = f'SKROUTZ-{self.customer_skroutz_id}' if self.customer_skroutz_id else False
        if ref:
            partner = Partner.search([('ref', '=', ref)], limit=1)
            if partner:
                return partner
        if self.customer_email:
            partner = Partner.search([('email', '=', self.customer_email)], limit=1)
            if partner:
                return partner
        country = self.env['res.country'].search(
            [('code', '=', self.ship_country_code or 'GR')], limit=1
        )
        name = self.customer_name or self._join_parts(self.ship_first_name, self.ship_last_name) or 'Skroutz Customer'
        vals = {
            'name': name,
            'ref': ref or '',
            'email': self.customer_email or '',
            'phone': self.customer_phone or self.ship_phone or '',
            'city': self.ship_city or '',
            'zip': self.ship_zip or '',
            'country_id': country.id if country else False,
        }
        # If the l10n_gr_partner addon is installed, store the street number
        # in its dedicated field; otherwise combine name + number in street.
        l10n_gr_installed = self.env['ir.module.module'].sudo().search_count(
            [('name', '=', 'l10n_gr_partner'), ('state', '=', 'installed')]
        )
        if l10n_gr_installed and self.ship_street_number:
            vals['street'] = self.ship_street or ''
            vals['arithmos_odou'] = self.ship_street_number
        else:
            vals['street'] = self._join_parts(self.ship_street, self.ship_street_number)
        return Partner.create(vals)

    # ── Data ingestion ────────────────────────────────────────────────────────

    @staticmethod
    def _parse_dt(value):
        """Parse an ISO-8601 datetime and convert it to naive UTC (Odoo storage format).

        Skroutz returns local-offset timestamps (e.g. +02:00/+03:00 Athens time);
        simply dropping the tzinfo would store wall-clock time and shift every
        date by 2-3 hours in the UI.
        """
        if not value:
            return False
        try:
            dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
            if dt.tzinfo:
                dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
            return dt
        except (ValueError, AttributeError):
            return False

    def _apply_skroutz_data(self, order_data):
        # Capture before write for idempotency check below
        _prev_data_json = self.skroutz_data
        customer = order_data.get('customer') or {}
        address = customer.get('address') or {}
        tracking = order_data.get('courier_tracking_codes') or []

        # Keep street name and number separate (joined again where needed)
        ship_street = (address.get('street_name') or '').strip()
        ship_street_number = (str(address.get('street_number') or '')).strip()

        # Map Skroutz state to our state; fall back to current state if unknown
        raw_state = order_data.get('state', '')
        if raw_state and raw_state not in _SKROUTZ_VALID_STATES:
            _logger.warning("Skroutz order %s: unknown state '%s', keeping current state.", self.code, raw_state)
        mapped_state = raw_state if raw_state in _SKROUTZ_VALID_STATES else self.state

        # Compute order total from line items (no top-level total_price in the API).
        # Fees (handling, installments, etc.) are added when present.
        line_items = order_data.get('line_items') or []
        computed_total = sum(float(item.get('total_price', 0)) for item in line_items)
        fees = order_data.get('fees') or {}
        fees_total = 0.0
        for v in fees.values():
            try:
                fees_total += float(v)
            except (TypeError, ValueError):
                pass
        computed_total += fees_total

        self.write({
            'state': mapped_state,
            'customer_skroutz_id': customer.get('id', ''),
            'customer_first_name': customer.get('first_name', ''),
            'customer_last_name': customer.get('last_name', ''),
            'customer_phone': customer.get('phone', ''),
            'ship_first_name': customer.get('first_name', ''),
            'ship_last_name': customer.get('last_name', ''),
            'ship_street': ship_street,
            'ship_street_number': ship_street_number,
            'ship_city': address.get('city', ''),
            'ship_zip': address.get('zip', ''),
            'ship_region': address.get('region', ''),
            'ship_country_code': address.get('country_code', 'GR'),
            'ship_phone': customer.get('phone', ''),
            'ship_mobile': customer.get('mobile', ''),
            'comments': order_data.get('comments', ''),
            'payment_method': order_data.get('payment_method', ''),
            'courier': order_data.get('courier', ''),
            'courier_voucher': order_data.get('courier_voucher', ''),
            'fulfilled_by_skroutz': bool(order_data.get('fulfilled_by_skroutz', False)),
            'set_as_ready_required': bool(order_data.get('set_as_ready_required', False)),
            'is_ready_for_dispatch': bool(order_data.get('is_ready_for_dispatch', False)),
            'courier_tracking_codes': ', '.join(str(t) for t in tracking),
            'total_price': computed_total,
            'payment_cost': fees_total,
            'created_at': self._parse_dt(order_data.get('created_at')),
            'expires_at': self._parse_dt(order_data.get('expires_at')),
            'dispatch_until': self._parse_dt(order_data.get('dispatch_until')),
            'skroutz_data': json.dumps(order_data),
        })

        # Rebuild line items only when payload changed (avoids churn on Skroutz webhook retries)
        new_line_items_json = json.dumps(order_data.get('line_items') or [], sort_keys=True)
        try:
            old_line_items_json = json.dumps(
                json.loads(_prev_data_json or '{}').get('line_items') or [], sort_keys=True
            )
        except (ValueError, TypeError):
            old_line_items_json = None
        lines_changed = new_line_items_json != old_line_items_json
        if lines_changed:
            self.line_ids.unlink()
        for item in (order_data.get('line_items') or []) if lines_changed else []:
            shop_uid = item.get('shop_uid') or ''
            mpn = item.get('mpn') or ''
            size = item.get('size') or {}
            size_mpn = size.get('mpn') or ''
            product = False
            for ref in filter(None, [shop_uid, mpn, size_mpn]):
                tmpl = self.env['product.template'].sudo().search(
                    [('default_code', '=', ref)], limit=1
                )
                if tmpl and tmpl.product_variant_ids:
                    product = tmpl.product_variant_ids[:1]
                    break
            self.env['skroutz.order.line'].create({
                'order_id': self.id,
                'skroutz_line_id': item.get('id'),
                'product_id': product.id if product else False,
                'product_name': item.get('product_name', ''),
                'shop_uid': shop_uid,
                'ean': item.get('ean') or size.get('ean') or '',
                'quantity': item.get('quantity', 1),
                'unit_price': item.get('unit_price', 0.0),
                'total_price': item.get('total_price', 0.0),
            })

    @api.model
    def _create_or_update_from_webhook(self, order_code, order_data=None):
        """Called by the webhook controller.

        order_data is the order object from the webhook payload. When provided,
        it is applied directly without an extra API call. If absent, the order
        is fetched from the API (e.g. when called from action_sync_from_skroutz).
        """
        record = self.search([('code', '=', order_code)], limit=1)
        is_new = not record
        if not record:
            record = self.create({'code': order_code})
        if order_data:
            record._apply_skroutz_data(order_data)
        else:
            client = record._get_api_client()
            data = client.get_order(order_code)
            record._apply_skroutz_data(data.get('order', {}))
        if is_new:
            record._notify_new_order()
        return record

    def _notify_new_order(self):
        sales_group = self.env.ref('sales_team.group_sale_salesman', raise_if_not_found=False)
        if not sales_group:
            return
        partners = sales_group.users.mapped('partner_id')
        if not partners:
            return
        self.message_post(
            body=f'New Skroutz order <b>{self.code}</b> received.',
            message_type='notification',
            subtype_xmlid='mail.mt_comment',
            partner_ids=partners.ids,
            notify_by_email=False,
        )


class SkroutzOrderLine(models.Model):
    _name = 'skroutz.order.line'
    _description = 'Skroutz Order Line'

    order_id = fields.Many2one('skroutz.order', string='Order', required=True, ondelete='cascade')
    skroutz_line_id = fields.Char(string='Skroutz Line ID')
    product_id = fields.Many2one('product.product', string='Product')
    product_name = fields.Char(string='Product Name')
    shop_uid = fields.Char(string='MPN / Shop UID')
    ean = fields.Char(string='EAN')
    quantity = fields.Integer(string='Qty', default=1)
    unit_price = fields.Float(string='Unit Price', digits=(10, 2))
    total_price = fields.Float(string='Total', digits=(10, 2))
