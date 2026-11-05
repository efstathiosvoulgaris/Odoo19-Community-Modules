from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    contract_notice_days = fields.Integer(
        string='Ειδοποίηση πριν τη λήξη (ημέρες)', default=30)
    contract_journal_id = fields.Many2one(
        'account.journal', string='Ημερολόγιο Προτιμολογίου',
        domain="[('type', '=', 'sale')]")
    contract_product_id = fields.Many2one(
        'product.product', string='Είδος Συμβολαίου')
    contract_payment_term_id = fields.Many2one(
        'account.payment.term', string='Όροι Πληρωμής')

    def _contract_product(self):
        self.ensure_one()
        return (self.contract_product_id
                or self.env.ref('maintenance_contracts.product_contract',
                                raise_if_not_found=False)
                or self.env['product.product'])
