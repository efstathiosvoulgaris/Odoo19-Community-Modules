from odoo import fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    service_contract_id = fields.Many2one(
        'service.contract', string='Συμβόλαιο', copy=False, index='btree_not_null')
