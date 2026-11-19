from odoo import fields, models


class ServiceContractHours(models.Model):
    _name = 'service.contract.hours'
    _description = 'Ώρες Εργασίας Συμβολαίου'
    _order = 'date desc, id desc'

    contract_id = fields.Many2one(
        'service.contract', string='Συμβόλαιο', required=True,
        ondelete='cascade', index=True)
    partner_id = fields.Many2one(related='contract_id.partner_id', string='Πελάτης')
    company_id = fields.Many2one(related='contract_id.company_id', store=True)
    date = fields.Date(string='Ημερομηνία', required=True,
                       default=fields.Date.context_today)
    user_id = fields.Many2one(
        'res.users', string='Υπάλληλος', required=True, index=True,
        default=lambda self: self.env.user, domain="[('share', '=', False)]")
    hours = fields.Float(string='Ώρες')
    name = fields.Char(string='Τι έγινε')
