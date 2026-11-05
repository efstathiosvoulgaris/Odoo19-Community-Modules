import base64

from odoo import api, models


class ReportQlCard(models.AbstractModel):
    """Η κάρτα QR (το Badge ID του εργαζομένου). Το QR φτιάχνεται εδώ ως data-URI: ποτέ μέσα σε
    URL (/report/barcode), ώστε ο κωδικός να μη γραφτεί σε κανένα log."""
    _name = 'report.shop_quick_login.report_ql_card'
    _description = 'Κάρτα γρήγορης σύνδεσης'

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
