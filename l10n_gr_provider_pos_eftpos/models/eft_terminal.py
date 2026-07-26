# -*- coding: utf-8 -*-
from odoo import api, models, _

from odoo.addons.l10n_gr_provider_eftpos.models.eft import (
    EftIlydaClient, _fatal_errors, _format_errors,
)
from odoo.addons.l10n_gr_provider_ilyda.models.account_move import _r2


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
        return {
            'signature': sig.get('signature'),
            'signing_author': sig.get('signingAuthor'),
            'terminal_code': terminal.code,
        }

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
