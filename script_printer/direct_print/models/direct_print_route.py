from odoo import fields, models


class DirectPrintRoute(models.Model):
    _name = 'direct.print.route'
    _description = 'Direct Print Route'
    _rec_name = 'report_display_name'

    report_name = fields.Char(
        'Report Technical Name', required=True,
        help='Technical name as used in action.report_name, '
             'e.g. account.report_invoice_with_payments')
    report_display_name = fields.Char('Display Name',
                                      help='Friendly label shown in the list')
    printer_name = fields.Char('Printer',
                               help='Leave blank to use the user\'s selected printer')
    copies = fields.Integer('Copies', default=1)
    active = fields.Boolean(default=True)
