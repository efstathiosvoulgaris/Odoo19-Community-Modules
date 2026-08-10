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
from .eft_driver import (
    MegEftPosDriver, POS_PROTOCOLS, RESPONSE_CODES, PAYMENT_METHODS,
    PROTOCOLS_NEED_HOST, PROTOCOLS_NEED_API_KEY, PROTOCOLS_NEED_CLIENT,
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

    # ── MegEftPos driver (Α.1155 automatic charging) ─────────────────────────
    # nsp_protocol above is ILYDA's signature hint; pos_protocol is the driver's
    # own enum for reaching the terminal. They are related but not the same
    # list, so both are kept.
    driver_url = fields.Char(
        string='MegEftPos Driver URL',
        help='Διεύθυνση του MegEftPosRestServices ΓΙΑ ΑΥΤΟ το τερματικό, π.χ. '
             'http://192.168.1.50:8187. Κενό = χρησιμοποιείται η γενική '
             'διεύθυνση της εταιρείας. Ορίστε το όταν κάθε ταμείο έχει τον '
             'δικό του driver, ή όταν η Odoo δεν τρέχει στο PC του ταμείου.')
    pos_protocol = fields.Selection(
        POS_PROTOCOLS, string='Πρωτόκολλο Driver',
        help='Πρωτόκολλο επικοινωνίας του MegEftPos Driver με το τερματικό. '
             'Κενό = το τερματικό χρεώνεται χειροκίνητα.')
    host = fields.Char(
        string='IP Τερματικού',
        help='Απαιτείται για Cardlink / EDPS / Nexi TCP.')
    port = fields.Integer(
        string='Port Τερματικού',
        help='Απαιτείται για Cardlink / EDPS / Nexi TCP.')
    api_key = fields.Char(
        string='API Key (WebECR)', groups='base.group_system',
        help='Απαιτείται για Mellon / ePay / Nexi / Attica / Worldline. '
             'Λαμβάνεται με εξαργύρωση του OTP που εμφανίζει το τερματικό.')
    client_id = fields.Char(
        string='Client ID (Viva)',
        help='Από το POS APIs Credentials του Viva portal.')
    client_secret = fields.Char(
        string='Client Secret (Viva)', groups='base.group_system')
    otp = fields.Char(
        string='OTP Τερματικού', copy=False,
        help='Ο εξαψήφιος κωδικός που εμφανίζει το τερματικό· εξαργυρώνεται '
             'μία φορά για να παραχθεί το API Key.')

    # Which extra fields this protocol needs — drives the form and the guard.
    needs_host = fields.Boolean(compute='_compute_protocol_needs')
    needs_api_key = fields.Boolean(compute='_compute_protocol_needs')
    needs_client = fields.Boolean(compute='_compute_protocol_needs')

    @api.depends('pos_protocol')
    def _compute_protocol_needs(self):
        for terminal in self:
            protocol = terminal.pos_protocol
            terminal.needs_host = protocol in PROTOCOLS_NEED_HOST
            terminal.needs_api_key = protocol in PROTOCOLS_NEED_API_KEY
            terminal.needs_client = protocol in PROTOCOLS_NEED_CLIENT

    def _l10n_gr_prov_driver_url(self):
        """Where this terminal's driver lives.

        The driver runs on the till PC and Odoo calls it server-side, so the
        address is only ever «localhost» when Odoo runs on that same PC. One
        address per company therefore only works for a single-till, all-on-one-
        box install; anything else — a second till, or Odoo on a server —
        needs the address per terminal. The company field stays as the default
        so existing single-till setups keep working untouched.
        """
        self.ensure_one()
        return self.driver_url or self.company_id.l10n_gr_prov_eft_driver_url

    def _l10n_gr_prov_driver_enabled(self):
        """True when this terminal can be charged by the driver."""
        self.ensure_one()
        return bool(self.pos_protocol and self._l10n_gr_prov_driver_url())

    def _l10n_gr_prov_pos_device(self):
        """The PosDevice structure the driver expects."""
        self.ensure_one()
        if not self.pos_protocol:
            raise UserError(_(
                'Το τερματικό %s δεν έχει πρωτόκολλο driver.', self.display_name))
        device = {'terminalId': self.code, 'posProtocol': self.pos_protocol}
        if self.needs_host:
            if not (self.host and self.port):
                raise UserError(_(
                    'Το πρωτόκολλο %s απαιτεί IP και port τερματικού.',
                    self.pos_protocol))
            device['host'] = self.host
            device['port'] = self.port
        if self.needs_api_key:
            api_key = self.sudo().api_key
            if not api_key:
                raise UserError(_(
                    'Το πρωτόκολλο %s απαιτεί API Key — εξαργυρώστε το OTP '
                    'του τερματικού.', self.pos_protocol))
            device['apiKey'] = api_key
        if self.needs_client:
            terminal = self.sudo()
            if not (terminal.client_id and terminal.client_secret):
                raise UserError(_(
                    'Το Viva Cloud απαιτεί Client ID και Client Secret.'))
            device['clientId'] = terminal.client_id
            # The driver spells this field «clientSecter» (sic, v2.1.5).
            device['clientSecter'] = terminal.client_secret
        return device

    def action_redeem_otp(self):
        """Exchange the terminal's OTP for the WebECR API key."""
        self.ensure_one()
        if not self.otp:
            raise UserError(_('Καταχωρίστε το OTP που εμφανίζει το τερματικό.'))
        data = MegEftPosDriver(self.company_id, self).redeem_otp(
            self._l10n_gr_prov_pos_device_for_otp(), self.otp)
        api_key = (data or {}).get('apiKey')
        if not api_key:
            raise UserError(_('Ο driver δεν επέστρεψε API Key.'))
        self.sudo().write({'api_key': api_key, 'otp': False})

    def _l10n_gr_prov_pos_device_for_otp(self):
        """The OTP exchange is what PRODUCES the api key, so it cannot require
        one — send the device without it."""
        self.ensure_one()
        device = {'terminalId': self.code, 'posProtocol': self.pos_protocol}
        if self.needs_host and self.host and self.port:
            device['host'] = self.host
            device['port'] = self.port
        return device


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
    move_type = fields.Selection(related='move_id.move_type')
    partner_id = fields.Many2one(related='move_id.partner_id', string='Πελάτης')
    terminal_id = fields.Many2one(
        'l10n.gr.prov.eft.terminal', string='Τερματικό', required=True,
        domain="[('company_id', '=', company_id)]")
    amount = fields.Monetary(string='Ποσό', currency_field='currency_id', required=True)
    tip_amount = fields.Monetary(string='Φιλοδώρημα', currency_field='currency_id')
    installments = fields.Integer(
        string='Δόσεις', default=0,
        help='Πλήθος δόσεων για τη χρέωση της κάρτας. 0 ή 1 = εφάπαξ. '
             'Υποστηρίζεται μόνο από όσους NSP προσφέρουν δόσεις.')
    payment_method = fields.Selection(
        PAYMENT_METHODS, string='Μέσο Πληρωμής', required=True,
        default='BANK_CARD', copy=False,
        help='Τι προεπιλέγεται στο τερματικό: κάρτα ή IRIS (το τερματικό '
             'εμφανίζει QR στον πελάτη). Και τα δύο είναι συναλλαγές EFT/POS '
             'και διαβιβάζονται ως τρόπος πληρωμής τύπου 7.\n'
             'Προσοχή: η προεπιλογή δεν υποστηρίζεται από όλους τους NSP — αν '
             'δεν υποστηρίζεται, το τερματικό εμφανίζει όλες τις επιλογές και '
             'ο πελάτης επιλέγει επιτόπου.')
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
    signature_uid = fields.Char(
        string='UID Υπογραφής (hash)', readonly=True, copy=False,
        help='Το uidHash της υπογραφής — το SHA-1 του uid, που είναι και το '
             'πρώτο πεδίο του signedContent. Ο driver το περιμένει ως '
             'providerUid.')
    signed_at = fields.Datetime(string='Έκδοση Υπογραφής', readonly=True, copy=False)
    signature_expiry = fields.Datetime(string='Λήξη Υπογραφής', readonly=True, copy=False)
    signature_expired = fields.Boolean(
        string='Ληγμένη', compute='_compute_signature_expired',
        help='Ανενεργή υπογραφή: αχρησιμοποίητες υπογραφές διαβιβάζονται '
             'αυτόματα στην ΑΑΔΕ ως «Ανοιχτά Παραστατικά» μετά από 24 ώρες.')

    signed_content = fields.Char(
        string='Υπογεγραμμένο Περιεχόμενο', readonly=True, copy=False,
        help='Η συμβολοσειρά που υπέγραψε ο πάροχος (signedContent). '
             'Διαβιβάζεται στον MegEftPos Driver ως providerInput.')

    # What the provider actually signed for. Α.1155 §5.3 ties the signature to
    # both an amount ceiling and the document's own totals, and neither can be
    # re-derived later: signedContent orders these fields differently per NSP.
    signature_amount = fields.Monetary(
        string='Ποσό Υπογραφής', currency_field='currency_id',
        readonly=True, copy=False,
        help='Το πληρωτέο για το οποίο εκδόθηκε η υπογραφή. Η πληρωμή δεν '
             'επιτρέπεται να το ξεπερνά.')
    signature_net = fields.Monetary(
        currency_field='currency_id', readonly=True, copy=False)
    signature_vat = fields.Monetary(
        currency_field='currency_id', readonly=True, copy=False)
    signature_gross = fields.Monetary(
        currency_field='currency_id', readonly=True, copy=False)

    transaction_id = fields.Char(
        string='Ταυτότητα Συναλλαγής', copy=False,
        help='Το transaction id που διαβιβάζεται στην ΑΑΔΕ. Με τον MegEftPos '
             'Driver είναι το nspReferenceNumber της συναλλαγής· χωρίς driver '
             'το καταχωρεί ο χειριστής από το τερματικό.')

    # ── MegEftPos driver result ──────────────────────────────────────────────
    driver_response_code = fields.Selection(
        RESPONSE_CODES, string='Απάντηση Τερματικού', readonly=True, copy=False)
    driver_message = fields.Char(
        string='Μήνυμα NSP', readonly=True, copy=False)
    preloaded_at = fields.Datetime(
        string='Προφορτώθηκε', readonly=True, copy=False,
        help='Πότε στάλθηκε η υπογραφή στο τερματικό ώστε ο πελάτης να '
             'πληρώσει αργότερα (ετεροχρονισμένη συναλλαγή, Α.1155 §4).')
    paid_amount = fields.Monetary(
        string='Ποσό που Χρεώθηκε', currency_field='currency_id',
        readonly=True, copy=False,
        help='Το paidAmount που επέστρεψε το τερματικό. Αν διαφέρει από το '
             'ζητούμενο ποσό, αυτό είναι που πραγματικά χρεώθηκε στην κάρτα.')
    original_amount = fields.Monetary(
        string='Αρχικό Ποσό POS', currency_field='currency_id',
        readonly=True, copy=False)
    ecr_reference = fields.Char(
        string='ECR Reference', readonly=True, copy=False,
        help='Μοναδικός κωδικός συναλλαγής του driver — με αυτόν αναζητείται '
             'η συναλλαγή στην τράπεζα και ανακτάται μια διακοπείσα χρέωση.')
    nsp_reference = fields.Char(
        string='NSP Reference', readonly=True, copy=False)
    bank_auth_code = fields.Char(
        string='Κωδικός Έγκρισης Τράπεζας', readonly=True, copy=False)
    receipt_number = fields.Char(
        string='Αριθμός Απόδειξης POS', readonly=True, copy=False)
    card_type = fields.Char(string='Τύπος Κάρτας', readonly=True, copy=False)
    card_number = fields.Char(string='Κάρτα', readonly=True, copy=False)
    driver_enabled = fields.Boolean(
        compute='_compute_driver_enabled',
        help='Το τερματικό μπορεί να χρεωθεί αυτόματα από τον driver.')
    origin_payment_id = fields.Many2one(
        'l10n.gr.prov.eft.payment', string='Αρχική Χρέωση', copy=False,
        help='Η χρέωση κάρτας που επιστρέφεται. Σε πιστωτικό συμπληρώνεται '
             'από το αρχικό παραστατικό — ο driver χρειάζεται τους κωδικούς '
             'της για να εκτελέσει Refund.')
    payment_method_mark = fields.Char(
        string='MARK Πληρωμής', readonly=True, copy=False,
        help='Το paymentMethodMark της ΑΑΔΕ (ετεροχρονισμένη διαβίβαση).')

    cancel_reason = fields.Selection(CANCEL_REASONS, string='Αιτία Ακύρωσης', copy=False)
    cancel_reason_text = fields.Char(string='Περιγραφή Αιτίας', copy=False)

    _amount_positive = models.Constraint(
        'CHECK(amount > 0)',
        'Το ποσό πρέπει να είναι θετικό.',
    )

    @api.depends('terminal_id')
    def _compute_driver_enabled(self):
        for pay in self:
            pay.driver_enabled = bool(
                pay.terminal_id and pay.terminal_id._l10n_gr_prov_driver_enabled())

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
        """Default the amount to what is still unassigned to EFT payments, and
        on a credit note point at the charge it reverses."""
        for pay in self:
            move = pay.move_id
            if not move:
                continue
            if not pay.amount:
                assigned = sum(move.l10n_gr_prov_eft_payment_ids.filtered(
                    lambda p: p.state != 'cancelled' and p.id != pay._origin.id
                ).mapped('amount'))
                pay.amount = max(move._l10n_gr_prov_payable() - assigned, 0.0)
            if move.move_type == 'out_refund' and not pay.origin_payment_id:
                pay.origin_payment_id = move.reversed_entry_id \
                    .l10n_gr_prov_eft_payment_ids.filtered(
                        lambda p: p.driver_response_code == 'APPROVED')[:1]

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
                lambda l: l.display_type == 'product').tax_ids}
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
            # providerUid must be the uidHash, not the uid: every driver
            # example has providerUid == the first segment of providerInput,
            # which is the SHA-1 hash. Fall back to uid if the provider omits it.
            'signature_uid': sig.get('uidHash') or sig.get('uid'),
            'signed_at': self._epoch_to_dt(sig.get('signedAt')),
            'signature_expiry': self._epoch_to_dt(sig.get('signatureExpirationDate')),
            # The string the provider actually signed. The terminal driver
            # needs it as providerInput, and it is only ever returned here.
            'signed_content': sig.get('signedContent'),
            # what this signature is bound to — checked again before it is used
            'signature_amount': sig.get('amount') or 0.0,
            'signature_net': sig.get('netAmount') or 0.0,
            'signature_vat': sig.get('vatAmount') or 0.0,
            'signature_gross': sig.get('grossAmount') or 0.0,
            'state': 'signed',
        })
        move.message_post(body=_(
            'Α.1155: εκδόθηκε υπογραφή πληρωμής %(amount)s για το τερματικό '
            '%(terminal)s (λήξη %(expiry)s).',
            amount=f'{self.amount:.2f}', terminal=terminal.display_name,
            expiry=self.signature_expiry or '—'))
        # With a driver, charge the card straight away — the signature exists
        # for exactly this and expires. Otherwise keep the dialog open so the
        # cashier can charge the terminal by hand and type the id.
        if self.driver_enabled:
            return self.action_charge_terminal()
        return self._reopen()

    def _check_signature_usable(self):
        """Α.1155 §5.3, checked before the signature leaves for the terminal.

        The provider enforces all of this too, but only once the document is
        transmitted — by then the card has been charged, and unwinding that
        costs a Void. Cheaper to refuse here.
        """
        self.ensure_one()
        if self.signature_expired:
            raise UserError(_(
                'Η υπογραφή του παρόχου έληξε στις %(expiry)s και δεν μπορεί '
                'να χρησιμοποιηθεί. Ακυρώστε την πληρωμή και ζητήστε νέα '
                'υπογραφή.', expiry=self.signature_expiry))
        # «Το ποσό του τρόπου πληρωμής ΠΡΕΠΕΙ να είναι ίσο ή μικρότερο από το
        # πληρωτέο της υπογραφής» — reachable because amount stays writable.
        if self.signature_amount and _r2(self.amount) > _r2(self.signature_amount):
            raise UserError(_(
                'Το ποσό %(amount)s ξεπερνά το ποσό της υπογραφής '
                '%(signed)s. Ακυρώστε την πληρωμή και ζητήστε νέα υπογραφή '
                'για το σωστό ποσό.',
                amount=f'{self.amount:.2f}', signed=f'{self.signature_amount:.2f}'))
        # «Η υπογραφή πρέπει να αφορά το συγκεκριμένο παραστατικό»: same net,
        # vat and gross. Only drifts if the document was edited after signing.
        move = self.move_id
        drift = [
            (label, signed, current)
            for label, signed, current in (
                (_('καθαρή αξία'), self.signature_net, move.amount_untaxed),
                (_('ΦΠΑ'), self.signature_vat, move.amount_tax),
                (_('σύνολο'), self.signature_gross, move._l10n_gr_prov_payable()),
            )
            if signed and _r2(signed) != _r2(current)
        ]
        if drift:
            raise UserError(_(
                'Το παραστατικό άλλαξε μετά την έκδοση της υπογραφής '
                '(%(fields)s). Ακυρώστε την πληρωμή και ζητήστε νέα υπογραφή.',
                fields='; '.join(
                    f'{label}: {signed:.2f} → {current:.2f}'
                    for label, signed, current in drift)))

    # ── Driver-side charging ────────────────────────────────────────────────

    def _driver_amounts(self):
        """The money block every driver request carries."""
        self.ensure_one()
        move = self.move_id
        block = {
            'amount': _r2(self.amount),
            'invoiceAmount': _r2(move._l10n_gr_prov_payable()),
            'netAmount': _r2(move.amount_untaxed),
            'vatAmount': _r2(move.amount_tax),
            'tipAmount': _r2(self.tip_amount) if self.tip_amount else 0,
        }
        # Optional everywhere, and NSPs that do not offer δόσεις reject a value:
        # only send it when instalments were actually asked for.
        if self.installments > 1:
            block['installments'] = self.installments
        return block

    def _driver_signature_block(self):
        """Α.1155 fields tying the charge to the provider's signature."""
        self.ensure_one()
        signed_at = self.signed_at
        return {
            'providerId': 'ILYDA',
            'providerInput': self.signed_content or '',
            'providerSignature': self.signature or '',
            'providerUid': self.signature_uid or '',
            # The driver wants epoch seconds. Odoo stores a *naive UTC*
            # datetime and datetime.timestamp() reads a naive value as local
            # time — on a Greek server that is 2-3 hours off, so say UTC.
            'signatureTimestamp': int(
                signed_at.replace(tzinfo=timezone.utc).timestamp()
            ) if signed_at else 0,
            'paymentMethodId': self.payment_method,
        }

    def _store_driver_result(self, data):
        """Keep whatever the terminal answered, approved or not.

        nspReferenceNumber is the value AADE expects as transactionId — the
        spec marks it «Αποστέλλεται στην ΑΑΔΕ» — so it becomes our
        transaction_id rather than anything the cashier types.
        """
        self.ensure_one()
        code = data.get('responseCode')
        # driverError is set by MegEftPosDriver.transaction when the call
        # failed at the driver rather than at the NSP (unreachable terminal,
        # timeout): without it a COMMUNICATION_ERROR would carry no reason.
        message = ' '.join(filter(None, (
            data.get('nspResponseCode'), data.get('nspResponseCodeDescription'),
            data.get('nspResponseCodeDescripton'), data.get('driverError'))))
        vals = {
            'driver_response_code': code if code in dict(RESPONSE_CODES) else 'UNKNOWN',
            'driver_message': message or False,
            'ecr_reference': data.get('ecrReferenceNumber') or self.ecr_reference,
            'nsp_reference': data.get('nspReferenceNumber') or self.nsp_reference,
            'bank_auth_code': data.get('bankAuthorizationCode')
                              or data.get('bankAuthorizatonCode') or False,
            'receipt_number': data.get('receiptNumber') or False,
            'card_type': data.get('cardType') or False,
            'card_number': data.get('cardNumber') or False,
            'paid_amount': data.get('paidAmount') or 0.0,
            'original_amount': data.get('originalAmount') or 0.0,
        }
        if data.get('nspReferenceNumber'):
            vals['transaction_id'] = data['nspReferenceNumber']
        if data.get('tipAmount'):
            vals['tip_amount'] = data['tipAmount']
        # The customer may have picked a different method on the terminal.
        # NONE_PAYMENT_METHOD means the NSP does not report it — keep what we
        # asked for, which is exactly what the spec tells the ERP to do.
        method = data.get('paymentMethodId')
        if method in dict(PAYMENT_METHODS):
            vals['payment_method'] = method
        self.write(vals)
        return code

    def _reconcile_paid_amount(self):
        """Make the transmitted amount the one the card actually paid.

        The terminal is the source of truth for what was charged: the customer
        may settle less, or the NSP may round. Transmitting our requested
        figure instead would put a number in the myDATA type-7 line that never
        happened, so adopt paidAmount and leave the shortfall unassigned for
        the user to cover with another payment method.

        NSPs disagree on whether paidAmount includes the tip, so a value
        matching either reading is taken as agreement.
        """
        self.ensure_one()
        paid = _r2(self.paid_amount)
        if not paid:
            return  # NSP does not report it — nothing to reconcile against
        requested, tip = _r2(self.amount), _r2(self.tip_amount)
        if paid in (requested, _r2(requested + tip)):
            return
        if paid > requested:
            # Over the signature's ceiling — the provider will reject the
            # document, so surface it now while a Void is still the answer.
            raise UserError(_(
                'Το τερματικό χρέωσε %(paid)s ενώ ζητήθηκαν %(asked)s. Το '
                'επιπλέον ποσό δεν καλύπτεται από την υπογραφή — ακυρώστε τη '
                'χρέωση στο τερματικό.',
                paid=f'{paid:.2f}', asked=f'{requested:.2f}'))
        self.amount = paid
        self.move_id.message_post(body=_(
            'Α.1155: το τερματικό χρέωσε %(paid)s αντί για %(asked)s — η '
            'πληρωμή προσαρμόστηκε. Υπόλοιπο %(rest)s προς εξόφληση με άλλο '
            'τρόπο πληρωμής.',
            paid=f'{paid:.2f}', asked=f'{requested:.2f}',
            rest=f'{requested - paid:.2f}'))

    def _original_transaction_block(self):
        """The references of the sale a refund reverses.

        Viva Cloud gained «Ελεύθερο Refund» in driver v2.1.08: it refunds to
        the card without quoting an earlier charge, which is the only way to
        credit a customer whose original sale went through another channel.
        Every other NSP needs the references.
        """
        self.ensure_one()
        origin = self.origin_payment_id
        if not origin and self.terminal_id.pos_protocol == 'VIVA_CLOUD':
            return {}
        if not origin.nsp_reference:
            raise UserError(_(
                'Για επιστροφή χρημάτων χρειάζεται η αρχική χρέωση κάρτας '
                '(πεδίο «Αρχική Χρέωση») με κωδικούς από το τερματικό.'))
        return {
            'ecrReferenceNumber': origin.ecr_reference or '',
            'nspReferenceNumber': origin.nsp_reference,
            'bankAuthorizationCode': origin.bank_auth_code or '',
            'receiptNumber': origin.receipt_number or '',
        }

    def action_charge_terminal(self):
        """Charge (or refund) the card through the MegEftPos driver.

        A credit note reverses a specific earlier charge, so it goes to
        /refund carrying that charge's references; everything else is a sale.
        """
        self.ensure_one()
        if self.state != 'signed':
            raise UserError(_('Χρειάζεται πρώτα υπογραφή παρόχου.'))
        self._check_signature_usable()
        if not self.driver_enabled:
            raise UserError(_(
                'Το τερματικό %s δεν είναι συνδεδεμένο με τον MegEftPos Driver.',
                self.terminal_id.display_name))
        is_refund = self.move_id.move_type == 'out_refund'
        request = dict(self._driver_amounts(), **self._driver_signature_block())
        request['cashier'] = self.env.user.name
        if is_refund:
            request.update(self._original_transaction_block())
        driver = MegEftPosDriver(self.move_id.company_id, self.terminal_id)
        device = self.terminal_id._l10n_gr_prov_pos_device()
        data = (driver.refund if is_refund else driver.sale)(device, request)
        code = self._store_driver_result(data)
        if code != 'APPROVED':
            # No raise: rolling back would throw away ecrReferenceNumber, which
            # is the only handle for recovering an interrupted transaction.
            self.move_id.message_post(body=_(
                'Α.1155: η συναλλαγή κάρτας δεν εγκρίθηκε (%(code)s) %(msg)s',
                code=code or '—', msg=self.driver_message or ''))
            return self._reopen()
        self._reconcile_paid_amount()
        self.move_id.message_post(body=_(
            'Α.1155: %(kind)s %(amount)s εγκρίθηκε — έγκριση τράπεζας '
            '%(auth)s, NSP ref %(nsp)s.',
            kind=_('επιστροφή') if is_refund else _('χρέωση κάρτας'),
            amount=f'{self.amount:.2f}', auth=self.bank_auth_code or '—',
            nsp=self.nsp_reference or '—'))
        return self.action_complete()

    def action_preload_terminal(self):
        """Push the signature to the terminal for the customer to pay later.

        Α.1155 §4: an already-issued document is settled by preloading its
        pending signature onto the payment means; the customer then pays at
        the terminal on their own time. Nothing is charged here — the outcome
        arrives later through «Ανάκτηση Συναλλαγής».
        """
        self.ensure_one()
        if self.state != 'signed':
            raise UserError(_('Χρειάζεται πρώτα υπογραφή παρόχου.'))
        self._check_signature_usable()
        if not self.driver_enabled:
            raise UserError(_(
                'Το τερματικό %s δεν είναι συνδεδεμένο με τον MegEftPos Driver.',
                self.terminal_id.display_name))
        move = self.move_id
        request = dict(self._driver_amounts(), **self._driver_signature_block())
        request['cashier'] = self.env.user.name
        # Mandatory on Cardlink, harmless elsewhere: the document being paid.
        request['receiptNumber'] = move.name or ''
        issue_date = move.invoice_date or fields.Date.context_today(self)
        request['receiptTimestamp'] = int(datetime.combine(
            issue_date, datetime.min.time(), tzinfo=timezone.utc).timestamp())
        data = MegEftPosDriver(move.company_id, self.terminal_id).preload(
            self.terminal_id._l10n_gr_prov_pos_device(), request)
        code = (data or {}).get('responseCode')
        if code != 'APPROVED':
            raise UserError(_(
                'Η προφόρτωση στο τερματικό δεν έγινε δεκτή: %(code)s %(msg)s',
                code=dict(RESPONSE_CODES).get(code, code or '—'),
                msg=(data or {}).get('nspResponseCodeDescription')
                    or (data or {}).get('nspResponseCodeDescripton')
                    or (data or {}).get('driverError') or ''))
        # Only the handle for finding the transaction later — deliberately not
        # the driver result fields, because nothing has been charged yet.
        self.write({
            'preloaded_at': fields.Datetime.now(),
            'ecr_reference': data.get('ecrReferenceNumber') or self.ecr_reference,
        })
        move.message_post(body=_(
            'Α.1155: προφορτώθηκε στο τερματικό %(terminal)s πληρωμή '
            '%(amount)s. Μετά την πληρωμή από τον πελάτη, χρησιμοποιήστε την '
            '«Ανάκτηση Συναλλαγής».',
            terminal=self.terminal_id.display_name, amount=f'{self.amount:.2f}'))
        return self._reopen()

    def _void_terminal(self):
        """Reverse an approved charge on the terminal (same-day cancellation).

        Called when the payment is cancelled: the money must go back before the
        provider signature is released.
        """
        self.ensure_one()
        request = dict(self._driver_amounts(), **self._driver_signature_block())
        request.update({
            'ecrReferenceNumber': self.ecr_reference or '',
            'nspReferenceNumber': self.nsp_reference,
            'bankAuthorizationCode': self.bank_auth_code or '',
            'receiptNumber': self.receipt_number or '',
        })
        request['cashier'] = self.env.user.name
        data = MegEftPosDriver(self.move_id.company_id, self.terminal_id).void(
            self.terminal_id._l10n_gr_prov_pos_device(), request)
        code = (data or {}).get('responseCode')
        if code != 'APPROVED':
            raise UserError(_(
                'Η ακύρωση της χρέωσης στο τερματικό δεν εγκρίθηκε: %(code)s '
                '%(msg)s', code=dict(RESPONSE_CODES).get(code, code or '—'),
                msg=(data or {}).get('nspResponseCodeDescription')
                    or (data or {}).get('nspResponseCodeDescripton')
                    or (data or {}).get('driverError') or ''))
        self.move_id.message_post(body=_(
            'Α.1155: ακυρώθηκε στο τερματικό η χρέωση %(amount)s (NSP ref '
            '%(nsp)s).', amount=f'{self.amount:.2f}', nsp=self.nsp_reference))

    def action_recover_pending(self):
        """Ask the terminal what became of a transaction we lost the answer to.

        A dropped connection or a timeout leaves the charge in an unknown
        state; the driver keeps it pending and can still report the outcome.
        """
        self.ensure_one()
        driver = MegEftPosDriver(self.move_id.company_id, self.terminal_id)
        device = self.terminal_id._l10n_gr_prov_pos_device()
        if self.ecr_reference:
            found = driver.pending_by_ecr(device, self.ecr_reference)
        elif self.nsp_reference:
            found = driver.pending_by_nsp(device, self.nsp_reference)
        else:
            found = driver.pending_all(device)
            if len(found) > 1:
                raise UserError(_(
                    'Το τερματικό έχει %s εκκρεμείς συναλλαγές — δεν μπορεί να '
                    'ταυτοποιηθεί η σωστή. Ελέγξτε το τερματικό.', len(found)))
        if not found:
            raise UserError(_(
                'Ο driver δεν βρήκε εκκρεμή συναλλαγή — η χρέωση δεν '
                'ολοκληρώθηκε στο τερματικό.'))
        code = self._store_driver_result(found[0])
        if code != 'APPROVED':
            return self._reopen()
        self._reconcile_paid_amount()
        self.move_id.message_post(body=_(
            'Α.1155: ανακτήθηκε εγκεκριμένη χρέωση %(amount)s — NSP ref '
            '%(nsp)s.', amount=f'{self.amount:.2f}', nsp=self.nsp_reference or '—'))
        return self.action_complete()

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
        self._check_signature_usable()
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
            # Always 7. IRIS at the terminal is a settlement mode inside the
            # EFT/POS transaction, not a separate rail — same terminal, same
            # signature. Type 8 is IRIS *direct*, which never touches a POS.
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
        if self.driver_response_code == 'APPROVED' and self.nsp_reference:
            # The card was actually charged — give the money back first.
            self._void_terminal()
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
