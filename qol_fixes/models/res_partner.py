import re
from urllib.parse import quote

from odoo import _, api, models
from odoo.exceptions import UserError
from odoo.fields import Domain


class ResPartner(models.Model):
    _inherit = 'res.partner'
    # Every contact field (sale, service, CRM, ...) finds the contact by mobile or phone too.
    _rec_names_search = ['complete_name', 'email', 'ref', 'vat', 'company_registry', 'kinito', 'phone']

    @api.model
    def _search_display_name(self, operator, value):
        """«698 488 8478» finds 6984888478: numbers are stored digits only, so the
        typed number is also tried without spaces, dashes, dots and brackets."""
        domain = super()._search_display_name(operator, value)
        if operator in ('ilike', '=ilike', 'like', '=like') and isinstance(value, str):
            compact = re.sub(r'[\s\-.()/]', '', value)
            if compact != value and re.fullmatch(r'\+?\d{3,}', compact):
                domain = Domain(domain) | Domain('kinito', operator, compact) | Domain('phone', operator, compact)
        return domain

    def _qol_viber_number(self):
        """The mobile in international form, digits only. A 10-digit number
        without a country code is taken as Greek."""
        digits = re.sub(r'\D', '', self.kinito or '')
        if digits.startswith('00'):
            digits = digits[2:]
        if len(digits) == 10:
            digits = '30' + digits
        return digits

    def action_qol_open_viber(self):
        self.ensure_one()
        number = self._qol_viber_number()
        if len(number) < 11:
            raise UserError(_('The mobile number %s is not valid for Viber.', self.kinito or ''))
        # act_url would prefix "/" to a viber:// link, so a client action opens it.
        return {
            'type': 'ir.actions.client',
            'tag': 'qol_fixes.open_external_url',
            'params': {'url': 'viber://chat?number=' + quote('+' + number)},
        }
