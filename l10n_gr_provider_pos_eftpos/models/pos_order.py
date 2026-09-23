# -*- coding: utf-8 -*-
from odoo import _, models


class PosOrder(models.Model):
    _inherit = 'pos.order'

    def _l10n_gr_prov_pos_eft_payment(self, pos_payment):
        """The charge record behind a signed POS payment line, if any."""
        key = pos_payment.l10n_gr_prov_eft_client_key
        if not key:
            return self.env['l10n.gr.prov.eft.payment']
        return self.env['l10n.gr.prov.eft.payment'].sudo().search(
            [('pos_client_key', '=', key)], limit=1)

    def _l10n_gr_prov_pos_payment_vals(self):
        """Build the invoice's myDATA payment lines with Α.1155 awareness.

        Card payments that carry a signature are emitted one line each (each
        has its own signature + transaction id); everything else is grouped by
        myDATA type and summed, so cash change (a negative return line) nets
        out. Fully replaces the base implementation when this bridge is present.

        Each card line is linked to its charge record, which is how the charge
        is marked submitted once the invoice reaches the provider. A charge the
        cashier made by hand is still «signed» on the server — the id they
        typed makes it paid here.
        """
        self.ensure_one()
        sign = -1.0 if self.amount_total < 0.0 else 1.0
        grouped = {}
        eft_lines = []
        for p in self.payment_ids:
            amount = sign * p.amount
            if p.l10n_gr_prov_eft_signature:
                if round(amount, 2) > 0:
                    eft = self._l10n_gr_prov_pos_eft_payment(p)
                    if (eft and eft.state == 'signed'
                            and p.l10n_gr_prov_eft_transaction_id):
                        eft.write({
                            'transaction_id': p.l10n_gr_prov_eft_transaction_id,
                            'state': 'paid',
                        })
                        eft._log(body=_(
                            'Α.1155: χειροκίνητη χρέωση %(amount)s στο ταμείο '
                            '%(pos)s — Ταυτότητα Συναλλαγής %(tid)s.',
                            amount=f'{eft.amount:.2f}', pos=self.config_id.name,
                            tid=eft.transaction_id))
                    eft_lines.append((0, 0, {
                        # A payment carrying an Α.1155 signature went through
                        # the EFT/POS — always type 7, whether the customer
                        # tapped a card or paid the terminal's IRIS QR.
                        'payment_type': '7',
                        'amount': round(amount, 2),
                        'transaction_id': p.l10n_gr_prov_eft_transaction_id,
                        'l10n_gr_prov_eft_signature': p.l10n_gr_prov_eft_signature,
                        'l10n_gr_prov_eft_signing_author':
                            p.l10n_gr_prov_eft_signing_author,
                        'l10n_gr_prov_eft_terminal_code':
                            p.l10n_gr_prov_eft_terminal_code,
                        'eft_payment_id': eft.id or False,
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

    def _generate_pos_order_invoice(self):
        """Once the invoice exists, the till's charges belong to it — the back
        office then finds them from the document like any other payment."""
        invoice = super()._generate_pos_order_invoice()
        charges = invoice.l10n_gr_prov_payment_ids.eft_payment_id.sudo()
        charges.filtered(lambda c: not c.move_id).write({'move_id': invoice.id})
        return invoice
