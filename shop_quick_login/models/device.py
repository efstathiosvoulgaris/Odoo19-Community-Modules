import hashlib
import hmac
import re
import secrets
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.addons.base.models.res_users import check_identity
from odoo.exceptions import UserError
from odoo.http import request

DEVICE_DAYS = 365
DEVICE_FAILS_PER_HOUR = 10
ENROLL_MINUTES = 2


def cookie_name(db):
    """Ένα cookie ανά βάση: εγγραφή στη test δεν ανοίγει τη skarlas."""
    return 'ql_device_' + re.sub(r'[^A-Za-z0-9_]', '_', db or '')


def token_hash(token):
    return hashlib.sha256((token or '').encode()).hexdigest()


class ShopQlDevice(models.Model):
    _name = 'shop.ql.device'
    _description = 'Γρήγορη σύνδεση: υπολογιστής καταστήματος'
    _inherit = ['mail.thread']
    _order = 'name'

    name = fields.Char('Υπολογιστής', required=True, tracking=True,
                       help='Π.χ. «Ταμείο», «Service 1». Εμφανίζεται στη σελίδα σύνδεσης.')
    state = fields.Selection([('pending', 'Αναμονή εγγραφής'), ('active', 'Ενεργός'),
                              ('blocked', 'Κλειστός (πολλές αποτυχίες)'), ('revoked', 'Ακυρώθηκε')],
                             default='pending', required=True, readonly=True, tracking=True)
    token_hash = fields.Char(readonly=True, copy=False, index=True)
    enroll_nonce_hash = fields.Char(readonly=True, copy=False)
    enroll_until = fields.Datetime(readonly=True, copy=False)
    enrolled_at = fields.Datetime('Εγγραφή', readonly=True, copy=False)
    enrolled_by = fields.Many2one('res.users', 'Εγγραφή από', readonly=True, copy=False)
    expires_at = fields.Datetime('Λήξη', readonly=True, copy=False)
    last_used = fields.Datetime('Τελευταία χρήση', readonly=True, copy=False)
    user_agent = fields.Char('Browser', readonly=True, copy=False)
    no_idle_logout = fields.Boolean(
        'Χωρίς αποσύνδεση αδράνειας', tracking=True,
        help='Για υπολογιστή όπου το backend πρέπει να μένει ανοιχτό (π.χ. ταμείο).')
    fail_count = fields.Integer(readonly=True, copy=False)
    fail_window_start = fields.Datetime(readonly=True, copy=False)

    # ── Εγγραφή (μόνο διαχειριστής, με επανέλεγχο κωδικού) ──────────────────

    def _check_admin(self):
        if not self.env.user.has_group('base.group_system'):
            raise UserError(_('Μόνο ο διαχειριστής.'))

    @check_identity
    def action_enroll_this_pc(self):
        """Ο browser που πάτησε το κουμπί γίνεται αυτός ο υπολογιστής. Το κουμπί δίνει έναν
        κωδικό μιας χρήσης (2') που ο controller ανταλλάσσει με το cookie της συσκευής."""
        self.ensure_one()
        self._check_admin()
        nonce = secrets.token_urlsafe(32)
        self.sudo().write({'enroll_nonce_hash': token_hash(nonce),
                           'enroll_until': fields.Datetime.now() + timedelta(minutes=ENROLL_MINUTES)})
        return {'type': 'ir.actions.act_url', 'target': 'self',
                'url': '/quick-login/enroll/%s/%s' % (self.id, nonce)}

    def _enroll(self, nonce, user_agent):
        """Επιστρέφει το token του cookie, ή False."""
        self.ensure_one()
        me = self.sudo()
        if not (me.enroll_nonce_hash and me.enroll_until and me.enroll_until > fields.Datetime.now()
                and hmac.compare_digest(me.enroll_nonce_hash, token_hash(nonce))):
            return False
        token = secrets.token_urlsafe(32)
        now = fields.Datetime.now()
        me.write({'token_hash': token_hash(token), 'state': 'active', 'enroll_nonce_hash': False,
                  'enroll_until': False, 'enrolled_at': now, 'enrolled_by': self.env.user.id,
                  'expires_at': now + timedelta(days=DEVICE_DAYS), 'user_agent': (user_agent or '')[:250],
                  'fail_count': 0, 'fail_window_start': False})
        admins = self.env.ref('base.group_system').sudo().all_user_ids.filtered(lambda u: not u.share)
        me.message_post(
            body=_('Νέος υπολογιστής καταστήματος «%(name)s» εγγράφηκε από %(user)s.',
                   name=me.name, user=self.env.user.name),
            partner_ids=admins.partner_id.ids, subtype_xmlid='mail.mt_comment')
        return token

    def action_revoke(self):
        self._check_admin()
        self.sudo().write({'state': 'revoked', 'token_hash': False, 'enroll_nonce_hash': False})

    def action_unblock(self):
        self._check_admin()
        self.filtered(lambda d: d.state == 'blocked').sudo().write(
            {'state': 'active', 'fail_count': 0, 'fail_window_start': False})

    @api.model
    def action_revoke_all(self):
        self._check_admin()
        self.sudo().search([('state', 'in', ('active', 'blocked', 'pending'))]).action_revoke()

    # ── Αναγνώριση της συσκευής του αιτήματος ───────────────────────────────

    @api.model
    def _from_request(self):
        """Η ενεργή συσκευή του browser που κάνει το αίτημα, ή κενό."""
        if not request or not request.db:
            return self.browse()
        token = request.httprequest.cookies.get(cookie_name(request.db))
        if not token:
            return self.browse()
        device = self.sudo().search([('token_hash', '=', token_hash(token))], limit=1)
        if not device or device.state != 'active' or \
                (device.expires_at and device.expires_at < fields.Datetime.now()):
            return self.browse()
        return device

    def _touch(self):
        self.ensure_one()
        now = fields.Datetime.now()
        if not self.last_used or now - self.last_used > timedelta(minutes=5):
            self.sudo().last_used = now

    def _register_failure(self):
        """Όριο ανά συσκευή: πάνω από DEVICE_FAILS_PER_HOUR αποτυχίες σε μία ώρα → η γρήγορη
        σύνδεση της συσκευής κλείνει μέχρι να την ξανανοίξει ο διαχειριστής."""
        self.ensure_one()
        me = self.sudo()
        now = fields.Datetime.now()
        if not me.fail_window_start or now - me.fail_window_start > timedelta(hours=1):
            me.write({'fail_window_start': now, 'fail_count': 1})
            return
        me.fail_count += 1
        if me.fail_count >= DEVICE_FAILS_PER_HOUR:
            me.state = 'blocked'
            admins = self.env.ref('base.group_system').sudo().all_user_ids.filtered(lambda u: not u.share)
            me.message_post(
                body=_('Ο υπολογιστής «%s» έκλεισε για γρήγορη σύνδεση: πολλές αποτυχημένες '
                       'προσπάθειες μέσα σε μία ώρα. Ελέγξτε και πατήστε «Άνοιγμα ξανά».', me.name),
                partner_ids=admins.partner_id.ids, subtype_xmlid='mail.mt_comment')
