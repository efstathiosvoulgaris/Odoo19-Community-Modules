# -*- coding: utf-8 -*-
from odoo import fields, models, _


class AccountMove(models.Model):
    _inherit = 'account.move'

    l10n_gr_prov_eft_payment_ids = fields.One2many(
        'l10n.gr.prov.eft.payment', 'move_id',
        string='Πληρωμές EFT/POS', copy=False)

    def action_l10n_gr_prov_send(self):
        """Α.1155 interception: a card (type-7) payment line needs a provider
        signature before the document may be submitted. Sending such a
        document opens the EFT dialog (terminal → signature → charge →
        transaction id); the dialog then re-triggers this send with the
        signature attached, which passes straight through."""
        if len(self) == 1 and self.state == 'posted' and not self.l10n_gr_prov_mark:
            # 'charging' too: a charge of unknown outcome must be settled
            # before the document goes out, or it goes out without it.
            pending = self.l10n_gr_prov_eft_payment_ids.filtered(
                lambda p: p.state in ('draft', 'signed', 'charging'))
            card_lines = self.l10n_gr_prov_payment_ids.filtered(
                lambda p: p.payment_type == '7' and not p.eft_payment_id)
            if pending:
                return pending[0]._reopen()
            if card_lines:
                return {
                    'type': 'ir.actions.act_window',
                    'name': _('Πληρωμή με Κάρτα (Α.1155)'),
                    'res_model': 'l10n.gr.prov.eft.payment',
                    'view_mode': 'form',
                    'target': 'new',
                    'context': {
                        'default_move_id': self.id,
                        'default_amount': sum(card_lines.mapped('amount')),
                    },
                }
        return super().action_l10n_gr_prov_send()

    def write(self, vals):
        """Once the provider holds the document, every card payment that was
        in it is submitted — not only the one whose dialog triggered the send.
        With two cards on one document, the first used to stay «paid» forever
        and could still be voided after AADE had it. Covers a later cron retry
        or recovery as well as the dialog."""
        res = super().write(vals)
        if vals.get('l10n_gr_prov_state') in ('sent', 'queued'):
            for move in self:
                in_payload = move.l10n_gr_prov_payment_ids.eft_payment_id
                in_payload.filtered(
                    lambda p: p.state == 'paid' and not p.retrograde
                ).write({'state': 'submitted', 'submit_error': False})
        return res

    def _l10n_gr_prov_ilyda_build_payload(self):
        """Enrich type-7 payment methods with the Α.1155 signature fields
        (real-time flow): signature, signingAuthor, terminalId, transactionId."""
        payload = super()._l10n_gr_prov_ilyda_build_payload()
        methods = payload.get('paymentMethods') or []
        lines = self.l10n_gr_prov_payment_ids
        # the builder emits one dict per payment line, in order
        if len(methods) == len(lines):
            for line, method in zip(lines, methods):
                eft = line.eft_payment_id
                if method.get('type') == 7 and eft and eft.signature:
                    method.update({
                        'signature': eft.signature,
                        'signingAuthor': eft.signing_author,
                        'terminalId': eft.terminal_id.code,
                        'transactionId': eft.transaction_id,
                    })
        return payload
