import re
from urllib.parse import quote

from odoo import _, fields, models
from odoo.exceptions import UserError
from odoo.tools.misc import formatLang


class _Blank(dict):
    """An unknown {field} in a company text stays as typed, never crashes."""

    def __missing__(self, key):
        return '{' + key + '}'


class ServiceTicket(models.Model):
    _inherit = 'service.ticket'

    # ── Viber: a ready-made message the employee sends himself ───────────────

    def _viber_number(self):
        """The customer's «Κινητό» (l10n_gr_partner) in international form, digits only;
        never the landline. A 10-digit number without a country code is taken as Greek."""
        self.ensure_one()
        partner = self.partner_id
        raw = partner.kinito
        digits = re.sub(r'\D', '', raw or '')
        if digits.startswith('00'):
            digits = digits[2:]
        if len(digits) == 10:
            digits = '30' + digits
        return digits

    def _viber_text(self, template):
        self.ensure_one()
        device = ' '.join(filter(None, (self.brand_id.name, self.product_model_id.name)))
        return (template or '').format_map(_Blank(
            customer=self.partner_id.name or '',
            device=device,
            ticket=self.name or '',
            amount=formatLang(self.env, self.total_price),
            company=self.env.company.name or '',
        )).replace('  ', ' ').strip()

    def _viber_open(self, template):
        self.ensure_one()
        if not self.partner_id:
            raise UserError(_('Το δελτίο δεν έχει πελάτη.'))
        number = self._viber_number()
        if len(number) < 11:
            raise UserError(_('Ο πελάτης %s δεν έχει έγκυρο κινητό για Viber.',
                              self.partner_id.name))
        text = self._viber_text(template)
        self.message_post(body=_('Μήνυμα Viber προς %(number)s: %(text)s',
                                 number='+' + number, text=text))
        return {
            'type': 'ir.actions.client',
            'tag': 'repair_shop_tickets.open_viber',
            'params': {
                'url': 'viber://chat?number=%s&draft=%s' % (quote('+' + number), quote(text)),
                'text': text,
            },
        }

    def action_viber_ready(self):
        """«Έτοιμη συσκευή» on Viber: opens the chat with the message written,
        and records the notification like «Ειδοποίηση Πελάτη» does."""
        self.ensure_one()
        company = self.env.company
        action = self._viber_open(company.repair_viber_not_repaired_text
                                  if self.repair_result == 'not_repaired'
                                  else company.repair_viber_ready_text)
        self.write({
            'notified': True,
            'notified_channel': 'viber',
            'notified_date': fields.Datetime.now(),
            'notified_uid': self.env.user.id,
        })
        return action

