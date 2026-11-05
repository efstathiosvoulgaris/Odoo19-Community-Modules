import math
import re
from datetime import timedelta

from passlib.context import CryptContext

from odoo import _, api, fields, models
from odoo.exceptions import AccessDenied, UserError
from odoo.http import request

CREDENTIAL_TYPE = 'quick_pin'
AUTH_PATH = '/quick-login/authenticate'
LOGIN_MAX_FAILURES = 5
LOGIN_LOCK_MINUTES = 15
# Ποτέ γρήγορη σύνδεση: όποιος μπορεί πολλά, μπαίνει μόνο με κωδικό (και 2FA αν έχει).
EXCLUDED_GROUPS = ('base.group_system', 'base.group_erp_manager', 'account.group_account_manager',
                   'hr.group_hr_user', 'hr.group_hr_manager')
_pin_crypt = CryptContext(['pbkdf2_sha512'])
# Για ίδιο χρόνο απόκρισης όταν δεν υπάρχει PIN.
_DUMMY_HASH = _pin_crypt.hash('000000')


def _pin_weak(pin):
    """Τα πρώτα που δοκιμάζει κάποιος: ίδια ψηφία, σειρές, επαναλαμβανόμενα ζεύγη/τριάδες."""
    if len(set(pin)) == 1:
        return True
    digits = [int(c) for c in pin]
    steps = {b - a for a, b in zip(digits, digits[1:])}
    if steps in ({1}, {-1}):
        return True
    return pin[:2] * 3 == pin or pin[:3] * 2 == pin


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    # Το PIN της γρήγορης σύνδεσης: μόνο hash, το ορίζει ο υπεύθυνος (ql.pin.wizard).
    ql_pin_hash = fields.Char(groups='base.group_system', copy=False)
    ql_has_pin = fields.Boolean(string='PIN γρήγορης σύνδεσης', compute='_compute_ql_has_pin',
                                groups='hr.group_hr_user')
    # Δικός της μετρητής, ανεξάρτητος από κάθε άλλο addon.
    ql_failures = fields.Integer(groups='base.group_system', copy=False)
    ql_locked_until = fields.Datetime(groups='base.group_system', copy=False)

    @api.depends('ql_pin_hash')
    def _compute_ql_has_pin(self):
        for emp in self:
            emp.ql_has_pin = bool(emp.sudo().ql_pin_hash)

    def _ql_set_pin(self, pin):
        self.ensure_one()
        if not re.fullmatch(r'\d{6}', pin or ''):
            raise UserError(_('Το PIN πρέπει να είναι ακριβώς 6 ψηφία.'))
        if _pin_weak(pin):
            raise UserError(_('Πολύ εύκολο PIN (ίδια ψηφία, σειρά ή επανάληψη). Διαλέξτε άλλο.'))
        self.sudo().write({'ql_pin_hash': _pin_crypt.hash(pin), 'ql_failures': 0,
                           'ql_locked_until': False})


class ResUsers(models.Model):
    _inherit = 'res.users'

    def _ql_eligible(self):
        """Μπορεί να μπει με γρήγορη σύνδεση; Εσωτερικός, ενεργός, με εργαζόμενο που έχει PIN,
        χωρίς 2FA και χωρίς καμία από τις «ισχυρές» ομάδες."""
        self.ensure_one()
        user = self.sudo()
        if not user.active or user.share or user.totp_enabled:
            return False
        if any(user.has_group(g) for g in EXCLUDED_GROUPS if self.env.ref(g, raise_if_not_found=False)):
            return False
        emp = user.employee_id
        return bool(emp and emp.ql_pin_hash)

    @api.model
    def _ql_eligible_users(self):
        users = self.sudo().search([('share', '=', False), ('employee_id', '!=', False)])
        return users.filtered(lambda u: u._ql_eligible()).sorted(lambda u: u.name or '')

    # ── Ο τύπος διαπιστευτηρίου, μέσα στον μηχανισμό σύνδεσης του Odoo ───────

    def _check_credentials(self, credential, env):
        if credential.get('type') != CREDENTIAL_TYPE:
            return super()._check_credentials(credential, env)
        # Μόνο από τη σελίδα γρήγορης σύνδεσης: ένα POST στο /web/login με type=quick_pin δεν
        # περνά (εκεί οι αποτυχίες δεν θα μετρούσαν, αφού γίνεται rollback).
        if not request or request.httprequest.path != AUTH_PATH:
            raise AccessDenied()
        device = self.env['shop.ql.device']._from_request()
        if not device:
            raise AccessDenied()
        user = self.env.user  # το _login έχει κάνει with_user στον χρήστη του login
        emp = user.sudo().employee_id
        if not user._ql_eligible() or self._ql_locked_minutes(emp):
            _pin_crypt.verify(credential.get('pin') or '', _DUMMY_HASH)  # ίδιος χρόνος
            self._ql_fail(emp, device)
            raise AccessDenied()
        if not _pin_crypt.verify(credential.get('pin') or '', emp.sudo().ql_pin_hash):
            self._ql_fail(emp, device)
            raise AccessDenied()
        emp.sudo().write({'ql_failures': 0, 'ql_locked_until': False})
        device._touch()
        return {'uid': user.id, 'auth_method': CREDENTIAL_TYPE, 'mfa': 'default'}

    @api.model
    def _ql_locked_minutes(self, emp):
        until = emp.sudo().ql_locked_until if emp else False
        if until and until > fields.Datetime.now():
            return max(1, math.ceil((until - fields.Datetime.now()).total_seconds() / 60))
        return 0

    @api.model
    def _ql_fail(self, emp, device):
        """Μετρά την αποτυχία (εργαζόμενος + συσκευή). Ο controller κάνει commit πριν απαντήσει,
        αλλιώς το rollback του AccessDenied θα την έσβηνε."""
        if emp:
            e = emp.sudo()
            failures = e.ql_failures + 1
            vals = {'ql_failures': failures}
            if failures >= LOGIN_MAX_FAILURES:
                vals.update(ql_failures=0, ql_locked_until=fields.Datetime.now()
                            + timedelta(minutes=LOGIN_LOCK_MINUTES))
            e.write(vals)
        if device:
            device._register_failure()
