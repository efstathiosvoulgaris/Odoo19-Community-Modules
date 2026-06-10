# -*- coding: utf-8 -*-
import json
import logging
from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class SkroutzAcceptWizard(models.TransientModel):
    _name = 'skroutz.accept.wizard'
    _description = 'Accept Skroutz Order'

    order_id = fields.Many2one('skroutz.order', string='Order', required=True)
    pickup_location = fields.Char(string='Pickup Location ID', required=True)
    pickup_window = fields.Integer(string='Pickup Window ID', required=True)
    number_of_parcels = fields.Integer(string='Number of Parcels', default=1)
    accept_options_hint = fields.Text(string='Available Options', readonly=True)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        order_id = self.env.context.get('default_order_id')
        if not order_id:
            return res
        order = self.env['skroutz.order'].browse(order_id)
        try:
            client = order._get_api_client()
            data = client.get_order(order.code)
            opts = (data.get('order') or {}).get('accept_options') or {}
            locations = opts.get('pickup_location') or []
            windows = opts.get('pickup_window') or []
            parcels = opts.get('number_of_parcels') or [1]

            if len(locations) == 1:
                res['pickup_location'] = str(locations[0]['id'])
            if len(windows) == 1:
                res['pickup_window'] = windows[0]['id']
            if parcels:
                res['number_of_parcels'] = parcels[0]

            hints = []
            if locations:
                hints.append('Pickup locations:\n' + '\n'.join(
                    f"  {loc['id']} — {loc.get('label', '')}" for loc in locations
                ))
            if windows:
                hints.append('Pickup windows:\n' + '\n'.join(
                    f"  {win['id']} — {win.get('label', '')}" for win in windows
                ))
            if not hints:
                hints.append('No accept_options returned by the API for this order.')
            res['accept_options_hint'] = '\n\n'.join(hints)
        except Exception:
            _logger.warning("Could not fetch accept_options for order %s", order_id, exc_info=True)
        return res

    def action_confirm_accept(self):
        self.ensure_one()
        order = self.order_id
        if order.state != 'open':
            raise UserError('Only open orders can be accepted.')
        client = order._get_api_client()
        client.accept_order(
            order.code,
            self.pickup_location,
            self.pickup_window,
            self.number_of_parcels,
        )
        order.state = 'accepted'
        config = self.env['ir.config_parameter'].sudo()
        if config.get_param('skroutz.auto_create_sale_order', 'True') == 'True':
            order._create_sale_order()
        return {'type': 'ir.actions.act_window_close'}
