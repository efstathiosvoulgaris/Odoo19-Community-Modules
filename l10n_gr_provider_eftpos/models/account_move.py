# -*- coding: utf-8 -*-
from odoo import fields, models, _
from odoo.exceptions import UserError


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

    def _l10n_gr_prov_eft_hold(self):
        """Why this document must not reach the provider yet, or False.

        The interception above only guards the button. The retry cron (auto
        send), Send & Print and the POS all transmit through _try_send
        directly — and did so while the card dialog was still open, putting
        the document at AADE without its Α.1155 signature or transaction id.
        """
        self.ensure_one()
        # Not 'draft': an abandoned dialog signed nothing and would hold the
        # document forever; its card line is caught as unsigned below.
        pending = self.l10n_gr_prov_eft_payment_ids.filtered(
            lambda p: p.state in ('signed', 'charging'))
        if pending:
            return _(
                'Εκκρεμεί πληρωμή με κάρτα (Α.1155) σε κατάσταση «%(state)s» — '
                'το παραστατικό διαβιβάζεται μόλις ολοκληρωθεί ή ακυρωθεί.',
                state=dict(pending[0]._fields['state'].selection)[pending[0].state])
        # A POS invoice carries what the till charged; whether an unsigned card
        # line is acceptable there is the till's setting, not ours.
        if 'pos_order_ids' in self._fields and self.pos_order_ids:
            return False
        unsigned = self.l10n_gr_prov_payment_ids.filtered(
            lambda p: p.payment_type == '7' and not p.eft_payment_id)
        if unsigned and self.env['l10n.gr.prov.eft.terminal'].search_count(
                [('company_id', '=', self.company_id.id)], limit=1):
            return _(
                'Η πληρωμή με κάρτα δεν έχει υπογραφή Α.1155 — πατήστε «Send to '
                'Provider» για να ολοκληρωθεί η πληρωμή στο τερματικό.')
        return False

    def _l10n_gr_prov_try_send(self, raise_on_error=False):
        """Hold the document while its card payment is unsettled.

        Nothing is written to the state: the document stays «to send» and goes
        out, signature included, once the payment is done. The reason is shown
        on the document, posted to the chatter only when it changes, so the
        hourly cron does not repeat it.
        """
        reason = self._l10n_gr_prov_eft_hold()
        if not reason:
            return super()._l10n_gr_prov_try_send(raise_on_error=raise_on_error)
        if raise_on_error:
            raise UserError(reason)
        if self.l10n_gr_prov_error != reason:
            self.l10n_gr_prov_error = reason
            self.message_post(body=reason)
        return None

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
