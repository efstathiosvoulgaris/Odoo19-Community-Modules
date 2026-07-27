# -*- coding: utf-8 -*-
from odoo import fields, models

from .catering_order import CATERING_SPECIAL_CATEGORY


class AccountMove(models.Model):
    _inherit = 'account.move'

    l10n_gr_prov_catering_order_ids = fields.One2many(
        'l10n.gr.prov.catering.order', 'closing_move_id',
        string='Δελτία Παραγγελίας Εστίασης', copy=False)

    def _l10n_gr_prov_ilyda_build_payload(self):
        """A document that closes order notes must carry their MARKs and the
        «Συναλλαγές Εστίασης» flag, otherwise the notes stay open — and a note
        left open for 24 hours suspends transmission for the whole entity."""
        payload = super()._l10n_gr_prov_ilyda_build_payload()
        marks = [
            int(order.mark)
            for order in self.l10n_gr_prov_catering_order_ids
            if order.mark
        ]
        if marks:
            payload['aadeData']['multipleConnectedMarks'] = marks
            payload['aadeData']['aadeSpecialInvoiceCategory'] = CATERING_SPECIAL_CATEGORY
        return payload
