import secrets
import string

from odoo import _, api, fields, models
from odoo.addons.base.models.res_users import check_identity
from odoo.exceptions import UserError


class HrEmployeeCard(models.Model):
    """Η κάρτα QR είναι το «Badge ID» του εργαζομένου (hr `barcode`): την ίδια κάρτα μπορεί να
    δέχεται και άλλο addon (π.χ. ΕΡΓΑΝΗ) χωρίς να εξαρτάται κανένα από το άλλο. Επιλέγει μόνο
    τον χρήστη· το PIN ζητείται πάντα."""
    _inherit = 'hr.employee'

    @api.model
    def _ql_find_by_card(self, raw):
        raw = (raw or '').strip()
        if not raw:
            return self.browse()
        return self.sudo().search([('barcode', '=', raw)], limit=1)

    def _ql_check_manager(self):
        if not self.env.user.has_group('base.group_system'):
            raise UserError(_('Μόνο ο διαχειριστής.'))

    def action_ql_print_card(self):
        """Τυπώνει την κάρτα· όποιος δεν έχει Badge ID παίρνει τυχαίο."""
        self._ql_check_manager()
        for emp in self.filtered(lambda e: not e.barcode):
            emp._ql_new_badge()
        return self.env.ref('shop_quick_login.action_report_ql_card').report_action(self)

    def action_ql_new_card(self):
        """Χαμένη κάρτα: νέο Badge ID, η παλιά δεν ισχύει πια πουθενά."""
        self._ql_check_manager()
        for emp in self:
            emp._ql_new_badge()
            emp.message_post(body=_('Νέα κάρτα QR από %s· η προηγούμενη δεν ισχύει πια.',
                                    self.env.user.name))
        return self.env.ref('shop_quick_login.action_report_ql_card').report_action(self)

    def _ql_new_badge(self):
        self.sudo().barcode = ''.join(secrets.choice(string.digits) for _ in range(16))

    def action_ql_set_pin(self):
        self.ensure_one()
        self._ql_check_manager()
        return {
            'type': 'ir.actions.act_window',
            'name': _('PIN γρήγορης σύνδεσης'),
            'res_model': 'shop.ql.pin.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_employee_id': self.id},
        }


class ShopQlPinWizard(models.TransientModel):
    """Ο υπεύθυνος ορίζει το PIN και το δίνει στον εργαζόμενο. Αποθηκεύεται μόνο το hash·
    το wizard σβήνεται από το Odoo λίγο μετά."""
    _name = 'shop.ql.pin.wizard'
    _description = 'Γρήγορη σύνδεση: ορισμός PIN'

    employee_id = fields.Many2one('hr.employee', 'Εργαζόμενος', required=True)
    pin = fields.Char('PIN (6 ψηφία)', required=True)
    pin2 = fields.Char('Ξανά το PIN', required=True)

    @check_identity
    def action_set(self):
        self.ensure_one()
        self.employee_id._ql_check_manager()
        if self.pin != self.pin2:
            raise UserError(_('Τα δύο PIN δεν ταιριάζουν.'))
        emp = self.employee_id
        if not emp.user_id:
            raise UserError(_('Ο %s δεν έχει χρήστη Odoo.', emp.name))
        emp._ql_set_pin(self.pin)
        self.write({'pin': False, 'pin2': False})
        emp.message_post(body=_('Ορίστηκε PIN γρήγορης σύνδεσης από %s.', self.env.user.name))
        if not emp.user_id._ql_eligible():
            return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {
                'type': 'warning', 'sticky': True,
                'message': _('Το PIN ορίστηκε, αλλά ο %s δεν μπορεί να μπει με γρήγορη σύνδεση: '
                             'έχει δικαιώματα διαχειριστή, λογιστηρίου ή HR, ή 2FA.', emp.name),
                'next': {'type': 'ir.actions.act_window_close'}}}
        return {'type': 'ir.actions.act_window_close'}
