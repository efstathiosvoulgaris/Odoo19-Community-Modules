from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    contract_notice_days = fields.Integer(
        related='company_id.contract_notice_days', readonly=False)
    contract_journal_id = fields.Many2one(
        related='company_id.contract_journal_id', readonly=False)
    contract_product_id = fields.Many2one(
        related='company_id.contract_product_id', readonly=False)
    contract_payment_term_id = fields.Many2one(
        related='company_id.contract_payment_term_id', readonly=False)
