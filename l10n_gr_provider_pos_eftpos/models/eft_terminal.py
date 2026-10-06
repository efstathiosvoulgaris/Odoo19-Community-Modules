# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError

from odoo.addons.l10n_gr_provider_eftpos.models.eft import (
    EftIlydaClient, _fatal_errors, _format_errors,
)
from odoo.addons.l10n_gr_provider_ilyda.models.account_move import _r2

_logger = logging.getLogger(__name__)

# pos.session states in which a till is actually open
OPEN_SESSION_STATES = ('opening_control', 'opened', 'closing_control')


class L10nGrProvEftPayment(models.Model):
    """POS card charges live in the same ledger as backend ones.

    Every attempt at the payment screen becomes a record BEFORE the card is
    charged, keyed by a uuid the till chose. The terminal's answer is committed
    on it the moment it arrives, so a charge survives anything that goes wrong
    afterwards — a proxy timing out, the worker being killed, the browser
    closing — and the till can ask what happened instead of charging again.
    Stuck charges show up in the back office list with everything else.
    """
    _inherit = 'l10n.gr.prov.eft.payment'

    pos_config_id = fields.Many2one(
        'pos.config', string='Ταμείο POS', readonly=True, copy=False, index=True)
    pos_client_key = fields.Char(
        string='Κλειδί Ταμείου', readonly=True, copy=False, index=True,
        help='Μοναδικό ανά προσπάθεια χρέωσης στο ταμείο. Αν χαθεί η απάντηση, '
             'το ταμείο ρωτά με αυτό τι έγινε, αντί να χρεώσει ξανά.')

    _pos_client_key_uniq = models.Constraint(
        'UNIQUE(pos_client_key)',
        'Το κλειδί προσπάθειας του ταμείου υπάρχει ήδη.',
    )

    def _is_pos_charge(self):
        return bool(self.pos_config_id)

    def _l10n_gr_prov_origin_label(self):
        if not self.move_id and self.pos_config_id:
            return _('POS %s', self.pos_config_id.name)
        return super()._l10n_gr_prov_origin_label()

    def _l10n_gr_prov_pos_result(self):
        """What the till needs to know about this attempt, by state.

        status: approved (charged by the driver) · signed (charge the terminal
        by hand) · pending (outcome unknown — do NOT charge again) · cancelled
        (nothing charged, or charged and given back).
        """
        self.ensure_one()
        result = {
            'client_key': self.pos_client_key,
            'signature': self.signature,
            'signing_author': self.signing_author,
            'terminal_code': self.terminal_id.code,
        }
        if self.state == 'paid' and self.transaction_id:
            result.update(status='approved', transaction_id=self.transaction_id)
        elif self.state == 'signed' and not self.driver_response_code:
            result['status'] = 'signed'
        elif self.state in ('charging', 'paid'):
            # 'paid' without a transaction id: approved but unusable, and the
            # void that should have followed did not go through.
            result.update(status='pending', error=self.driver_message or _(
                'Άγνωστη έκβαση της χρέωσης.'))
        else:
            result.update(status='cancelled', error=self.driver_message or _(
                'Η χρέωση δεν ολοκληρώθηκε.'))
        return result

    def _l10n_gr_prov_pos_release(self, reason=False):
        """Give back whatever this attempt holds: void an approved charge,
        cancel the signature. Never raises; returns an error text or False."""
        self.ensure_one()
        if self.state in ('cancelled', 'submitted'):
            return False
        try:
            self.cancel_reason = 'TRANSACTION_CANCELLED'
            self.action_cancel()
        except Exception as e:
            _logger.warning('Α.1155 POS release of %s failed: %s', self.display_name, e)
            return str(e)
        if reason:
            self.driver_message = reason
        return False


