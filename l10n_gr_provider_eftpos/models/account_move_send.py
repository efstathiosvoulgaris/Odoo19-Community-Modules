# -*- coding: utf-8 -*-
from odoo import models


class AccountMoveSend(models.AbstractModel):
    _inherit = 'account.move.send'

    def _call_web_service_before_invoice_pdf_render(self, invoices_data):
        """Send & Print must not render and mail a document the provider has
        not got because its card payment is unsettled — flag it instead, like
        a failed transmission."""
        for invoice in list(invoices_data):
            if (invoice.l10n_gr_prov_applicable and invoice.state == 'posted'
                    and not invoice.l10n_gr_prov_mark):
                reason = invoice._l10n_gr_prov_eft_hold()
                if reason:
                    invoices_data[invoice]['error'] = {
                        'error_title': 'Πληρωμή με κάρτα σε εκκρεμότητα (Α.1155)',
                        'errors': [reason],
                    }
        return super()._call_web_service_before_invoice_pdf_render(invoices_data)
