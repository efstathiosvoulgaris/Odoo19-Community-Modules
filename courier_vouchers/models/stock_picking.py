# -*- coding: utf-8 -*-
from odoo import fields, models


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    courier_voucher_ids = fields.One2many('courier.voucher', 'picking_id', string='Vouchers')
    courier_voucher_count = fields.Integer(compute='_compute_courier_voucher_count')

    def _compute_courier_voucher_count(self):
        for picking in self:
            picking.courier_voucher_count = len(picking.courier_voucher_ids)

    def _courier_voucher_defaults(self):
        """Default values of a new voucher for this delivery."""
        self.ensure_one()
        defaults = {
            'default_picking_id': self.id,
            'default_partner_id': self.partner_id.id,
            'default_weight': max(self.weight or 0.0, 0.5),
            'default_reference': self.sale_id.name or self.name,
        }
        if self.sale_id.courier_cod:
            defaults['default_cod_amount'] = self.sale_id.amount_total
        return defaults

    def action_courier_new_voucher(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'courier.voucher',
            'view_mode': 'form',
            'target': 'current',
            'context': self._courier_voucher_defaults(),
        }

    def action_courier_vouchers(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('courier_vouchers.action_courier_voucher')
        action['domain'] = [('picking_id', '=', self.id)]
        action['context'] = self._courier_voucher_defaults()
        return action
