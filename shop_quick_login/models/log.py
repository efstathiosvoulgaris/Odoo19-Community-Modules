from datetime import timedelta

from odoo import api, fields, models

RETENTION_DAYS = 365
STORM_FAILURES = 5
STORM_MINUTES = 10


class ShopQlLog(models.Model):
    """Ιστορικό γρήγορων συνδέσεων. Μόνο προσθήκη (κανείς δεν έχει δικαίωμα αλλαγής ή διαγραφής·
    μόνο το cron διατήρησης σβήνει ό,τι είναι πάνω από 12 μήνες)."""
    _name = 'shop.ql.log'
    _description = 'Γρήγορη σύνδεση: ιστορικό'
    _order = 'id desc'

    user_id = fields.Many2one('res.users', 'Χρήστης', readonly=True, index=True)
    device_id = fields.Many2one('shop.ql.device', 'Υπολογιστής', readonly=True, index=True)
    method = fields.Selection([('pin', 'PIN'), ('card', 'Κάρτα + PIN')], 'Τρόπος', readonly=True)
    success = fields.Boolean('Επιτυχία', readonly=True)
    ip = fields.Char('IP', readonly=True)
    note = fields.Char('Σημείωση', readonly=True)

    @api.model
    def _record(self, user, device, method, success, ip, note=False):
        rec = self.sudo().create({'user_id': user.id or False, 'device_id': device.id or False,
                                  'method': method, 'success': success, 'ip': ip, 'note': note})
        if not success:
            since = fields.Datetime.now() - timedelta(minutes=STORM_MINUTES)
            recent = self.sudo().search_count([('success', '=', False), ('create_date', '>=', since)])
            if recent == STORM_FAILURES and device:  # μία ειδοποίηση ανά «καταιγίδα»
                admins = self.env.ref('base.group_system').sudo().all_user_ids.filtered(
                    lambda u: not u.share)
                device.sudo().message_post(
                    body='Γρήγορη σύνδεση: %d αποτυχίες μέσα σε %d λεπτά (τελευταία: %s).'
                         % (recent, STORM_MINUTES, device.name),
                    partner_ids=admins.partner_id.ids, subtype_xmlid='mail.mt_comment')
        return rec

    @api.model
    def _cron_retention(self):
        limit = fields.Datetime.now() - timedelta(days=RETENTION_DAYS)
        self.sudo().search([('create_date', '<', limit)]).unlink()
