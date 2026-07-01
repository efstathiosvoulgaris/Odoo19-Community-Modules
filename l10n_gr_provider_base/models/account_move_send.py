# -*- coding: utf-8 -*-
from odoo import api, models


class AccountMoveSend(models.AbstractModel):
    _inherit = 'account.move.send'

    @api.model
    def _is_gr_edi_applicable(self, move):
        """Suppress the l10n_gr_edi ERP channel for provider-routed documents.

        A document must reach myDATA through exactly one channel. When a
        provider is configured, sales documents are issued (and reported to
        myDATA) by the provider, so the ERP channel must not also send them.
        Vendor bills / expense classifications still use the ERP channel.
        """
        if move.l10n_gr_prov_applicable:
            return False
        return super()._is_gr_edi_applicable(move)

    def _call_web_service_before_invoice_pdf_render(self, invoices_data):
        """Issue provider documents during Send & Print, before the PDF renders,
        so the rendered PDF carries the MARK / hash / QR markings."""
        for invoice in list(invoices_data):
            if (
                invoice.l10n_gr_prov_applicable
                and invoice.state == 'posted'
                and not invoice.l10n_gr_prov_mark
            ):
                invoice._l10n_gr_prov_try_send()
                # Guard with .get() — another hook may have removed this invoice
                # from invoices_data before we get here.
                if invoice.l10n_gr_prov_state == 'error' and invoice in invoices_data:
                    invoices_data[invoice]['error'] = {
                        'error_title': 'Error when issuing through the e-invoicing provider',
                        'errors': [invoice.l10n_gr_prov_error or 'Unknown error'],
                    }
        return super()._call_web_service_before_invoice_pdf_render(invoices_data)
