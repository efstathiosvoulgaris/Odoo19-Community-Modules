from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    repair_prices_include_tax = fields.Boolean(
        related='company_id.repair_prices_include_tax', readonly=False)
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
    repair_viber_ready_text = fields.Text(
        related='company_id.repair_viber_ready_text', readonly=False)
    repair_viber_not_repaired_text = fields.Text(
        related='company_id.repair_viber_not_repaired_text', readonly=False)
    repair_signature_device_id = fields.Many2one(
        related='company_id.repair_signature_device_id', readonly=False)
    repair_sign_text_repaired = fields.Char(
        related='company_id.repair_sign_text_repaired', readonly=False)
    repair_sign_text_not_repaired = fields.Char(
        related='company_id.repair_sign_text_not_repaired', readonly=False)
