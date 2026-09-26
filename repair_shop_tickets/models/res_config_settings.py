from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    repair_labor_product_id = fields.Many2one(
        related='company_id.repair_labor_product_id', readonly=False)
    repair_location_id = fields.Many2one(
        related='company_id.repair_location_id', readonly=False)
    repair_consume_on = fields.Selection(
        related='company_id.repair_consume_on', readonly=False)
    repair_journal_retail_id = fields.Many2one(
        related='company_id.repair_journal_retail_id', readonly=False)
    repair_journal_business_id = fields.Many2one(
        related='company_id.repair_journal_business_id', readonly=False)
    repair_receipt_terms = fields.Html(
        related='company_id.repair_receipt_terms', readonly=False)
    repair_pickup_reminder_days = fields.Integer(
        related='company_id.repair_pickup_reminder_days', readonly=False)