class L10nGrProvEftTerminal(models.Model):
    _inherit = 'l10n.gr.prov.eft.terminal'

    # ── Access ────────────────────────────────────────────────────────────────

    @api.model
    def _l10n_gr_prov_pos_config(self, vals):
        """The till a POS call acts for — only for a POS user with a session
        open on it. Everything after this runs as sudo: the charge ledger and
        the provider credentials are not something a cashier reads directly."""
        if not self.env.user.has_group('point_of_sale.group_pos_user'):
            raise AccessError(_('Μόνο χρήστες POS.'))
        config = self.env['pos.config'].browse(int(vals.get('config_id') or 0)).exists()
        if not config or not self.env['pos.session'].sudo().search_count([
                ('config_id', '=', config.id),
                ('state', 'in', OPEN_SESSION_STATES)]):
            raise AccessError(_('Δεν υπάρχει ανοιχτή βάρδια σε αυτό το ταμείο.'))
        return config.sudo()

    @api.model
    def _l10n_gr_prov_pos_attempt(self, config, client_key):
        if not client_key:
            return self.env['l10n.gr.prov.eft.payment']
        payment = self.env['l10n.gr.prov.eft.payment'].sudo().search(
            [('pos_client_key', '=', client_key)], limit=1)
        if payment and payment.pos_config_id != config:
            raise AccessError(_('Η χρέωση ανήκει σε άλλο ταμείο.'))
        return payment

    # ── Calls from the payment screen ─────────────────────────────────────────

    @api.model
    def l10n_gr_prov_pos_sign(self, vals):
        """Sign — and, with the MegEftPos Driver, charge — one POS card line.

        `vals`: config_id, client_key (uuid of this attempt), terminal_id (the
        cashier's pick; the till's default when absent), amount, net, vat,
        gross, vat_rate, is_timologio, is_refund, refunded_order_id (the
        order a return gives back), installments — amounts always positive,
        like the document.

        Idempotent on client_key: calling it again for an attempt that already
        exists never signs or charges twice, it reports that attempt. So a till
        that lost the answer can simply ask again.

        Returns the attempt's status (see _l10n_gr_prov_pos_result), or
        {'status': 'error', 'error': …} when nothing was signed.
        """
        config = self._l10n_gr_prov_pos_config(vals)
        existing = self._l10n_gr_prov_pos_attempt(config, vals.get('client_key'))
        if existing:
            return existing._l10n_gr_prov_pos_result()
        allowed = config._l10n_gr_prov_eft_terminals()
        if not allowed:
            return {'status': 'error', 'error': _(
                'Δεν έχει οριστεί τερματικό EFT/POS στο POS (Ρυθμίσεις → '
                'Πάροχος myDATA → Τερματικό Α.1155).')}
        # The till says which terminal the customer is paying on; only one
        # this till is set up for is accepted.
        terminal = allowed[:1]
        if vals.get('terminal_id'):
            terminal = allowed.filtered(lambda t: t.id == int(vals['terminal_id']))
            if not terminal:
                return {'status': 'error', 'error': _(
                    'Το τερματικό δεν είναι ρυθμισμένο για αυτό το ταμείο.')}
        company = terminal.company_id
        journal = self._l10n_gr_prov_pos_sign_journal(config, vals)
        if not journal:
            return {'status': 'error', 'error': _(
                'Δεν έχει οριστεί ημερολόγιο ΑΛΠ/ΤΙΜ/ΠΛΠ στο POS.')}
        net, vat, gross = (_r2(vals.get(k) or 0) for k in ('net', 'vat', 'gross'))
        body = {
            'amount': _r2(vals['amount']),
            'terminalId': terminal.code,
            'nspProtocol': terminal.nsp_protocol,
            'netAmount': net,
            'vatAmount': vat,
            'grossAmount': gross,
            'vatRate': _r2(vals.get('vat_rate') or 0),
            'sellerVat': self.env['account.move']._ilyda_vat(
                company.vat, prefixed=False),
            'series': journal.code,
            'invoiceTypeCode': journal.l10n_gr_edi_inv_type_default,
            'sellerBranch': company.partner_id.l10n_gr_edi_branch_number or 0,
        }
        try:
            data = EftIlydaClient(company).sign(body)
        except Exception as e:
            return {'status': 'error', 'error': str(e)}
        fatal = _fatal_errors(data)
        if fatal:
            return {'status': 'error', 'error': _format_errors(fatal)}
        sigs = data.get('invoiceSignatures') or []
        if not sigs:
            return {'status': 'error', 'error': _('Ο πάροχος δεν επέστρεψε υπογραφή.')}
        sig = sigs[0]
        Payment = self.env['l10n.gr.prov.eft.payment']
        payment = Payment.sudo().create({
            'terminal_id': terminal.id,
            'pos_config_id': config.id,
            'pos_client_key': vals.get('client_key') or False,
            'amount': _r2(vals['amount']),
            'installments': int(vals.get('installments') or 0),
            'signature': sig.get('signature'),
            'signing_author': sig.get('signingAuthor'),
            'signature_uid': sig.get('uidHash') or sig.get('uid'),
            'signed_at': Payment._epoch_to_dt(sig.get('signedAt')),
            'signature_expiry': Payment._epoch_to_dt(sig.get('signatureExpirationDate')),
            'signed_content': sig.get('signedContent'),
            'signature_amount': sig.get('amount') or _r2(vals['amount']),
            'signature_net': sig.get('netAmount') or net,
            'signature_vat': sig.get('vatAmount') or vat,
            'signature_gross': sig.get('grossAmount') or gross,
            'state': 'signed',
        })
        # The provider holds this signature now; losing the record would leave
        # it to become an «Ανοιχτό Παραστατικό».
        payment._commit()
        driver = terminal._l10n_gr_prov_driver_enabled()
        if driver and vals.get('is_refund'):
            # A driver Refund must quote the original sale's ecr/nsp/bankAuth/
            # receipt references. The till sends the order being returned;
            # its card charge is found here, never taken from the browser.
            payment.origin_payment_id = self._l10n_gr_prov_pos_refund_origin(
                terminal, vals)
        if not driver or (vals.get('is_refund') and not payment.origin_payment_id):
            # Standalone terminal — or a return whose sale has no single card
            # charge on this terminal to reverse (cash sale, split cards,
            # another terminal, a return typed in by hand): the cashier
            # charges it and types the id. Α.1155 only requires the signature,
            # which this path issues.
            return payment._l10n_gr_prov_pos_result()
        try:
            payment.action_charge_terminal()
        except UserError as e:
            # Refused before a transaction existed (driver unreachable, bad
            # configuration): nothing charged, release the signature.
            error = payment._l10n_gr_prov_pos_release(str(e))
            return {'status': 'error', 'error': error or str(e)}
        if payment.state == 'paid' and not payment.transaction_id:
            # Approved, but without the nspReferenceNumber AADE needs as the
            # transaction id: the charge can never be declared — and a Void
            # needs that very reference, so it cannot be given back from here
            # either. Releasing only the signature would leave the money taken
            # with nothing on record. Keep it, flagged for a human.
            payment.submit_error = _(
                'Το τερματικό ενέκρινε τη χρέωση χωρίς nspReferenceNumber — δεν '
                'μπορεί ούτε να διαβιβαστεί ούτε να ακυρωθεί αυτόματα. '
                'Ακυρώστε τη συναλλαγή στο τερματικό και μετά την πληρωμή εδώ.')
            payment._commit()
            return dict(payment._l10n_gr_prov_pos_result(), error=payment.submit_error)
        elif payment.state == 'signed':
            # Declined: nothing charged; this signature will not be used.
            payment._l10n_gr_prov_pos_release()
        return payment._l10n_gr_prov_pos_result()

    @api.model
    def l10n_gr_prov_pos_status(self, vals):
        """What became of an attempt the till lost the answer to. Never
        charges. {'status': 'unknown'} when no such attempt was recorded —
        it may still be signing; ask again shortly."""
        config = self._l10n_gr_prov_pos_config(vals)
        payment = self._l10n_gr_prov_pos_attempt(config, vals.get('client_key'))
        if not payment:
            return {'status': 'unknown', 'client_key': vals.get('client_key')}
        return payment._l10n_gr_prov_pos_result()

    @api.model
    def l10n_gr_prov_pos_recover(self, vals):
        """«Ανάκτηση» from the till: ask the driver about a pending attempt."""
        config = self._l10n_gr_prov_pos_config(vals)
        payment = self._l10n_gr_prov_pos_attempt(config, vals.get('client_key'))
        if not payment:
            return {'status': 'unknown', 'client_key': vals.get('client_key')}
        try:
            payment.action_recover_pending()
        except UserError as e:
            return dict(payment._l10n_gr_prov_pos_result(), error=str(e))
        return payment._l10n_gr_prov_pos_result()

    @api.model
    def l10n_gr_prov_pos_release(self, vals):
        """Give an attempt back: void the charge if the driver made one, and
        cancel the signature. For a validation that is abandoned or a card line
        the cashier removes. The references come from the server-side record,
        never from the browser.

        Returns {'ok': True, 'voided': bool} or {'error': …}. `voided` False
        on a line the cashier charged by hand: only the signature could be
        released, the money has to be reversed on the terminal.
        """
        config = self._l10n_gr_prov_pos_config(vals)
        payment = self._l10n_gr_prov_pos_attempt(config, vals.get('client_key'))
        if not payment:
            return {'error': _('Δεν βρέθηκε η χρέωση.')}
        if payment.state == 'charging':
            return {'error': _(
                'Η έκβαση της χρέωσης είναι άγνωστη — κάντε πρώτα «Ανάκτηση».')}
        error = payment._l10n_gr_prov_pos_release()
        if error:
            return {'error': error}
        return {'ok': True, 'voided': bool(payment.voided_at)}

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _l10n_gr_prov_pos_refund_origin(self, terminal, vals):
        """The card charge a POS return gives back, or an empty recordset.

        Only an unambiguous one: the returned order's single approved card
        charge, made on this very terminal, covering at least the amount
        going back. Anything else — no charge, two cards, another terminal —
        is left to the manual path rather than refunding against a guess.
        """
        Payment = self.env['l10n.gr.prov.eft.payment']
        order = self.env['pos.order'].sudo().browse(
            int(vals.get('refunded_order_id') or 0)).exists()
        if not order.account_move or order.company_id != terminal.company_id:
            return Payment
        charges = Payment.sudo().search([
            ('move_id', '=', order.account_move.id),
            ('driver_response_code', '=', 'APPROVED'),
            ('nsp_reference', '!=', False),
            ('voided_at', '=', False),
        ])
        if len(charges) != 1 or charges.terminal_id != terminal \
                or _r2(charges.amount) < _r2(vals.get('amount') or 0):
            return Payment
        return charges

    def _l10n_gr_prov_pos_sign_journal(self, config, vals):
        """The series the signature is issued against.

        A return is a credit document with its own series — ΠΛΠ 11.4 for
        retail, ΠΙΣΤ 5.1 for a ΤΙΜ — never the sale journal, mirroring
        `pos.order._l10n_gr_prov_pos_journal()`.
        """
        is_timologio = bool(vals.get('is_timologio'))
        if not vals.get('is_refund'):
            return (config.l10n_gr_prov_tim_journal_id if is_timologio
                    else config.l10n_gr_prov_alp_journal_id)
        if not is_timologio and config.l10n_gr_prov_pla_journal_id:
            return config.l10n_gr_prov_pla_journal_id
        return self.env['account.journal'].sudo().search([
            ('company_id', '=', config.company_id.id),
            ('type', '=', 'sale'),
            ('l10n_gr_edi_inv_type_default', '=', '5.1' if is_timologio else '11.4'),
            ('l10n_gr_prov_delivery_note', '=', False),
        ], limit=1)
