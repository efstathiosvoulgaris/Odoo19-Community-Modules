# -*- coding: utf-8 -*-
from odoo import fields, models
from odoo.exceptions import UserError
from ..models.skroutz_order import REJECTION_REASONS

_REJECTION_REASON_LABELS = dict(REJECTION_REASONS)


class SkroutzRejectWizard(models.TransientModel):
    _name = 'skroutz.reject.wizard'
    _description = 'Reject Skroutz Order'

    order_id = fields.Many2one('skroutz.order', string='Order', required=True)
    rejection_reason = fields.Selection(
        REJECTION_REASONS,
        string='Reason',
        required=True,
        default='other',
    )

    def action_confirm_reject(self):
        self.ensure_one()
        order = self.order_id
        if order.state != 'open':
            raise UserError('Only open orders can be rejected.')
        client = order._get_api_client()
        reason_text = _REJECTION_REASON_LABELS.get(self.rejection_reason, self.rejection_reason)
        client.reject_order(order.code, reason_text)
        order.state = 'rejected'
        return {'type': 'ir.actions.act_window_close'}
