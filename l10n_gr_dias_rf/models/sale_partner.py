import base64

from odoo import api, fields, models

from ..lib import rf


class ResPartner(models.Model):
    _inherit = 'res.partner'

    dias_rf_code_fmt = fields.Char('Πάγιος κωδικός RF', compute='_compute_dias_rf_code_fmt')

    def _dias_rf_partner_code(self):
        """Πάγιος κωδικός του commercial partner (χωρίς έλεγχο ποσού), ή False."""
        self.ensure_one()
        partner = self.commercial_partner_id
        org = (partner.company_id or self.env.company).sudo().dias_org_code
        if not (org and partner.id):
            return False
        try:
            return rf.make_rf(org, partner.id, rf.KIND_PARTNER)
        except ValueError:
            return False

    def _compute_dias_rf_code_fmt(self):
        for partner in self:
            code = partner.id and partner._dias_rf_partner_code()
            partner.dias_rf_code_fmt = rf.format_rf(code) if code else False


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    dias_rf_code_fmt = fields.Char('Κωδικός RF', compute='_compute_dias_rf_code')

    def _dias_rf_order_code(self):
        """Κωδικός παραγγελίας με έλεγχο ποσού. Ακολουθεί το τρέχον σύνολο (όπως στη v13)."""
        self.ensure_one()
        org = self.company_id.sudo().dias_org_code
        # IST/… = ιστορικές προσφορές της v13 (αδρανείς, μόνο για ιστορικό): ποτέ κωδικός.
        if not (org and self.id and self.partner_id and self.amount_total > 0
                and self.state != 'cancel' and self.currency_id.name == 'EUR'
                and not (self.name or '').startswith('IST/')):
            return False
        try:
            return rf.make_rf(org, self.partner_id.commercial_partner_id.id, rf.KIND_ORDER,
                              self.id, self.amount_total)
        except ValueError:
            return False

    @api.depends('amount_total', 'partner_id', 'company_id', 'state')
    def _compute_dias_rf_code(self):
        for order in self:
            code = order._dias_rf_order_code()
            order.dias_rf_code_fmt = rf.format_rf(code) if code else False

    def _dias_rf_print(self):
        self.ensure_one()
        code = self._dias_rf_order_code()
        if not code:
            return False
        png = self.env['ir.actions.report'].barcode(
            'QR', rf.qr_value(code, self.amount_total), width=240, height=240)
        return {
            'code': rf.format_rf(code),
            'qr': 'data:image/png;base64,' + base64.b64encode(png).decode(),
            'fixed': False,
            'test': self.company_id.sudo().dias_env != 'P',
        }
