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
        if not marks:
            return payload
        payload['aadeData']['multipleConnectedMarks'] = marks
        payload['aadeData']['aadeSpecialInvoiceCategory'] = CATERING_SPECIAL_CATEGORY
        # DP-0007: a catering document is matched against the notes line by
        # line, so its rows must carry quantities — which the base builder only
        # emits for dispatch notes and for the 8.6 itself.
        lines = {number: line for number, line
                 in enumerate(self._l10n_gr_prov_ilyda_lines(), start=1)}
        for row in payload['aadeData'].get('invoiceRowTypes') or []:
            line = lines.get(row.get('lineNumber'))
            if not line:
                continue
            row['quantity'] = line.quantity
            unit_code, unit_title = line._l10n_gr_prov_measurement_unit()
            row['measurementUnit'] = unit_code
            if unit_code == 7:
                row['otherMeasurementUnitTitle'] = unit_title
                row['otherMeasurementUnitQuantity'] = max(int(line.quantity or 0), 1)
        return payload
