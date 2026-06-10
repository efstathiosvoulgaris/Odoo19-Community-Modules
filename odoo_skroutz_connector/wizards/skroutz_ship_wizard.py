# -*- coding: utf-8 -*-
from odoo import fields, models
from odoo.exceptions import UserError

COURIERS = [
    ('acs', 'ACS'),
    ('dhl', 'DHL'),
    ('geniki_taxydromiki', 'Geniki Taxydromiki'),
    ('dpd', 'DPD'),
    ('gls', 'GLS'),
]


class SkroutzShipWizard(models.TransientModel):
    _name = 'skroutz.ship.wizard'
    _description = 'Ship Skroutz Order'

    order_id = fields.Many2one('skroutz.order', string='Order', required=True)
    courier = fields.Selection(
        COURIERS,
        string='Courier',
        required=True,
        help='Courier used for this shipment (FBM orders only).',
    )
    tracking_codes = fields.Char(
        string='Tracking Code(s)',
        required=True,
        help='Enter one or more tracking codes separated by commas.',
    )

    def action_confirm_ship(self):
        self.ensure_one()
        order = self.order_id
        if order.state != 'accepted':
            raise UserError('Only accepted orders can be marked as dispatched.')
        client = order._get_api_client()
        client.update_tracking(order.code, self.courier, self.tracking_codes)
        order.write({
            'state': 'dispatched',
            'courier_tracking_codes': self.tracking_codes,
        })
        return {'type': 'ir.actions.act_window_close'}
