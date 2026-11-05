"""Δηλώσεις οργάνωσης χρόνου εργασίας από το Odoo (2.0, ergani/PLAN_2.0.md).

One declaration = one employee, one or more days, one POST. Today only
«Μεταβαλλόμενο ανά ημέρα» (WTODaily): another time, split, telework, rest,
non-work. Leaves (kind='leave') are modelled but cannot be submitted until the
trial reveals their document code and v2 schema (PLAN_2.0 §3).

Law (PLAN_2.0 §2.1): a change reaches ΕΡΓΑΝΗ before the day's work starts —
start = the earlier of the declared start and the first punch. After that only
an extension that keeps the original periods and begins after the moment of
submission. There is no late change. The rule is checked on «Έλεγχος», on
«Υποβολή» and again by the cron right before the POST.

Payload follows samples/json examples/WTODaily.json and xsds/WTO_v1.xsd.
"""
import hashlib
import json
import logging
from datetime import datetime, time, timedelta

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .ergani_client import (ErganiAuthError, ErganiClient, ErganiNotSent, ErganiRejected,
                            ErganiThrottled, ErganiUnknown)
from .ergani_status import _is_manager
from .res_company import ERGANI_MODES

_logger = logging.getLogger(__name__)
ATHENS = pytz.timezone('Europe/Athens')
DAY_TYPE_CODES = {'work': 'ΕΡΓ', 'telework': 'ΤΗΛ', 'rest': 'ΑΝ', 'no_work': 'ΜΕ'}
CONTENT_FIELDS = {'kind', 'employee_id', 'date_from', 'date_to', 'line_ids', 'comments'}
EFFECTIVE_STATES = ('sent', 'simulated')
STALE_SENDING_MINUTES = 10


def _hhmm(value):
    minutes = int(round((value or 0.0) * 60))
    return '%02d:%02d' % divmod(minutes, 60)


def _utc(day, value):
    """Local Athens HH:MM (float hours) on `day` → naive UTC."""
    hours, minutes = divmod(int(round(value * 60)), 60)
    local = ATHENS.localize(datetime.combine(day, time(min(hours, 23), minutes)))
    return local.astimezone(pytz.utc).replace(tzinfo=None)


