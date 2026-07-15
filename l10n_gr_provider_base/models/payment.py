# -*- coding: utf-8 -*-
"""myDATA payment methods (§5.2 PaymentMethodDetailType, §8.12 types 1-8).

A document may be paid with several methods, each with its own amount.
POS signature fields (tid/ProvidersSignature/ECRToken, Α.1155/2023) are
deliberately omitted until a POS provider integration exists.
"""
from odoo import api, fields, models

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


class AccountMove(models.Model):
    _inherit = 'account.move'

    l10n_gr_prov_payment_ids = fields.One2many(
        'l10n.gr.prov.payment', 'move_id',
        string='Τρόποι Πληρωμής myDATA', copy=False)

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
