# -*- coding: utf-8 -*-
"""Α.1155/2023 EFT/POS interconnection through the e-invoicing provider.

Terminal registry + provider payment signatures. The signature is issued by
the provider (ILYDA /api/invoice/sign), reaches the card terminal through its
NSP, and after the charge the payment is tied to the document either in the
submit payload (real-time) or via sendPaymentMethods (retrograde).
"""
import logging
from datetime import datetime, timezone

import requests

from odoo import api, fields, models, _
from odoo.exceptions import UserError

from odoo.addons.l10n_gr_provider_ilyda.models.account_move import (
    IlydaClient, TIMEOUT, _r2,
)

_logger = logging.getLogger(__name__)

# NSPProtocol enum (Α.1155 doc §7.7) — decides how the provider constructs
# the signature for the specific terminal vendor.
NSP_PROTOCOLS = [
    ('DEFAULT', 'DEFAULT (EDPS)'),
    ('VIVA', 'Viva'),
    ('CARDLINK', 'Cardlink'),
    ('MELLON', 'Mellon'),
    ('EPAY', 'ePay'),
    ('NEXI', 'Nexi'),
    ('NEOSOFT', 'Neosoft'),
    ('WORLDLINE', 'Worldline'),
    ('ATTICA', 'Attica'),
]

CANCEL_REASONS = [
    ('TRANSACTION_CANCELLED', 'Η πληρωμή ακυρώθηκε (π.χ. πληρώθηκε με μετρητά)'),
    ('TRANSACTION_FAILED', 'Η συναλλαγή απέτυχε (π.χ. timeout τερματικού)'),
    ('TERMINAL_CHANGED', 'Χρησιμοποιήθηκε άλλο τερματικό'),
    ('AMOUNT_CHANGED', 'Άλλαξε το ποσό'),
    ('MARK_CHANGED', 'Ζητήθηκε υπογραφή για λάθος ΜΑΡΚ'),
    ('OTHER', 'Άλλη αιτία (υποχρεωτική περιγραφή)'),
]


class EftIlydaClient(IlydaClient):
    """The Α.1155 signature endpoints, on top of the base ILYDA client."""

    def _post(self, path, body):
        resp = requests.post(
            f'{self.base}{path}',
            json=body, headers=self._headers(), auth=self._auth, timeout=TIMEOUT)
        return self._parse(resp)

    def sign(self, body):
        return self._post('/api/invoice/sign', body)

    def send_payment_methods(self, body):
        return self._post('/api/invoice/sendPaymentMethods', body)

    def cancel_signature(self, body):
        return self._post('/api/invoice/sign/cancel', body)


def _fatal_errors(data):
    return [e for e in (data.get('errors') or []) if e.get('fatal')]


def _format_errors(errors):
    return '; '.join(
        f"{e.get('code')}: {e.get('defaultMessage')}" for e in errors)


class EftTerminal(models.Model):
    _name = 'l10n.gr.prov.eft.terminal'
    _description = 'Τερματικό EFT/POS (Α.1155)'

    name = fields.Char(string='Ονομασία', required=True)
    code = fields.Char(
        string='Terminal ID', required=True,
        help='Ο αναγνωριστικός αριθμός του τερματικού POS (terminalId), '
             'όπως έχει δηλωθεί στον NSP.')
    nsp_protocol = fields.Selection(
        NSP_PROTOCOLS, string='Πρωτόκολλο NSP', required=True, default='DEFAULT',
        help='Ο πάροχος μέσων πληρωμών (NSP) του τερματικού — καθορίζει τον '
             'τρόπο κατασκευής της υπογραφής. Αν δεν είναι γνωστός, DEFAULT.')
    company_id = fields.Many2one(
        'res.company', string='Εταιρεία', required=True,
        default=lambda self: self.env.company)
    active = fields.Boolean(default=True)


