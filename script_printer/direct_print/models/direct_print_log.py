from odoo import fields, models


class DirectPrintLog(models.Model):
    _name = 'direct.print.log'
    _description = 'Direct Print Log'
    _order = 'create_date desc'
    _rec_name = 'document_name'

    document_name = fields.Char('Document', required=True)
    job_type = fields.Selection([
        ('pdf', 'PDF Report'),
        ('receipt', 'Receipt'),
        ('html', 'HTML'),
        ('label', 'Label'),
    ], string='Type', required=True)
    printer_name = fields.Char('Printer')
    copies = fields.Integer('Copies', default=1)
    status = fields.Selection([
        ('success', 'Success'),
        ('error', 'Error'),
    ], string='Status', required=True)
    error_message = fields.Text('Error Detail')
    user_id = fields.Many2one('res.users', string='User', readonly=True,
                              default=lambda self: self.env.user)
    create_date = fields.Datetime('Date', readonly=True)
