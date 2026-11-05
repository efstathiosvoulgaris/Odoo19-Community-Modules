import base64

from odoo import api, models


class ReportErganiCard(models.AbstractModel):
    """The employee's QR card (his Badge ID). The QR is built here as a data-URI,
    never in a URL (/report/barcode), so the code is written to no access log."""
    _name = 'report.l10n_gr_ergani_card.report_ergani_card'
    _description = 'Κάρτα QR εργαζομένου'

    @api.model
    def _get_report_values(self, docids, data=None):
        employees = self.env['hr.employee'].sudo().browse(docids)
        report = self.env['ir.actions.report']
        cards = [{
            'name': emp.name,
            'company': emp.company_id.name,
            'qr_src': 'data:image/png;base64,' + base64.b64encode(
                report.barcode('QR', emp.barcode, width=300, height=300)).decode(),
        } for emp in employees if emp.barcode]
        return {'doc_ids': docids, 'docs': employees, 'cards': cards}
