# -*- coding: utf-8 -*-
from odoo import models

# One report body (report_gr_invoice.xml), reached from two entry points:
# the dedicated «Παραστατικό» action, and the standard Print button (core
# account.report_invoice). Both need the matching physical paperformat
# (A4 / 80mm) — chosen from the printed document's own journal, not from the
# action being called.
#
# The paper geometry MUST follow the same decision as the template routing:
# account.move._l10n_gr_prov_print_form() is the single source of truth for
# both. Reading the journal field directly here was the fresh-install bug —
# the journal defaults to gr_a4 while the routing also requires a configured
# provider, so an unconfigured database rendered the vanilla Odoo invoice on
# the Greek form's 85mm/30mm margins.
GR_PAPERFORMATS = {
    'gr_a4': 'l10n_gr_provider_base.paperformat_gr_a4',
    'gr_80mm': 'l10n_gr_provider_base.paperformat_gr_80mm',
}


class IrActionsReport(models.Model):
    _inherit = 'ir.actions.report'

    def get_paperformat(self):
        if self.model == 'account.move':
            res_ids = self.env.context.get('l10n_gr_prov_report_res_ids')
            if res_ids:
                move = self.env['account.move'].browse(res_ids[0]).exists()
                xmlid = GR_PAPERFORMATS.get(
                    move and move._l10n_gr_prov_print_form())
                if xmlid:
                    paperformat = self.env.ref(xmlid, raise_if_not_found=False)
                    if paperformat:
                        return paperformat
        return super().get_paperformat()

    def _render_qweb_pdf(self, report_ref, res_ids=None, data=None):
        if res_ids:
            self = self.with_context(l10n_gr_prov_report_res_ids=res_ids)
        return super(IrActionsReport, self)._render_qweb_pdf(
            report_ref, res_ids=res_ids, data=data)
