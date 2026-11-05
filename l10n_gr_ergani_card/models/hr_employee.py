import hmac
import math
import re
import secrets
import string
import unicodedata
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

# A check-in older than this without a check-out counts as a forgotten
# «Αποχώρηση» (DESIGN §5.3): it no longer keeps the employee «inside».
OPEN_SHIFT_HOURS = 16
SCAN_MAX_FAILURES = 5
SCAN_LOCK_MINUTES = 15
ATHENS = ZoneInfo('Europe/Athens')


def _afm_valid(afm):
    if not re.fullmatch(r'\d{9}', afm or '') or afm == '0' * 9:
        return False
    total = sum(int(d) * 2 ** (8 - i) for i, d in enumerate(afm[:8]))
    return total % 11 % 10 == int(afm[8])


def _ergani_name(value):
    """ΕΡΓΑΝΗ keeps names upper case without accents."""
    if not value:
        return value
    stripped = ''.join(c for c in unicodedata.normalize('NFD', value)
                       if unicodedata.category(c) != 'Mn')
    return ' '.join(stripped.upper().split())


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    ergani_enabled = fields.Boolean(
        string='Χτυπά κάρτα ΕΡΓΑΝΗ', groups='hr.group_hr_user',
        help='Ο εργαζόμενος περνά από τη σελίδα χτυπήματος μετά το login.')
    ergani_exempt_reason = fields.Selection(
        [('owner', 'Ιδιοκτήτης'), ('not_salaried', 'Μη μισθωτός'), ('other', 'Άλλο')],
        string='Αιτία εξαίρεσης', groups='hr.group_hr_user')
    ergani_afm = fields.Char(string='ΑΦΜ (ΕΡΓΑΝΗ)', size=9, groups='hr.group_hr_user')
    ergani_last_name = fields.Char(string='Επώνυμο (ΕΡΓΑΝΗ)', groups='hr.group_hr_user')
    ergani_first_name = fields.Char(string='Όνομα (ΕΡΓΑΝΗ)', groups='hr.group_hr_user')
    # Wrong cards at the gate count here; only the system writes them.
    ergani_scan_failures = fields.Integer(groups='base.group_system', copy=False)
    ergani_scan_locked_until = fields.Datetime(groups='base.group_system', copy=False)
    ergani_schedule_confirmed = fields.Date(
        string='Ωράριο επιβεβαιωμένο με λογιστή στις', groups='hr.group_hr_user',
        help='Πότε επιβεβαιώθηκε ότι το ωράριο εργασίας του Odoo είναι ίδιο με το ωράριο '
             'που έχει δηλώσει ο λογιστής στο ΕΡΓΑΝΗ. Αν το ωράριο αλλάξει μετά, η κατάσταση '
             'κινήσεων το επισημαίνει.')
    ergani_flex_minutes = fields.Integer(
        string='Ευέλικτη προσέλευση (λεπτά)', groups='hr.group_hr_user',
        help='Όπως στη Δήλωση Μεταβολής Στοιχείων Εργασιακής Σχέσης (0–120). Μετρά μόνο μετά την '
             'έναρξη του ωραρίου και μετακινεί αντίστοιχα τη λήξη (Ενιαίος Οδηγός σ. 94–96).')
    ergani_break_minutes = fields.Integer(string='Διάλειμμα (λεπτά)', groups='hr.group_hr_user')
    ergani_break_in_schedule = fields.Boolean(
        string='Διάλειμμα εντός ωραρίου', groups='hr.group_hr_user',
        help='Ναι: εντός ωραρίου. Όχι: με παράταση του ωραρίου (Δήλωση Μεταβολής).')
    ergani_has_card = fields.Boolean(
        string='Κάρτα QR', compute='_compute_ergani_has_card', groups='hr.group_hr_user')

    @api.depends('barcode')
    def _compute_ergani_has_card(self):
        for emp in self:
            emp.ergani_has_card = bool(emp.sudo().barcode)

    @api.constrains('ergani_flex_minutes', 'ergani_last_name', 'ergani_first_name')
    def _check_ergani_limits(self):
        for emp in self:
            if not 0 <= emp.ergani_flex_minutes <= 120:
                raise ValidationError(_('Η ευέλικτη προσέλευση είναι 0 έως 120 λεπτά.'))
            # Card_v1.xsd: f_eponymo ≤ 50, f_onoma ≤ 30 characters.
            if len(emp.ergani_last_name or '') > 50 or len(emp.ergani_first_name or '') > 30:
                raise ValidationError(_('Το ΕΡΓΑΝΗ δέχεται έως 50 χαρακτήρες επώνυμο και 30 όνομα.'))

    @api.constrains('ergani_afm')
    def _check_ergani_afm(self):
        for emp in self:
            if emp.ergani_afm and not _afm_valid(emp.ergani_afm):
                raise ValidationError(_('Μη έγκυρος ΑΦΜ: %s', emp.ergani_afm))

    @api.constrains('ergani_enabled', 'ergani_afm', 'ergani_last_name', 'ergani_first_name')
    def _check_ergani_complete(self):
        for emp in self:
            if emp.ergani_enabled and not (emp.ergani_afm and emp.ergani_last_name
                                           and emp.ergani_first_name and emp.user_id):
                raise ValidationError(_(
                    '%s: για κάρτα ΕΡΓΑΝΗ χρειάζονται ΑΦΜ, επώνυμο, όνομα και '
                    'συνδεδεμένος χρήστης Odoo.', emp.name))

    @api.model_create_multi
    def create(self, vals_list):
        return super().create([self._ergani_clean(vals) for vals in vals_list])

    def write(self, vals):
        return super().write(self._ergani_clean(vals))

    @staticmethod
    def _ergani_clean(vals):
        vals = dict(vals)
        for key in ('ergani_last_name', 'ergani_first_name'):
            if vals.get(key):
                vals[key] = _ergani_name(vals[key])
        if vals.get('ergani_afm'):
            vals['ergani_afm'] = re.sub(r'\D', '', vals['ergani_afm'])
        return vals

    # ── Card QR (DESIGN §5.4) ────────────────────────────────────────────────
    # The card carries the employee's Badge ID (hr `barcode`), the same QR the
    # quick login reads; neither addon needs the other.

    def _ergani_scan_locked_minutes(self):
        self.ensure_one()
        until = self.sudo().ergani_scan_locked_until
        if until and until > fields.Datetime.now():
            return max(1, math.ceil((until - fields.Datetime.now()).total_seconds() / 60))
        return 0

    def _ergani_check_card(self, code):
        """True when the scanned code is this employee's own card. Wrong ones
        count; the counter lives in the database so a new login does not reset it."""
        self.ensure_one()
        emp = self.sudo()
        if self._ergani_scan_locked_minutes():
            return False
        code = (code or '').strip()
        if emp.barcode and code and hmac.compare_digest(code, emp.barcode):
            emp.write({'ergani_scan_failures': 0, 'ergani_scan_locked_until': False})
            return True
        failures = emp.ergani_scan_failures + 1
        vals = {'ergani_scan_failures': failures}
        if failures >= SCAN_MAX_FAILURES:
            vals.update(ergani_scan_failures=0, ergani_scan_locked_until=(
                fields.Datetime.now() + timedelta(minutes=SCAN_LOCK_MINUTES)))
        emp.write(vals)
        return False

    def action_ergani_print_card(self):
        """Print the QR card; an employee without a Badge ID gets a random one."""
        if not self.env.user.has_group('hr.group_hr_user'):
            raise UserError(_('Μόνο υπεύθυνος HR.'))
        for emp in self.filtered(lambda e: not e.barcode):
            emp._ergani_new_badge()
        return self.env.ref('l10n_gr_ergani_card.action_report_ergani_card').report_action(self)

    def action_ergani_new_card(self):
        """Lost card: a new Badge ID, so the old QR stops working everywhere."""
        if not self.env.user.has_group('hr.group_hr_user'):
            raise UserError(_('Μόνο υπεύθυνος HR.'))
        for emp in self:
            emp._ergani_new_badge()
            emp.message_post(body=_('Νέα κάρτα QR από %s· η προηγούμενη δεν ισχύει πια.',
                                    self.env.user.name))
        return self.env.ref('l10n_gr_ergani_card.action_report_ergani_card').report_action(self)

    def _ergani_new_badge(self):
        self.barcode = ''.join(secrets.choice(string.digits) for _ in range(16))

    # ── Shift state (DESIGN §5.3) ────────────────────────────────────────────

    @staticmethod
    def _ergani_today():
        return datetime.now(ATHENS).date()

    def _ergani_open_dates(self):
        """Reference dates whose check-in can still be closed now: today, and
        with night work also yesterday until 11:00 (Ενιαίος Οδηγός σ. 18)."""
        now = datetime.now(ATHENS)
        dates = [now.date()]
        if self.company_id.sudo().ergani_night_shift and now.hour < 11:
            dates.append(now.date() - timedelta(days=1))
        return dates

    def _ergani_open_in_card(self):
        """The current period's check-in: a check-in without check-out, of
        today (Athens) and not older than OPEN_SHIFT_HOURS. Yesterday's evening
        check-in left open must not swallow this morning's (split schedule)."""
        self.ensure_one()
        since = fields.Datetime.now() - timedelta(hours=OPEN_SHIFT_HOURS)
        return self.env['ergani.card'].sudo().search([
            ('employee_id', '=', self.id), ('card_type', '=', '0'),
            ('out_card_ids', '=', False), ('event_datetime', '>=', since),
            ('reference_date', 'in', self._ergani_open_dates()),
        ], order='event_datetime desc', limit=1)

    def _ergani_required(self):
        self.ensure_one()
        emp = self.sudo()
        return bool(emp.ergani_enabled and emp.company_id.ergani_mode != 'off')

    def _ergani_flag_forgotten(self):
        """Check-ins past the open window without a check-out: tell the
        manager once. Nothing is sent for the employee (DESIGN §3)."""
        since = fields.Datetime.now() - timedelta(hours=OPEN_SHIFT_HOURS)
        cards = self.env['ergani.card'].sudo().search([
            ('employee_id', 'in', self.ids), ('card_type', '=', '0'),
            ('out_card_ids', '=', False), ('forgotten_notified', '=', False),
            '|', ('event_datetime', '<', since),
            ('reference_date', '<', min(self[:1]._ergani_open_dates() or [self._ergani_today()])),
        ])
        for card in cards:
            card._ergani_notify(_('Ξεχασμένη αποχώρηση'), _(
                '%(emp)s χτύπησε προσέλευση %(when)s χωρίς αποχώρηση. Δεν στάλθηκε '
                'τίποτα για λογαριασμό του· το ΕΡΓΑΝΗ κρατά το δηλωμένο ωράριο.',
                emp=card.employee_id.name, when=card._ergani_local_label()))
            card.forgotten_notified = True


class ResUsers(models.Model):
    _inherit = 'res.users'

    def _ergani_gate_state(self):
        """What the gate needs to know about the current user."""
        self.ensure_one()
        emp = self.sudo().employee_id
        if not emp or not emp._ergani_required():
            return {'required': False, 'mode': None, 'open_card_id': False, 'has_card': False}
        open_in = emp._ergani_open_in_card()
        return {
            'required': not open_in,
            'mode': 'out' if open_in else 'in',
            'open_card_id': open_in.id,
            'has_card': bool(emp.barcode),
            'employee': emp.name,
            'locked_minutes': emp._ergani_scan_locked_minutes(),
            'simulation': emp.company_id.ergani_mode == 'simulation',
        }