class ErganiWto(models.Model):
    _name = 'ergani.wto'
    _description = 'ΕΡΓΑΝΗ: δήλωση ωραρίου / άδειας'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_from desc, id desc'

    name = fields.Char(compute='_compute_name')
    kind = fields.Selection([('daily', 'Αλλαγή ωραρίου'), ('leave', 'Άδεια')],
                            string='Είδος', required=True, default='daily')
    employee_id = fields.Many2one('hr.employee', string='Εργαζόμενος', required=True, index=True)
    company_id = fields.Many2one(related='employee_id.company_id', store=True, index=True)
    date_from = fields.Date(string='Από', required=True)
    date_to = fields.Date(string='Έως', required=True)
    comments = fields.Char(string='Σχόλια', size=200)
    line_ids = fields.One2many('ergani.wto.line', 'wto_id', string='Ανάλυση ημερών')
    state = fields.Selection([
        ('draft', 'Πρόχειρο'),
        ('pending', 'Σε αναμονή'),
        ('sending', 'Αποστέλλεται'),
        ('sent', 'Υποβλήθηκε'),
        ('simulated', 'Προσομοίωση'),
        ('error', 'Σφάλμα'),
        ('unknown', 'Άγνωστη έκβαση'),
        ('expired', 'Έληξε η προθεσμία'),
    ], string='Κατάσταση', default='draft', required=True, readonly=True, tracking=True, index=True)
    environment = fields.Selection([m for m in ERGANI_MODES if m[0] != 'off'],
                                   string='Περιβάλλον', readonly=True)
    submitted_by_id = fields.Many2one('res.users', string='Υποβλήθηκε από', readonly=True)
    submitted_at = fields.Datetime(string='Ώρα υποβολής', readonly=True, index=True)
    protocol = fields.Char(string='Πρωτόκολλο', readonly=True, tracking=True)
    ergani_id = fields.Char(string='ID ΕΡΓΑΝΗ', readonly=True)
    submit_date_raw = fields.Char(string='Ημ/νία υποβολής (ΕΡΓΑΝΗ)', readonly=True)
    payload = fields.Text(readonly=True)
    payload_hash = fields.Char(readonly=True)
    response = fields.Text(readonly=True)
    attempts = fields.Integer(string='Προσπάθειες', readonly=True)
    last_error = fields.Text(string='Τελευταίο σφάλμα', readonly=True)

    @api.depends('employee_id', 'kind', 'date_from', 'date_to')
    def _compute_name(self):
        kinds = dict(self._fields['kind'].selection)
        for wto in self:
            span = wto.date_from and wto.date_from.strftime('%d/%m/%Y') or ''
            if wto.date_to and wto.date_to != wto.date_from:
                span += '–' + wto.date_to.strftime('%d/%m/%Y')
            wto.name = '%s · %s · %s' % (wto.employee_id.name or '', kinds.get(wto.kind, ''), span)

    # ── immutability ─────────────────────────────────────────────────────────

    def write(self, vals):
        if CONTENT_FIELDS & set(vals) and self.filtered(lambda w: w.state != 'draft'):
            raise UserError(_('Μια δήλωση που υποβλήθηκε δεν αλλάζει. Φτιάξτε νέα: για κάθε μέρα '
                              'ισχύει η τελευταία υποβολή.'))
        return super().write(vals)

    def unlink(self):
        if self.filtered(lambda w: w.state != 'draft'):
            raise UserError(_('Διαγράφονται μόνο πρόχειρα.'))
        return super().unlink()

    # ── checks (PLAN_2.0 §2.1, §2.5) ─────────────────────────────────────────

    def _ergani_lines_by_day(self):
        self.ensure_one()
        by_day = {}
        for line in self.line_ids:
            by_day.setdefault(line.date, []).append(line)
        return by_day

    def _ergani_errors(self, deadline_only=False):
        self.ensure_one()
        errors = []
        emp = self.employee_id.sudo()
        by_day = self._ergani_lines_by_day()
        if not deadline_only:
            if self.kind == 'leave':
                errors.append(_('Η υποβολή αδειών ενεργοποιείται όταν επιβεβαιωθεί στο trial ο κωδικός '
                                'υποβολής τους (PLAN_2.0 §3).'))
            if not (emp.ergani_afm and emp.ergani_last_name and emp.ergani_first_name):
                errors.append(_('%s: λείπουν ΑΦΜ / επώνυμο / όνομα ΕΡΓΑΝΗ.', emp.name))
            if not self.date_from or not self.date_to or self.date_to < self.date_from:
                errors.append(_('Λάθος διάστημα ημερομηνιών.'))
                return errors
            day = self.date_from
            while day <= self.date_to:
                if day not in by_day:
                    # ΕΡΓΑΝΗ wants every day of the range declared (Ενιαίος σ. 86)
                    errors.append(_('%s: λείπει η ανάλυση της ημέρας.', day.strftime('%d/%m/%Y')))
                day += timedelta(days=1)
            for day, lines in by_day.items():
                if not self.date_from <= day <= self.date_to:
                    errors.append(_('%s: εκτός διαστήματος.', day.strftime('%d/%m/%Y')))
                errors += self._ergani_day_errors(day, lines)
        for day, lines in by_day.items():
            errors += self._ergani_deadline_errors(day, lines)
        return errors

    def _ergani_day_errors(self, day, lines):
        label = day.strftime('%d/%m/%Y')
        errors = []
        cats = {l.category for l in lines}
        if 'no_work' in cats and cats & {'work', 'telework'}:
            errors.append(_('%s: ρεπό / μη εργασία δεν συνδυάζεται με εργασία (Ενιαίος σ. 15).', label))
        if self.kind == 'daily' and cats & {'leave', 'hourly_leave'}:
            errors.append(_('%s: οι άδειες δηλώνονται ως «Άδεια», όχι ως αλλαγή ωραρίου.', label))
        timed = sorted((l for l in lines if l.category in ('work', 'telework', 'hourly_leave')),
                       key=lambda l: l.time_from)
        for line in timed:
            if not 0 <= line.time_from < line.time_to <= 24:
                # no night work here, and WTO_v1.xsd has no «change of day» field
                errors.append(_('%(d)s: διάστημα %(f)s–%(t)s: η λήξη πρέπει να είναι μετά την έναρξη '
                                'της ίδιας μέρας.', d=label, f=_hhmm(line.time_from),
                                t=_hhmm(line.time_to)))
        for a, b in zip(timed, timed[1:]):
            if b.time_from < a.time_to:
                errors.append(_('%s: επικαλυπτόμενα διαστήματα.', label))
        return errors

    def _ergani_deadline_errors(self, day, lines):
        """Before the day's work starts; after it, only an extension that keeps
        the original periods and starts after now (PLAN_2.0 §2.1)."""
        label = day.strftime('%d/%m/%Y')
        today = datetime.now(ATHENS).date()
        if day < today:
            return [_('%s: η μέρα έχει περάσει — δεν υπάρχει εκπρόθεσμη αλλαγή ωραρίου.', label)]
        if day > today or self.kind == 'leave':
            return []
        emp = self.employee_id.sudo()
        now = fields.Datetime.now()
        _kind, original = emp._ergani_expected_periods(day, exclude_wto=self)
        first_punch = self.env['ergani.card'].sudo().search([
            ('employee_id', '=', emp.id), ('card_type', '=', '0'),
            ('reference_date', '=', day)], order='event_datetime', limit=1).event_datetime
        starts = [s for s, _e in original] + ([first_punch] if first_punch else [])
        started = bool(starts) and now >= min(starts)
        new = [(_utc(day, l.time_from), _utc(day, l.time_to))
               for l in lines if l.category == 'work']
        errors = []
        if started and not new:
            errors.append(_('%s: η εργασία έχει ήδη αρχίσει — δεν δηλώνεται ρεπό / μη εργασία.', label))
        if started:
            for ps, pe in original:
                if not any(s <= ps and e >= pe for s, e in new):
                    errors.append(_('%s: η εργασία έχει αρχίσει — η νέα δήλωση πρέπει να περιέχει '
                                    'αυτούσιο το αρχικό ωράριο.', label))
                    break
        for s, e in new:
            begin = s
            for ps, pe in original:
                if ps <= begin < pe:
                    begin = pe  # the part inside the original period is not new
            if begin < e and begin <= now:
                errors.append(_('%(d)s: το νέο διάστημα από %(t)s πρέπει να αρχίζει μετά την ώρα '
                                'υποβολής.', d=label,
                                t=fields.Datetime.context_timestamp(
                                    self.with_context(tz='Europe/Athens'), begin).strftime('%H:%M')))
        return errors

    # ── payload (WTODaily.json / WTO_v1.xsd) ─────────────────────────────────

    def _ergani_payload(self):
        self.ensure_one()
        emp = self.employee_id.sudo()
        company = emp.company_id
        aa = emp.ergani_branch_id.aa if emp.ergani_branch_id else company.ergani_branch_aa
        days = []
        for day in sorted(self._ergani_lines_by_day()):
            lines = sorted(self._ergani_lines_by_day()[day], key=lambda l: l.time_from)
            days.append({
                'f_afm': emp.ergani_afm,
                'f_eponymo': emp.ergani_last_name,
                'f_onoma': emp.ergani_first_name,
                'f_date': day.strftime('%d/%m/%Y'),
                'ErgazomenosAnalytics': {'ErgazomenosWTOAnalytics': [{
                    'f_type': line.type_id.code,
                    'f_from': _hhmm(line.time_from) if line.category != 'no_work' else '',
                    'f_to': _hhmm(line.time_to) if line.category != 'no_work' else '',
                } for line in lines]},
            })
        return {'WTOS': {'WTO': [{
            'f_aa_pararthmatos': str(aa or 0),
            'f_rel_protocol': '',
            'f_rel_date': '',
            'f_comments': self.comments or '',
            'f_from_date': '',
            'f_to_date': '',
            'Ergazomenoi': {'ErgazomenoiWTO': days},
        }]}}

    # ── actions ──────────────────────────────────────────────────────────────

    def _ergani_check_manager(self):
        if not _is_manager(self.env):
            raise UserError(_('Μόνο για τον υπεύθυνο.'))

    def action_check(self):
        self._ergani_check_manager()
        errors = [e for wto in self for e in wto._ergani_errors()]
        if errors:
            raise UserError('\n'.join(errors))
        return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {
            'type': 'success', 'message': _('Ο έλεγχος πέρασε. Μπορεί να υποβληθεί.')}}

    def action_submit(self):
        self._ergani_check_manager()
        for wto in self.filtered(lambda w: w.state == 'draft'):
            errors = wto._ergani_errors()
            if errors:
                raise UserError(_('%(name)s:\n%(errors)s', name=wto.name, errors='\n'.join(errors)))
            company = wto.company_id
            if company.ergani_mode == 'off':
                raise UserError(_('Η σύνδεση με το ΕΡΓΑΝΗ είναι ανενεργή.'))
            payload = json.dumps(wto._ergani_payload(), ensure_ascii=False)
            vals = {
                'environment': company.ergani_mode,
                'payload': payload,
                'payload_hash': hashlib.sha256(payload.encode()).hexdigest(),
                'submitted_by_id': self.env.user.id,
                'submitted_at': fields.Datetime.now(),
                'state': 'simulated' if company.ergani_mode == 'simulation' else 'pending',
            }
            wto.sudo().write(vals)
            wto.message_post(body=_('Υποβολή από %s.', self.env.user.name))
        if self.filtered(lambda w: w.state == 'pending'):
            self.env.ref('l10n_gr_ergani_card.ir_cron_ergani_send').sudo()._trigger()
        return True

    def action_resend(self):
        """«Άγνωστη έκβαση» or «Σφάλμα»: send the same declaration again. Harmless
        for a schedule change — the last submission per day wins."""
        self._ergani_check_manager()
        for wto in self.filtered(lambda w: w.state in ('unknown', 'error')):
            errors = wto._ergani_errors(deadline_only=True)
            if errors:
                raise UserError('\n'.join(errors))
            wto.sudo().write({'state': 'pending', 'last_error': False})
            wto.message_post(body=_('Επαναποστολή από %s.', self.env.user.name))
        self.env.ref('l10n_gr_ergani_card.ir_cron_ergani_send').sudo()._trigger()

    def action_copy_draft(self):
        self._ergani_check_manager()
        self.ensure_one()
        new = self.copy({'state': 'draft', 'line_ids': [(0, 0, {
            'date': l.date, 'type_id': l.type_id.id, 'time_from': l.time_from,
            'time_to': l.time_to}) for l in self.line_ids]})
        return {'type': 'ir.actions.act_window', 'res_model': self._name, 'res_id': new.id,
                'view_mode': 'form'}

    # ── sender (called by the card cron, before the cards) ───────────────────

    @api.model
    def _ergani_send_pending(self, company):
        Cron = self.env['ir.cron']
        Card = self.env['ergani.card']
        stale = self.sudo().search([
            ('company_id', '=', company.id), ('state', '=', 'sending'),
            ('write_date', '<', fields.Datetime.now() - timedelta(minutes=STALE_SENDING_MINUTES))])
        for wto in stale:
            wto.write({'state': 'unknown', 'last_error': _('Έμεινε «Αποστέλλεται» (διακοπή).')})
        for wto in self.sudo().search([('company_id', '=', company.id), ('state', '=', 'pending'),
                                       ('environment', '=', company.ergani_mode)], order='id'):
            if company.ergani_paused:
                return
            errors = wto._ergani_errors(deadline_only=True)
            if errors:
                wto.write({'state': 'expired', 'last_error': '\n'.join(errors)})
                wto._ergani_notify(_('ΕΡΓΑΝΗ: δήλωση ωραρίου δεν στάλθηκε'), wto.last_error)
                Cron._commit_progress(0)
                continue
            wto.write({'state': 'sending', 'attempts': wto.attempts + 1})
            Cron._commit_progress(0)  # durable before the POST
            try:
                entry, raw = ErganiClient(company).post_document(
                    'WTODaily', json.loads(wto.payload), record=wto)
            except ErganiNotSent as e:
                wto.write({'state': 'pending', 'last_error': str(e)})
            except ErganiUnknown as e:
                wto.write({'state': 'unknown', 'last_error': str(e)})
                wto._ergani_notify(_('ΕΡΓΑΝΗ: άγνωστη έκβαση δήλωσης'), str(e))
            except ErganiRejected as e:
                wto.write({'state': 'error', 'last_error': str(e), 'response': str(e)})
                wto._ergani_notify(_('ΕΡΓΑΝΗ: απόρριψη δήλωσης ωραρίου'), str(e))
            except (ErganiAuthError, ErganiThrottled) as e:
                wto.write({'state': 'pending', 'last_error': str(e)})
                Card._ergani_pause(company, str(e))
            except Exception as e:
                _logger.exception('ΕΡΓΑΝΗ WTO send failed for %s', wto.id)
                wto.write({'state': 'unknown', 'last_error': str(e)})
            else:
                wto.write({'state': 'sent', 'ergani_id': str(entry.get('id') or ''),
                           'protocol': str(entry.get('protocol') or ''),
                           'submit_date_raw': str(entry.get('submitDate') or ''),
                           'response': raw, 'last_error': False})
            Cron._commit_progress(0)

    def _ergani_notify(self, summary, note):
        for wto in self:
            manager = wto.company_id.ergani_manager_id
            if manager:
                wto.sudo().activity_schedule('mail.mail_activity_data_todo', user_id=manager.id,
                                             summary=summary, note=note)