class EftPayment(models.Model):
    _name = 'l10n.gr.prov.eft.payment'
    _description = 'Πληρωμή EFT/POS (Α.1155)'
    _order = 'id desc'

    move_id = fields.Many2one(
        'account.move', string='Παραστατικό', required=True, index=True,
        ondelete='restrict',
        domain="[('move_type', 'in', ('out_invoice', 'out_refund')), ('state', '=', 'posted')]")
    company_id = fields.Many2one(related='move_id.company_id', store=True)
    currency_id = fields.Many2one(related='move_id.currency_id')
    partner_id = fields.Many2one(related='move_id.partner_id', string='Πελάτης')
    terminal_id = fields.Many2one(
        'l10n.gr.prov.eft.terminal', string='Τερματικό', required=True,
        domain="[('company_id', '=', company_id)]")
    amount = fields.Monetary(string='Ποσό', currency_field='currency_id', required=True)
    tip_amount = fields.Monetary(string='Φιλοδώρημα', currency_field='currency_id')
    state = fields.Selection([
        ('draft', 'Πρόχειρη'),
        ('signed', 'Με Υπογραφή'),
        ('paid', 'Πληρωμένη'),
        ('submitted', 'Διαβιβασμένη'),
        ('cancelled', 'Ακυρωμένη'),
    ], default='draft', string='Κατάσταση', required=True, copy=False)

    # Signature (InvoiceSignature) as returned by the provider
    signature = fields.Text(string='Υπογραφή Παρόχου', readonly=True, copy=False)
    signing_author = fields.Char(string='Αναγν. ΥΠΑΗΕΣ', readonly=True, copy=False)
    signature_uid = fields.Char(string='UID Υπογραφής', readonly=True, copy=False)
    signed_at = fields.Datetime(string='Έκδοση Υπογραφής', readonly=True, copy=False)
    signature_expiry = fields.Datetime(string='Λήξη Υπογραφής', readonly=True, copy=False)
    signature_expired = fields.Boolean(
        string='Ληγμένη', compute='_compute_signature_expired',
        help='Ανενεργή υπογραφή: αχρησιμοποίητες υπογραφές διαβιβάζονται '
             'αυτόματα στην ΑΑΔΕ ως «Ανοιχτά Παραστατικά» μετά από 24 ώρες.')

    transaction_id = fields.Char(
        string='Ταυτότητα Συναλλαγής', copy=False,
        help='Το transaction id που επιστρέφει το τερματικό μετά τη χρέωση.')
    payment_method_mark = fields.Char(
        string='MARK Πληρωμής', readonly=True, copy=False,
        help='Το paymentMethodMark της ΑΑΔΕ (ετεροχρονισμένη διαβίβαση).')

    cancel_reason = fields.Selection(CANCEL_REASONS, string='Αιτία Ακύρωσης', copy=False)
    cancel_reason_text = fields.Char(string='Περιγραφή Αιτίας', copy=False)

    _sql_constraints = [
        ('amount_positive', 'CHECK(amount > 0)', 'Το ποσό πρέπει να είναι θετικό.'),
    ]

    @api.depends('signature_expiry', 'state')
    def _compute_signature_expired(self):
        now = fields.Datetime.now()
        for pay in self:
            pay.signature_expired = bool(
                pay.state == 'signed'
                and pay.signature_expiry and pay.signature_expiry < now)

    @api.depends('move_id', 'amount')
    def _compute_display_name(self):
        for pay in self:
            pay.display_name = f'{pay.move_id.name or "?"} · {pay.amount:.2f}'

    @api.onchange('move_id')
    def _onchange_move_id(self):
        """Default the amount to what is still unassigned to EFT payments."""
        for pay in self:
            move = pay.move_id
            if not move or pay.amount:
                continue
            assigned = sum(move.l10n_gr_prov_eft_payment_ids.filtered(
                lambda p: p.state != 'cancelled' and p.id != pay._origin.id
            ).mapped('amount'))
            pay.amount = max(move._l10n_gr_prov_payable() - assigned, 0.0)

    # ── Flow ──────────────────────────────────────────────────────────────────
    def _client(self):
        return EftIlydaClient(self.move_id.company_id)

    def action_request_signature(self):
        """Ask the provider for the payment signature (Α.1155 §6.1).

        Retrograde (document already marked): by MARK. Real-time (posted but
        not yet sent): from the document totals. The provider returns an
        existing unexpired unused signature instead of issuing a second one.
        """
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_('Η υπογραφή έχει ήδη ζητηθεί.'))
        move = self.move_id
        if move.state != 'posted':
            raise UserError(_('Το παραστατικό πρέπει πρώτα να καταχωριστεί.'))
        terminal = self.terminal_id
        body = {
            'amount': _r2(self.amount),
            'terminalId': terminal.code,
            'nspProtocol': terminal.nsp_protocol,
        }
        if move.l10n_gr_prov_mark:
            body['mark'] = move.l10n_gr_prov_mark
        else:
            company = move.company_id
            series, _serial = move._l10n_gr_prov_ilyda_series_serial()
            rates = {_r2(t.amount) for t in move.invoice_line_ids.filtered(
                lambda l: not l.display_type).tax_ids}
            body.update({
                'netAmount': _r2(move.amount_untaxed),
                'vatAmount': _r2(move.amount_tax),
                'grossAmount': _r2(move._l10n_gr_prov_payable()),
                # vatRate is only consumed by the VIVA strategy; a mixed-rate
                # document sends 0, like the spec's own examples.
                'vatRate': rates.pop() if len(rates) == 1 else 0,
                'sellerVat': move._ilyda_vat(company.vat, prefixed=False),
                'series': series,
                'invoiceTypeCode': move.l10n_gr_edi_inv_type
                    or move.journal_id.l10n_gr_edi_inv_type_default,
                'sellerBranch': company.partner_id.l10n_gr_edi_branch_number or 0,
            })
        data = self._client().sign(body)
        _logger.info('ILYDA sign response for %s: %s', self.display_name, data)
        fatal = _fatal_errors(data)
        if fatal:
            raise UserError(_('Αποτυχία έκδοσης υπογραφής: %s', _format_errors(fatal)))
        sigs = data.get('invoiceSignatures') or []
        if not sigs:
            raise UserError(_('Ο πάροχος δεν επέστρεψε υπογραφή.'))
        sig = sigs[0]
        self.write({
            'signature': sig.get('signature'),
            'signing_author': sig.get('signingAuthor'),
            'signature_uid': sig.get('uid'),
            'signed_at': self._epoch_to_dt(sig.get('signedAt')),
            'signature_expiry': self._epoch_to_dt(sig.get('signatureExpirationDate')),
            'state': 'signed',
        })
        move.message_post(body=_(
            'Α.1155: εκδόθηκε υπογραφή πληρωμής %(amount)s για το τερματικό '
            '%(terminal)s (λήξη %(expiry)s).',
            amount=f'{self.amount:.2f}', terminal=terminal.display_name,
            expiry=self.signature_expiry or '—'))
        # keep the dialog open on step 2 (charge the terminal, enter the
        # transaction id) — returning nothing would close it
        return self._reopen()

    def _reopen(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Πληρωμή με Κάρτα (Α.1155)'),
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_complete(self):
        """Second dialog step: the card was charged — record the terminal's
        transaction id and finish automatically.

        Retrograde (document already marked): sendPaymentMethods — stores the
        returned paymentMethodMark. Real-time: attach the type-7 payment line
        and run the normal document send (the payload carries signature +
        transactionId).
        """
        self.ensure_one()
        if self.state != 'signed':
            raise UserError(_('Χρειάζεται πρώτα υπογραφή παρόχου.'))
        if not self.transaction_id:
            raise UserError(_(
                'Συμπληρώστε την Ταυτότητα Συναλλαγής από το τερματικό.'))
        self.state = 'paid'
        if self.move_id.l10n_gr_prov_mark:
            self._submit_retrograde()
        else:
            self._submit_realtime()

    def _payment_method_dict(self):
        return {
            'type': 7,
            'amount': _r2(self.amount),
            **({'tipAmount': _r2(self.tip_amount)} if self.tip_amount else {}),
            'terminalId': self.terminal_id.code,
            'signature': self.signature,
            'signingAuthor': self.signing_author,
            'transactionId': self.transaction_id,
        }

    def _submit_retrograde(self):
        move = self.move_id
        if not move.l10n_gr_prov_invoice_id:
            raise UserError(_(
                'Το παραστατικό δεν έχει αναγνωριστικό παρόχου (invoiceId) — '
                'η διαβίβαση τρόπων πληρωμής δεν είναι δυνατή.'))
        data = self._client().send_payment_methods({
            'invoiceId': move.l10n_gr_prov_invoice_id,
            'paymentMethods': [self._payment_method_dict()],
        })
        _logger.info('ILYDA sendPaymentMethods response for %s: %s',
                     self.display_name, data)
        fatal = _fatal_errors(data)
        if fatal:
            raise UserError(_(
                'Αποτυχία διαβίβασης πληρωμής: %s', _format_errors(fatal)))
        submitted = ((data.get('submittedPaymentMethods') or [])
                     + (data.get('previouslySubmittedPaymentMethods') or []))
        entry = next((p for p in submitted
                      if p.get('transactionId') == self.transaction_id), None)
        self.write({
            'payment_method_mark': entry and entry.get('paymentMethodMark'),
            'state': 'submitted',
        })
        self._sync_move_payment_line()
        move.message_post(body=_(
            'Α.1155: διαβιβάστηκε πληρωμή POS %(amount)s — MARK πληρωμής %(mark)s.',
            amount=f'{self.amount:.2f}',
            mark=self.payment_method_mark or '—'))

    def _submit_realtime(self):
        move = self.move_id
        self._sync_move_payment_line()
        move.action_l10n_gr_prov_send()
        # sent or queued (TF-2) both mean the provider holds the payment data
        if move.l10n_gr_prov_state in ('sent', 'queued'):
            self.state = 'submitted'

    def _sync_move_payment_line(self):
        """Mirror this payment onto the move's myDATA type-7 payment line, so
        the ILYDA payload (and the Κατάσταση tab) show the real methods."""
        self.ensure_one()
        move = self.move_id
        line = move.l10n_gr_prov_payment_ids.filtered(
            lambda p: p.eft_payment_id == self)
        vals = {
            'payment_type': '7',
            'amount': self.amount,
            'tip_amount': self.tip_amount,
            'transaction_id': self.transaction_id,
            'eft_payment_id': self.id,
        }
        if line:
            line[0].write(vals)
            return
        # adopt a hand-made POS line without an EFT link (same amount) —
        # e.g. the default seeded line the user switched to type 7
        orphan = move.l10n_gr_prov_payment_ids.filtered(
            lambda p: p.payment_type == '7' and not p.eft_payment_id
            and _r2(p.amount) == _r2(self.amount))
        if orphan:
            orphan[0].write(vals)
        else:
            move.l10n_gr_prov_payment_ids = [(0, 0, vals)]

    def action_cancel(self):
        """Cancel the provider signature (customer paid cash, terminal failed,
        wrong amount...). A used signature cannot be cancelled."""
        self.ensure_one()
        if self.state == 'submitted':
            raise UserError(_(
                'Η πληρωμή έχει διαβιβαστεί — η υπογραφή δεν ακυρώνεται.'))
        if self.state in ('signed', 'paid') and self.signature:
            if not self.cancel_reason:
                raise UserError(_('Επιλέξτε Αιτία Ακύρωσης.'))
            if self.cancel_reason == 'OTHER' and not self.cancel_reason_text:
                raise UserError(_(
                    'Για αιτία «Άλλη» απαιτείται η Περιγραφή Αιτίας.'))
            data = self._client().cancel_signature({
                'signature': self.signature,
                'signatureCancelReason': self.cancel_reason,
                **({'signatureCancelReasonText': self.cancel_reason_text}
                   if self.cancel_reason_text else {}),
            })
            fatal = _fatal_errors(data)
            if fatal:
                raise UserError(_(
                    'Αποτυχία ακύρωσης υπογραφής: %s', _format_errors(fatal)))
            self.move_id.message_post(body=_(
                'Α.1155: ακυρώθηκε υπογραφή πληρωμής %(amount)s (%(reason)s).',
                amount=f'{self.amount:.2f}',
                reason=dict(CANCEL_REASONS)[self.cancel_reason]))
        self.state = 'cancelled'

    def unlink(self):
        if any(p.state not in ('draft', 'cancelled') for p in self):
            raise UserError(_(
                'Διαγράφονται μόνο πρόχειρες ή ακυρωμένες πληρωμές — '
                'χρησιμοποιήστε την Ακύρωση Υπογραφής.'))
        return super().unlink()

    @staticmethod
    def _epoch_to_dt(value):
        """Provider timestamps are epoch millis; ISO strings just in case."""
        if not value:
            return False
        try:
            return datetime.fromtimestamp(
                float(value) / 1000, tz=timezone.utc).replace(tzinfo=None)
        except (TypeError, ValueError):
            try:
                return fields.Datetime.to_datetime(str(value)[:19].replace('T', ' '))
            except ValueError:
                return False


class L10nGrProvPayment(models.Model):
    _inherit = 'l10n.gr.prov.payment'

    eft_payment_id = fields.Many2one(
        'l10n.gr.prov.eft.payment', string='Πληρωμή EFT/POS',
        readonly=True, copy=False, ondelete='set null')
