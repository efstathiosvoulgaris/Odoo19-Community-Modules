# -*- coding: utf-8 -*-
"""POS orders through the e-invoicing provider.

Every validated order becomes a posted invoice on the proper Greek journal
(ΑΛΠ 11.x / ΤΙΜ 1.1 / ΠΛΑ 11.4) and rides the existing provider workflow —
send, TF-2 queue, TF-1 offline QR. A failed transmission never blocks the
sale: the document stays in the retry queue and the receipt says so.
"""
import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class PosOrder(models.Model):
    _inherit = 'pos.order'

    # The cashier's explicit «Τιμολόγιο» request (the stock to_invoice flag is
    # forced on for every provider order, so it can't carry that meaning).
    l10n_gr_prov_timologio = fields.Boolean(copy=False)

    # Legal markings, surfaced for the receipt (read by the POS UI after sync)
    l10n_gr_prov_doc_name = fields.Char(related='account_move.name')
    l10n_gr_prov_inv_type = fields.Selection(
        related='account_move.l10n_gr_edi_inv_type')
    l10n_gr_prov_mark = fields.Char(related='account_move.l10n_gr_prov_mark')
    l10n_gr_prov_verification_hash = fields.Char(
        related='account_move.l10n_gr_prov_verification_hash')
    l10n_gr_prov_qr_url = fields.Char(related='account_move.l10n_gr_prov_qr_url')
    l10n_gr_prov_state = fields.Selection(
        related='account_move.l10n_gr_prov_state')

    def _l10n_gr_prov_pos_applicable(self):
        self.ensure_one()
        return bool(self.config_id.l10n_gr_prov_alp_journal_id
                    and self.company_id.l10n_gr_prov_provider)

    def _l10n_gr_prov_pos_journal(self):
        """ΑΛΠ by default; ΤΙΜ on explicit request; refunds go to the proper
        credit journals — ΠΛΠ (11.4) for retail, ΠΙΣΤ (5.1) for a ΤΙΜ —
        never to the sale journal's R-sequence."""
        self.ensure_one()
        config = self.config_id
        is_refund = self.amount_total < 0.0
        if self.l10n_gr_prov_timologio:
            if is_refund:
                return self._l10n_gr_prov_find_journal('5.1')
            return config.l10n_gr_prov_tim_journal_id
        if is_refund:
            return (config.l10n_gr_prov_pla_journal_id
                    or self._l10n_gr_prov_find_journal('11.4'))
        return config.l10n_gr_prov_alp_journal_id

    def _l10n_gr_prov_find_journal(self, inv_type):
        return self.env['account.journal'].search([
            ('company_id', '=', self.company_id.id),
            ('type', '=', 'sale'),
            ('l10n_gr_edi_inv_type_default', '=', inv_type),
            ('l10n_gr_prov_delivery_note', '=', False),
        ], limit=1)

    def _process_saved_order(self, draft):
        if not draft and self.state != 'cancel' and self._l10n_gr_prov_pos_applicable():
            # remember the cashier's actual choice, then force invoicing —
            # the provider needs an account.move for every order
            self.l10n_gr_prov_timologio = self.to_invoice
            self.to_invoice = True
        res = super()._process_saved_order(draft)
        if not draft and self.account_move and self._l10n_gr_prov_pos_applicable():
            self._l10n_gr_prov_pos_send()
        return res

    def _prepare_invoice_vals(self):
        vals = super()._prepare_invoice_vals()
        if len(self) == 1 and self._l10n_gr_prov_pos_applicable():
            journal = self._l10n_gr_prov_pos_journal()
            if journal:
                vals['journal_id'] = journal.id
                vals['l10n_gr_edi_inv_type'] = journal.l10n_gr_edi_inv_type_default
            if not self.partner_id:
                vals['partner_id'] = \
                    self.config_id._l10n_gr_prov_get_walkin_partner().id
        return vals

    def _get_invoice_lines_values(self, line_values, pos_line, move_type):
        """Invoice lines are created directly (no onchange path) — derive the
        myDATA classification here, exactly like the form onchange would."""
        vals = super()._get_invoice_lines_values(line_values, pos_line, move_type)
        if (self._l10n_gr_prov_pos_applicable()
                and not vals.get('display_type')
                and vals.get('product_id')):
            journal = self._l10n_gr_prov_pos_journal()
            inv_type = journal.l10n_gr_edi_inv_type_default
            product = pos_line.product_id
            ptype = product.product_tmpl_id.l10n_gr_prov_product_type_gr or 'goods'
            cat, e3 = self.env['l10n.gr.prov.cls.default'].get_default(
                inv_type, ptype, self.company_id.id)
            if cat:
                vals['l10n_gr_prov_cls_category'] = cat
                vals['l10n_gr_prov_cls_type'] = e3
        return vals

    def _l10n_gr_prov_pos_send(self):
        """Real payment methods onto the move, then synchronous send. Any
        failure is swallowed: the receipt shows the pending notice and the
        provider cron retries."""
        self.ensure_one()
        move = self.account_move
        if not move.l10n_gr_prov_applicable or move.l10n_gr_prov_mark:
            return
        try:
            # refund orders carry negative payment amounts — normalize the
            # sign so their real methods survive (the credit note is positive)
            sign = -1.0 if self.amount_total < 0.0 else 1.0
            payments = [{
                'payment_type':
                    p.payment_method_id.l10n_gr_prov_payment_type or '3',
                'amount': sign * p.amount,
            } for p in self.payment_ids if sign * p.amount > 0]
            # cash change: the tendered amount exceeds the payable — deduct
            # the difference from the largest cash-type payment
            payable = move._l10n_gr_prov_payable()
            excess = round(sum(p['amount'] for p in payments) - abs(payable), 2)
            if excess > 0:
                cash = max((p for p in payments if p['payment_type'] == '3'),
                           key=lambda p: p['amount'], default=None)
                if cash:
                    cash['amount'] = round(cash['amount'] - excess, 2)
            move.l10n_gr_prov_payment_ids.unlink()
            move.l10n_gr_prov_payment_ids = [(0, 0, p) for p in payments]
            move._l10n_gr_prov_try_send()
        except Exception:
            _logger.exception(
                'Provider send failed for POS order %s (%s)',
                self.name, move.name)