class ErganiWtoLine(models.Model):
    _name = 'ergani.wto.line'
    _description = 'ΕΡΓΑΝΗ: ανάλυση ημέρας'
    _order = 'date, time_from'

    wto_id = fields.Many2one('ergani.wto', required=True, ondelete='cascade', index=True)
    employee_id = fields.Many2one(related='wto_id.employee_id', store=True, index=True)
    state = fields.Selection(related='wto_id.state', store=True)
    date = fields.Date(string='Ημέρα', required=True)
    type_id = fields.Many2one('ergani.worktime.type', string='Τύπος', required=True)
    category = fields.Selection(related='type_id.category', store=True)
    time_from = fields.Float(string='Από')
    time_to = fields.Float(string='Έως')
    name = fields.Char(compute='_compute_name')

    @api.depends('employee_id', 'type_id', 'time_from', 'time_to')
    def _compute_name(self):
        for line in self:
            times = '' if line.category == 'no_work' else ' %s–%s' % (
                _hhmm(line.time_from), _hhmm(line.time_to))
            line.name = '%s: %s%s' % (line.employee_id.name or '', line.type_id.code or '', times)

    def write(self, vals):
        if self.filtered(lambda l: l.wto_id.state != 'draft'):
            raise UserError(_('Μια δήλωση που υποβλήθηκε δεν αλλάζει.'))
        return super().write(vals)

    def unlink(self):
        if self.filtered(lambda l: l.wto_id.state != 'draft'):
            raise UserError(_('Μια δήλωση που υποβλήθηκε δεν αλλάζει.'))
        return super().unlink()
