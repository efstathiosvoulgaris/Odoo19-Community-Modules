# -*- coding: utf-8 -*-
from odoo import models


class PosOrder(models.Model):
    _inherit = 'pos.order'

    def _l10n_gr_prov_pos_payment_vals(self):
        """Build the invoice's myDATA payment lines with Α.1155 awareness.

        Card payments that carry a signature are emitted one line each (each
        has its own signature + transaction id); everything else is grouped by
        myDATA type and summed, so cash change (a negative return line) nets
        out. Fully replaces the base implementation when this bridge is present.
        """
        self.ensure_one()
        sign = -1.0 if self.amount_total < 0.0 else 1.0
        grouped = {}
        eft_lines = []
        for p in self.payment_ids:
            amount = sign * p.amount
            if p.l10n_gr_prov_eft_signature:
                if round(amount, 2) > 0:
                    eft_lines.append((0, 0, {
                        # A payment carrying an Α.1155 signature is a card
                        # payment — always type 7 (AADE PM-0037: only 7/8 may
                        # carry transactionId/terminalId/signature).
                        'payment_type': '7',
                        'amount': round(amount, 2),
                        'transaction_id': p.l10n_gr_prov_eft_transaction_id,
                        'l10n_gr_prov_eft_signature': p.l10n_gr_prov_eft_signature,
                        'l10n_gr_prov_eft_signing_author':
                            p.l10n_gr_prov_eft_signing_author,
                        'l10n_gr_prov_eft_terminal_code':
                            p.l10n_gr_prov_eft_terminal_code,
                    }))
            else:
                ptype = p.payment_method_id._l10n_gr_prov_mydata_type()
                grouped[ptype] = grouped.get(ptype, 0.0) + amount
        vals = [
            (0, 0, {'payment_type': ptype, 'amount': round(amount, 2)})
            for ptype, amount in grouped.items()
            if round(amount, 2) > 0
        ]
        return vals + eft_lines
