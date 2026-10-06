# -*- coding: utf-8 -*-
"""myDATA payment methods (§5.2 PaymentMethodDetailType, §8.12 types 1-8).

A document may be paid with several methods, each with its own amount.
POS signature fields (tid/ProvidersSignature/ECRToken, Α.1155/2023) are
deliberately omitted until a POS provider integration exists.
"""
import logging

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)

PAYMENT_TYPE_SELECTION = [
    ('1', '1 - Επαγγελματικός Λογαριασμός Πληρωμών Ημεδαπής'),
    ('2', '2 - Επαγγελματικός Λογαριασμός Πληρωμών Αλλοδαπής'),
    ('3', '3 - Μετρητά'),
    ('4', '4 - Επιταγή'),
    ('5', '5 - Επί Πιστώσει'),
    ('6', '6 - Web Banking'),
    ('7', '7 - POS / e-POS'),
    ('8', '8 - Άμεσες Πληρωμές IRIS'),
]


class L10nGrProvPayment(models.Model):
    _name = 'l10n.gr.prov.payment'
    _description = 'Τρόπος Πληρωμής myDATA'

    move_id = fields.Many2one(
        'account.move', required=True, ondelete='cascade', index=True)
    currency_id = fields.Many2one(related='move_id.currency_id')
    payment_type = fields.Selection(
        PAYMENT_TYPE_SELECTION, string='Τύπος', required=True, default='5')
    amount = fields.Monetary(string='Ποσό', currency_field='currency_id')
    info = fields.Char(string='Πληροφορίες')
    tip_amount = fields.Monetary(
        string='Φιλοδώρημα', currency_field='currency_id')
    transaction_id = fields.Char(string='Ταυτότητα Συναλλαγής')
    account_payment_id = fields.Many2one(
        'account.payment', string='Λογιστική Πληρωμή', readonly=True, copy=False,
        help='Η είσπραξη της Αυτόματης Εξόφλησης για αυτή τη γραμμή.')


class AccountMove(models.Model):
    _inherit = 'account.move'

    l10n_gr_prov_payment_ids = fields.One2many(
        'l10n.gr.prov.payment', 'move_id',
        string='Τρόποι Πληρωμής myDATA', copy=False)

    def write(self, vals):
        res = super().write(vals)
        if vals.get('l10n_gr_prov_state') == 'sent':
            for move in self:
                move._l10n_gr_prov_auto_settle()
        return res

    def _l10n_gr_prov_auto_settle(self):
        """Αυτόματη Εξόφληση: once AADE holds the document, book the payment
        methods it declares as payments.

        The declared method is only what AADE is told; the accounting never
        saw the money, so a cash ΑΛΠ issued from the back office stayed «not
        paid» (the POS books its own payments and is left alone). Each line
        whose method has a journal in the settings becomes a payment on it,
        for at most what is still open — a payment already registered by hand
        is not paid twice. Card lines tied to a terminal charge are booked by
        that charge. The document is final by now; a failure is logged on it
        and never undoes the transmission.
        """
        self.ensure_one()
        if (self.state != 'posted'
                or self.move_type not in ('out_invoice', 'out_refund')
                or ('pos_order_ids' in self._fields and self.pos_order_ids)):
            return
        for line in self.l10n_gr_prov_payment_ids:
            if (line.account_payment_id
                    or ('eft_payment_id' in line._fields and line.eft_payment_id)):
                continue
            journal = self.company_id._l10n_gr_prov_settle_journal(line.payment_type)
            if not journal:
                continue
            if self.currency_id.is_zero(self.amount_residual):
                return
            amount = min(line.amount, self.amount_residual)
            try:
                with self.env.cr.savepoint():
                    payments = self.env['account.payment.register'].with_context(
                        active_model='account.move', active_ids=self.ids,
                    ).create({
                        'journal_id': journal.id,
                        'amount': amount,
                        'payment_date': self.invoice_date or fields.Date.context_today(self),
                        'communication': self.name,
                    })._create_payments()
                    line.account_payment_id = payments[:1]
            except Exception as e:
                _logger.exception('Auto-settle failed for %s', self.name)
                self.message_post(body=_(
                    'Αυτόματη Εξόφληση: δεν καταχωρήθηκε η πληρωμή %(amount)s '
                    '(%(method)s) — %(error)s. Καταχωρίστε την με το κουμπί '
                    '«Πληρωμή».', amount=f'{amount:.2f}',
                    method=dict(PAYMENT_TYPE_SELECTION)[line.payment_type], error=e))

    def _l10n_gr_prov_payable(self):
        """myDATA gross: Odoo total + extra taxes − withheld (what is paid)."""
        self.ensure_one()
        return round(
            self.amount_total
            + self.l10n_gr_prov_stamp_duty_amount
            + self.l10n_gr_prov_fees_amount
            + self.l10n_gr_prov_other_taxes_amount
            - self.l10n_gr_prov_withholding_amount, 2)

    @api.onchange('l10n_gr_prov_payment_ids')
    def _onchange_l10n_gr_prov_payment_remainder(self):
        """Default a new payment line's amount to the unassigned remainder."""
        payable = self._l10n_gr_prov_payable()
        assigned = sum(self.l10n_gr_prov_payment_ids.mapped('amount'))
        for line in self.l10n_gr_prov_payment_ids:
            if not line.amount:
                line.amount = max(payable - assigned, 0.0)
