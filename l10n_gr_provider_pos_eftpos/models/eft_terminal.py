# -*- coding: utf-8 -*-
import logging

from odoo import api, models, _

from odoo.addons.l10n_gr_provider_eftpos.models.eft import (
    EftIlydaClient, _fatal_errors, _format_errors,
)
from odoo.addons.l10n_gr_provider_eftpos.models.eft_driver import (
    MegEftPosDriver, RESPONSE_CODES,
)
from odoo.addons.l10n_gr_provider_ilyda.models.account_move import _r2

_logger = logging.getLogger(__name__)


class L10nGrProvEftTerminal(models.Model):
    _inherit = 'l10n.gr.prov.eft.terminal'

    @api.model
    def l10n_gr_prov_pos_sign(self, vals):
        """Request an Α.1155 payment signature for a POS card payment, before
        the invoice exists (called from the payment screen).

        The realtime sign endpoint signs against the document totals + series +
        invoice type — none of which need the serial number — so it works at
        payment time. `vals`: config_id, amount, net, vat, gross, vat_rate,
        is_timologio. Returns the signature dict, or {'error': <text>}.

        When the terminal is driven by the MegEftPos Driver the card is also
        charged here and `transaction_id` comes back alongside the signature,
        so the cashier never types it. Both steps happen in one call because
        the signature exists only to be spent on this charge: issued but
        unused, it reaches AADE as an «Ανοιχτό Παραστατικό» after 24h.
        """
        config = self.env['pos.config'].browse(vals['config_id'])
        terminal = config.l10n_gr_prov_eft_terminal_id
        if not terminal:
            return {'error': _(
                'Δεν έχει οριστεί τερματικό EFT/POS στο POS (Ρυθμίσεις → '
                'Πάροχος myDATA → Τερματικό Α.1155).')}
        company = terminal.company_id
        journal = (config.l10n_gr_prov_tim_journal_id if vals.get('is_timologio')
                   else config.l10n_gr_prov_alp_journal_id)
        if not journal:
            return {'error': _('Δεν έχει οριστεί ημερολόγιο ΑΛΠ/ΤΙΜ στο POS.')}
        body = {
            'amount': _r2(vals['amount']),
            'terminalId': terminal.code,
            'nspProtocol': terminal.nsp_protocol,
            'netAmount': _r2(vals.get('net') or 0),
            'vatAmount': _r2(vals.get('vat') or 0),
            'grossAmount': _r2(vals.get('gross') or 0),
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
            return {'error': str(e)}
        fatal = _fatal_errors(data)
        if fatal:
            return {'error': _format_errors(fatal)}
        sigs = data.get('invoiceSignatures') or []
        if not sigs:
            return {'error': _('Ο πάροχος δεν επέστρεψε υπογραφή.')}
        sig = sigs[0]
        result = {
            'signature': sig.get('signature'),
            'signing_author': sig.get('signingAuthor'),
            'terminal_code': terminal.code,
        }
        if not terminal._l10n_gr_prov_driver_enabled():
            return result  # standalone terminal: the cashier charges it
        charge = terminal._l10n_gr_prov_pos_charge(sig, vals)
        if charge.get('error'):
            # Nothing was charged, so release the signature rather than leave
            # it to expire into an open document.
            self.l10n_gr_prov_pos_cancel({
                'config_id': vals['config_id'], 'signature': result['signature']})
            return charge
        result.update(charge)
        return result

    def _l10n_gr_prov_pos_charge(self, sig, vals):
        """Charge the card for a POS order through the MegEftPos Driver.

        Returns {'transaction_id': …} on approval, else {'error': …}. Unlike
        the backend flow there is no record to park a failed charge on, so an
        unapproved response is reported and the signature released; an
        interrupted one is left to the driver's own pending list, which the
        cashier resolves from the terminal.
        """
        self.ensure_one()
        signed_at = sig.get('signedAt')
        request = self._l10n_gr_prov_pos_request(vals, {
            'signed_content': sig.get('signedContent') or '',
            'signature': sig.get('signature') or '',
            # the uidHash, not the uid — see the backend signature block
            'signature_uid': sig.get('uidHash') or sig.get('uid') or '',
            # provider timestamps are epoch millis, the driver wants seconds
            'signature_ts': int(float(signed_at) / 1000) if signed_at else 0,
        })
        try:
            data = MegEftPosDriver(self.company_id).sale(
                self._l10n_gr_prov_pos_device(), request)
        except Exception as e:
            return {'error': str(e)}
        _logger.info('MegEftPos POS sale result: %s', data)
        code = (data or {}).get('responseCode')
        if code != 'APPROVED':
            return {'error': _(
                'Η χρέωση στο τερματικό δεν εγκρίθηκε: %(code)s %(msg)s',
                code=dict(RESPONSE_CODES).get(code, code or '—'),
                msg=(data or {}).get('nspResponseCodeDescription')
                    or (data or {}).get('nspResponseCodeDescripton')
                    or (data or {}).get('driverError') or '')}
        # nspReferenceNumber is what AADE expects as the transactionId.
        transaction_id = data.get('nspReferenceNumber')
        if not transaction_id:
            return {'error': _(
                'Το τερματικό ενέκρινε τη συναλλαγή αλλά δεν επέστρεψε '
                'nspReferenceNumber — δεν μπορεί να διαβιβαστεί.')}
        # Everything a later Void has to quote back, plus the bank trail.
        return {
            'transaction_id': transaction_id,
            'signed_content': request['providerInput'],
            'signature_uid': request['providerUid'],
            'signature_ts': request['signatureTimestamp'],
            'ecr_reference': data.get('ecrReferenceNumber') or '',
            'bank_auth_code': data.get('bankAuthorizationCode')
                              or data.get('bankAuthorizatonCode') or '',
            'receipt_number': data.get('receiptNumber') or '',
        }

    def _l10n_gr_prov_pos_request(self, vals, sig):
        """The money + signature block shared by Sale and Void."""
        self.ensure_one()
        return {
            'amount': _r2(vals['amount']),
            'invoiceAmount': _r2(vals.get('gross') or 0),
            'netAmount': _r2(vals.get('net') or 0),
            'vatAmount': _r2(vals.get('vat') or 0),
            'tipAmount': 0,
            'cashier': self.env.user.name,
            'providerId': 'ILYDA',
            'providerInput': sig.get('signed_content') or '',
            'providerSignature': sig.get('signature') or '',
            'providerUid': sig.get('signature_uid') or '',
            'signatureTimestamp': sig.get('signature_ts') or 0,
            # paymentMethodId is deliberately omitted (it is optional — the
            # driver's own preload example leaves it out). At a counter the
            # cashier cannot know whether the customer will tap a card or pay
            # the IRIS QR, and preselecting one can hide the other on NSPs
            # that honour it. Either way it is the same EFT/POS transaction.
        }

    @api.model
    def l10n_gr_prov_pos_void(self, vals):
        """Give back a charge the driver already made for a POS order.

        Called when the order does not go through after the card was charged
        — a later payment line failing, validation being abandoned, or the
        cashier removing a charged line. The signature is released too: it was
        never spent on a transmitted document.

        `vals` carries what the charge returned (transaction_id, ecr_reference,
        bank_auth_code, receipt_number, signature…) plus the order totals.
        Returns {'ok': True} or {'error': <text>}.
        """
        config = self.env['pos.config'].browse(vals['config_id'])
        terminal = config.l10n_gr_prov_eft_terminal_id
        if not terminal or not terminal._l10n_gr_prov_driver_enabled():
            return {'error': _('Το τερματικό δεν είναι συνδεδεμένο με driver.')}
        request = terminal._l10n_gr_prov_pos_request(vals, vals)
        request.update({
            'ecrReferenceNumber': vals.get('ecr_reference') or '',
            'nspReferenceNumber': vals.get('transaction_id') or '',
            'bankAuthorizationCode': vals.get('bank_auth_code') or '',
            'receiptNumber': vals.get('receipt_number') or '',
        })
        try:
            data = MegEftPosDriver(terminal.company_id).void(
                terminal._l10n_gr_prov_pos_device(), request)
        except Exception as e:
            return {'error': str(e)}
        _logger.info('MegEftPos POS void result: %s', data)
        code = (data or {}).get('responseCode')
        if code != 'APPROVED':
            return {'error': _(
                'Η ακύρωση της χρέωσης στο τερματικό δεν εγκρίθηκε: '
                '%(code)s %(msg)s',
                code=dict(RESPONSE_CODES).get(code, code or '—'),
                msg=(data or {}).get('nspResponseCodeDescription')
                    or (data or {}).get('nspResponseCodeDescripton')
                    or (data or {}).get('driverError') or '')}
        # The money is back; the signature was never used on a sent document.
        if vals.get('signature'):
            self.l10n_gr_prov_pos_cancel({
                'config_id': vals['config_id'], 'signature': vals['signature']})
        return {'ok': True}

    @api.model
    def l10n_gr_prov_pos_cancel(self, vals):
        """Cancel an unused Α.1155 signature (order abandoned after signing —
        AADE auto-transmits unused signatures after 24h, so release it)."""
        config = self.env['pos.config'].browse(vals['config_id'])
        company = (config.l10n_gr_prov_eft_terminal_id.company_id
                   or self.env.company)
        try:
            data = EftIlydaClient(company).cancel_signature({
                'signature': vals['signature'],
                'signatureCancelReason': 'TRANSACTION_CANCELLED',
            })
        except Exception as e:
            return {'error': str(e)}
        fatal = _fatal_errors(data)
        return {'error': _format_errors(fatal)} if fatal else {'ok': True}
