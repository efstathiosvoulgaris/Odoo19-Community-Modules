# -*- coding: utf-8 -*-
from odoo import models


class PosOrder(models.Model):
    _inherit = 'pos.order'

    def _prepare_invoice_vals(self):
        """Attach the table's open order notes to the invoice that closes them.

        They are linked before the invoice is posted and transmitted, so the
        payload builder emits multipleConnectedMarks in the same call — the
        closing document and its correlation must reach AADE together.
        """
        vals = super()._prepare_invoice_vals()
        notes = self._l10n_gr_prov_open_catering_orders()
        if notes:
            vals['l10n_gr_prov_catering_order_ids'] = [(6, 0, notes.ids)]
        return vals

    def _l10n_gr_prov_open_catering_orders(self):
        """Transmitted notes of this POS order that no document has closed yet.

        Notes still in error carry no MARK, so they cannot be correlated; they
        stay open and are visible in the back office for retransmission.
        """
        self.ensure_one()
        if not self.uuid:
            return self.env['l10n.gr.prov.catering.order']
        return self.env['l10n.gr.prov.catering.order'].search([
            ('pos_order_uuid', '=', self.uuid),
            ('state', '=', 'sent'),
            ('closing_move_id', '=', False),
        ])

    def _generate_pos_order_invoice(self):
        invoice = super()._generate_pos_order_invoice()
        notes = invoice.l10n_gr_prov_catering_order_ids
        if notes:
            notes.write({'state': 'closed', 'pos_order_id': self.id})
        return invoice
