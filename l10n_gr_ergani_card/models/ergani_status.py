"""Κατάσταση κινήσεων and «Σήμερα» (PLAN_1.3 §3 C–E).

Compares punches with the employee's **Odoo** working schedule. That is not
the schedule declared in ΕΡΓΑΝΗ, so nothing here is a compliance check and
the wording says so everywhere (PLAN_1.3 §2.1). Nothing is sent anywhere.

One engine, `_ergani_expected_periods`, answers «which work periods did this
employee have on this day»; 1.4/2.0 replace only that function.
"""
from collections import defaultdict
from datetime import datetime, time, timedelta

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .hr_employee import OPEN_SHIFT_HOURS

ATHENS = pytz.timezone('Europe/Athens')  # resource.calendar needs pytz (tz.localize)
DISCLAIMER = ('Σύγκριση με το ωράριο του Odoo, όχι με το ωράριο που δηλώθηκε στο ΕΡΓΑΝΗ. '
              'Δεν αποτελεί έλεγχο συμμόρφωσης.')

FILTERS = [
    ('all', 'Όλες οι γραμμές'),
    ('risk', 'Χρειάζεται έλεγχος (όλα)'),
    ('before_start', 'Προσέλευση πριν την έναρξη'),
    ('over', 'Εργασία μετά τη λήξη / εκτός ωραρίου / περισσότερη'),
    ('rest_work', 'Χτύπημα σε ρεπό ή αργία/άδεια'),
    ('unpaired', 'Μη ζευγαρωμένες κινήσεις'),
    ('no_punch', 'Χωρίς χτύπημα σε μέρα με ωράριο'),
    ('info', 'Πληροφορία προσωπικού (όλα)'),
    ('late', 'Καθυστέρηση προσέλευσης'),
    ('early', 'Προαναχώρηση'),
    ('under', 'Εργασία λιγότερη από το ωράριο'),
    ('present', 'Παρόντες'),
    ('no_schedule', 'Χωρίς ωράριο αναφοράς'),
]
RISK_FLAGS = ('f_before_start', 'f_over', 'f_rest_work', 'f_unpaired', 'f_no_punch')
INFO_FLAGS = ('f_late', 'f_early', 'f_under')


def _utc(dt):
    return dt.astimezone(pytz.utc).replace(tzinfo=None)


def _minutes(delta):
    return max(0, int(delta.total_seconds() // 60))


def _is_manager(env):
    return env.user.has_group('hr.group_hr_manager') or env.user.has_group('base.group_system')


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    def _ergani_declared_periods(self, day, exclude_wto=None):
        """The schedule change submitted from Odoo for this day, if any: the
        last one wins (Ενιαίος σ. 14, 17). None when there is none."""
        self.ensure_one()
        emp = self.sudo()
        mode = emp.company_id.ergani_mode
        domain = [('employee_id', '=', emp.id), ('date', '=', day),
                  ('wto_id.kind', '=', 'daily'), ('state', 'in', ('sent', 'simulated'))]
        if mode != 'off':
            domain.append(('wto_id.environment', '=', mode))
        if exclude_wto:
            domain.append(('wto_id', 'not in', exclude_wto.ids))
        lines = self.env['ergani.wto.line'].sudo().search(domain)
        if not lines:
            return None
        last = max(lines.wto_id, key=lambda w: (w.submitted_at or w.create_date, w.id))
        lines = lines.filtered(lambda l: l.wto_id == last)
        work = lines.filtered(lambda l: l.category == 'work').sorted('time_from')
        if work:
            from .ergani_wto import _utc
            return 'work', [(_utc(day, l.time_from), _utc(day, l.time_to)) for l in work]
        if lines.filtered(lambda l: l.category == 'telework'):
            return 'telework', []
        return 'rest', []

    def _ergani_expected_periods(self, day, exclude_wto=None):
        """(kind, [(start_utc, end_utc)]) for one Athens day. kind is
        'work', 'rest' (no attendance that weekday or declared rest), 'leave'
        (attendance cancelled by a calendar leave), 'telework' (declared) or
        'none' (no usable schedule). A change declared from Odoo comes first,
        then the Odoo working schedule (PLAN_2.0 §4)."""
        self.ensure_one()
        declared = self._ergani_declared_periods(day, exclude_wto)
        if declared:
            return declared
        emp = self.sudo()
        cal = emp._get_calendars(day)[emp.id]
        if not cal or cal.flexible_hours or cal.duration_based:
            return 'none', []
        start = ATHENS.localize(datetime.combine(day, time.min))
        end = ATHENS.localize(datetime.combine(day + timedelta(days=1), time.min))
        res = emp.resource_id
        work = cal._work_intervals_batch(start, end, resources=res, tz=ATHENS)[res.id]
        if not list(work):
            planned = cal._attendance_intervals_batch(start, end, resources=res, tz=ATHENS)[res.id]
            return ('leave' if list(planned) else 'rest'), []
        lunch = [(s, e) for s, e, _r in cal._attendance_intervals_batch(
            start, end, resources=res, tz=ATHENS, lunch=True)[res.id]]
        # A lunch break is not the end of a work period (DESIGN §5.5): only a
        # real gap in the schedule splits the day.
        merged = []
        for s, e in sorted((s, e) for s, e, _r in work):
            if merged:
                ps, pe = merged[-1]
                if s <= pe or any(ls <= pe and le >= s for ls, le in lunch):
                    merged[-1] = (ps, max(pe, e))
                    continue
            merged.append((s, e))
        return 'work', [(_utc(s), _utc(e)) for s, e in merged]

    def _ergani_schedule_warning(self):
        """Text when the Odoo schedule cannot be trusted as «what the
        accountant declared» (PLAN_1.3 §2.2), else False."""
        self.ensure_one()
        emp = self.sudo()
        cal = emp._get_calendars(fields.Date.today())[emp.id]
        if not emp.ergani_schedule_confirmed:
            return _('%s: το ωράριο δεν έχει επιβεβαιωθεί με τον λογιστή.', emp.name)
        if cal:
            changed = max([cal.write_date] + cal.attendance_ids.mapped('write_date'))
            if changed and changed.date() > emp.ergani_schedule_confirmed:
                return _('%(emp)s: το ωράριο άλλαξε (%(when)s) μετά την επιβεβαίωση με τον '
                         'λογιστή (%(conf)s).', emp=emp.name,
                         when=changed.strftime('%d/%m/%Y'),
                         conf=emp.ergani_schedule_confirmed.strftime('%d/%m/%Y'))
        return False


class ErganiStatusWizard(models.TransientModel):
    _name = 'ergani.status.wizard'
    _description = 'ΕΡΓΑΝΗ: κατάσταση κινήσεων'

    def _default_from(self):
        return fields.Date.context_today(self).replace(day=1)

    date_from = fields.Date(string='Από', required=True, default=_default_from)
    date_to = fields.Date(string='Έως', required=True, default=fields.Date.context_today)
    employee_ids = fields.Many2many('hr.employee', string='Εργαζόμενοι',
                                    help='Κενό = όλοι όσοι χτυπούν κάρτα.')
    filter = fields.Selection(FILTERS, string='Φίλτρο', default='all', required=True)
    layout = fields.Selection([('detail', 'Αναλυτική'), ('summary', 'Συγκεντρωτική')],
                              string='Μορφή', default='detail', required=True)
    is_manager = fields.Boolean(compute='_compute_is_manager')
    disclaimer = fields.Char(default=DISCLAIMER, readonly=True)
    warning = fields.Text(readonly=True)
    line_ids = fields.One2many('ergani.status.line', 'wizard_id')

    def _compute_is_manager(self):
        for wiz in self:
            wiz.is_manager = _is_manager(self.env)

    def _ergani_employees(self):
        if _is_manager(self.env):
            return self.employee_ids.sudo() or self.env['hr.employee'].sudo().search([
                ('ergani_enabled', '=', True), ('company_id', 'in', self.env.companies.ids)])
        # An employee sees his own report only (PLAN_1.3 §2.5).
        own = self.env.user.employee_id.sudo()
        if not own:
            raise UserError(_('Ο χρήστης σας δεν είναι συνδεδεμένος με εργαζόμενο.'))
        return own

    def _ergani_build(self):
        self.ensure_one()
        if self.date_to < self.date_from:
            raise UserError(_('Η ημερομηνία «Έως» είναι πριν την «Από».'))
        if (self.date_to - self.date_from).days > 92:
            raise UserError(_('Έως 3 μήνες ανά αναφορά.'))
        Line = self.env['ergani.status.line']
        self.line_ids.unlink()
        employees = self._ergani_employees()
        vals_list, warnings = [], []
        for emp in employees:
            warning = emp._ergani_schedule_warning()
            if warning:
                warnings.append(warning)
            vals_list += Line._ergani_compute(emp, self.date_from, self.date_to,
                                              bool(warning))
        for vals in vals_list:
            vals['wizard_id'] = self.id
        Line.create(vals_list)
        self.warning = '\n'.join(warnings) or False

    def _ergani_action(self, view_mode, name):
        filt = self.filter
        context = {'ergani_disclaimer': DISCLAIMER}
        if filt != 'all':
            context['search_default_' + filt] = 1
        if self.layout == 'summary':
            context['group_by'] = ['employee_id']
        return {
            'type': 'ir.actions.act_window',
            'name': name,
            'res_model': 'ergani.status.line',
            'view_mode': view_mode,
            'domain': [('wizard_id', '=', self.id)],
            'context': context,
        }

    def action_view(self):
        self._ergani_build()
        return self._ergani_action('list,pivot,form', _(
            'Κατάσταση κινήσεων — ωράριο Odoo, όχι έλεγχος συμμόρφωσης'))

    def action_print(self):
        self._ergani_build()
        lines = self.line_ids
        if self.filter == 'risk':
            lines = lines.filtered('f_risk')
        elif self.filter == 'info':
            lines = lines.filtered(lambda l: any(l[f] for f in INFO_FLAGS))
        elif self.filter != 'all':
            lines = lines.filtered('f_' + self.filter)
        if not lines:
            raise UserError(_('Καμία γραμμή για το φίλτρο αυτό.'))
        return self.env.ref('l10n_gr_ergani_card.action_report_ergani_status').report_action(lines)

    @api.model
    def action_ergani_today(self):
        if not _is_manager(self.env):
            raise UserError(_('Μόνο για τον υπεύθυνο.'))
        today = fields.Date.context_today(self)
        wiz = self.create({'date_from': today, 'date_to': today})
        wiz._ergani_build()
        action = wiz._ergani_action('kanban,list,form', _('Σήμερα — ωράριο Odoo, όχι έλεγχος συμμόρφωσης'))
        action['help'] = _(
            '<p class="o_view_nocontent_smiling_face">Κανένας εργαζόμενος δεν χτυπά κάρτα</p>'
            '<p>Ανοίξτε ΕΡΓΑΝΗ → «Εργαζόμενοι» και ενεργοποιήστε τον διακόπτη «Χτυπά κάρτα» '
            '(χρειάζονται ΑΦΜ, επώνυμο, όνομα και χρήστης Odoo).</p>')
        action['views'] = [(self.env.ref('l10n_gr_ergani_card.ergani_status_line_view_kanban').id,
                            'kanban'), (False, 'list'), (False, 'form')]
        return action


class ErganiStatusLine(models.TransientModel):
    _name = 'ergani.status.line'
    _description = 'ΕΡΓΑΝΗ: γραμμή κατάστασης κινήσεων'
    _order = 'employee_id, date, sched_start, in_dt'

    wizard_id = fields.Many2one('ergani.status.wizard', required=True, ondelete='cascade',
                                index=True)
    employee_id = fields.Many2one('hr.employee', string='Εργαζόμενος', readonly=True)
    date = fields.Date(string='Ημέρα', readonly=True)
    day_status = fields.Selection([
        ('in', 'Μέσα'),
        ('out', 'Έξω (ολοκληρώθηκε)'),
        ('not_yet', 'Δεν ήρθε ακόμα'),
        ('no_punch', 'Χωρίς χτύπημα'),
        ('forgotten', 'Ξεχασμένη αποχώρηση'),
        ('rest', 'Ρεπό'),
        ('leave', 'Αργία / άδεια'),
        ('telework', 'Τηλεργασία'),
        ('rest_work', 'Χτύπημα σε ρεπό/αργία'),
        ('outside', 'Χτύπημα εκτός ωραρίου'),
        ('no_schedule', 'Χωρίς ωράριο αναφοράς'),
    ], string='Κατάσταση', readonly=True)
    sched_start = fields.Datetime(string='Ωράριο από', readonly=True)
    sched_end = fields.Datetime(string='Ωράριο έως', readonly=True)
    in_dt = fields.Datetime(string='Προσέλευση', readonly=True)
    out_dt = fields.Datetime(string='Αποχώρηση', readonly=True)
    in_card_id = fields.Many2one('ergani.card', string='Κάρτα προσέλευσης', readonly=True)
    out_card_id = fields.Many2one('ergani.card', string='Κάρτα αποχώρησης', readonly=True)
    send_state = fields.Selection([
        ('ok', 'Στάλθηκε'), ('pending', 'Σε αναμονή'), ('problem', 'Πρόβλημα αποστολής'),
        ('simulated', 'Προσομοίωση'),
    ], string='Αποστολή', readonly=True)
    scheduled_minutes = fields.Integer(string='Ωράριο (λ.)', aggregator='sum', readonly=True)
    worked_minutes = fields.Integer(string='Εργασία (λ.)', aggregator='sum', readonly=True)
    before_start_minutes = fields.Integer(string='Πριν την έναρξη (λ.)', aggregator='sum',
                                          readonly=True)
    after_end_minutes = fields.Integer(string='Μετά τη λήξη (λ.)', aggregator='sum',
                                       readonly=True)
    late_minutes = fields.Integer(string='Καθυστέρηση (λ.)', aggregator='sum', readonly=True)
    early_minutes = fields.Integer(string='Προαναχώρηση (λ.)', aggregator='sum', readonly=True)
    f_before_start = fields.Boolean(string='Πριν την έναρξη', readonly=True)
    f_over = fields.Boolean(string='Μετά τη λήξη / περισσότερη', readonly=True)
    f_rest_work = fields.Boolean(string='Σε ρεπό/αργία', readonly=True)
    f_unpaired = fields.Boolean(string='Μη ζευγαρωμένη', readonly=True)
    f_no_punch = fields.Boolean(string='Χωρίς χτύπημα', readonly=True)
    f_late = fields.Boolean(string='Καθυστέρηση', readonly=True)
    f_early = fields.Boolean(string='Προαναχώρηση', readonly=True)
    f_under = fields.Boolean(string='Λιγότερη εργασία', readonly=True)
    f_present = fields.Boolean(string='Παρών', readonly=True)
    f_no_schedule = fields.Boolean(string='Χωρίς ωράριο', readonly=True)
    f_risk = fields.Boolean(string='Χρειάζεται έλεγχος', readonly=True)
    schedule_warning = fields.Boolean(string='Ωράριο μη επιβεβαιωμένο', readonly=True)
    note = fields.Char(string='Σημείωση', readonly=True)

    # ── engine ───────────────────────────────────────────────────────────────

    @api.model
    def _ergani_cards(self, emp, date_from, date_to):
        mode = emp.company_id.ergani_mode
        domain = [('employee_id', '=', emp.id), ('card_type', '=', '0'),
                  ('reference_date', '>=', date_from), ('reference_date', '<=', date_to)]
        if mode != 'off':  # simulated punches never mix with real ones
            domain.append(('environment', '=', mode))
        by_day = defaultdict(list)
        for card in self.env['ergani.card'].sudo().search(domain, order='event_datetime'):
            by_day[card.reference_date].append(card)
        return by_day

    @staticmethod
    def _ergani_send_state(cards):
        states = set(cards.mapped('state'))
        if states & {'error', 'unknown'} or any(c.late and c.state == 'pending' for c in cards):
            return 'problem'
        if states & {'pending', 'sending'}:
            return 'pending'
        if states == {'simulated'}:
            return 'simulated'
        return 'ok' if states else False

    @api.model
    def _ergani_compute(self, emp, date_from, date_to, schedule_warning):
        tol = timedelta(minutes=emp.company_id.ergani_tolerance_minutes or 0)
        now = fields.Datetime.now()
        today = fields.Date.context_today(self)
        open_since = now - timedelta(hours=OPEN_SHIFT_HOURS)
        cards_by_day = self._ergani_cards(emp, date_from, date_to)
        flex = timedelta(minutes=emp.ergani_flex_minutes or 0)
        open_dates = emp._ergani_open_dates()
        lines = []
        day = date_from
        while day <= date_to:
            kind, periods = emp._ergani_expected_periods(day)
            pairs = []
            for in_card in cards_by_day.get(day, []):
                out_card = in_card.out_card_ids[:1]
                pairs.append((in_card, out_card))
            base = {'employee_id': emp.id, 'date': day, 'schedule_warning': schedule_warning}
            lines += self._ergani_day(base, kind, periods, pairs, tol, now, today, open_since,
                                      flex, open_dates)
            day += timedelta(days=1)
        return lines

    def _ergani_day(self, base, kind, periods, pairs, tol, now, today, open_since, flex,
                    open_dates):
        day = base['date']
        if kind != 'work' and not pairs:
            if kind == 'none' and day != today:
                return []
            return [dict(base, day_status={'none': 'no_schedule'}.get(kind, kind),
                         f_no_schedule=kind == 'none')]
        # Each pair goes to the period it overlaps most — not «in order», so a
        # missing afternoon punch cannot shift the whole day.
        assigned = defaultdict(list)
        stray = []
        for in_card, out_card in pairs:
            in_dt = in_card.event_datetime
            end = out_card.event_datetime if out_card else max(now, in_dt)
            best, best_overlap = None, timedelta(0)
            for idx, (ps, pe) in enumerate(periods):
                overlap = min(pe, end) - max(ps, in_dt)
                if overlap > best_overlap:
                    best, best_overlap = idx, overlap
            (assigned[best] if best is not None else stray).append((in_card, out_card))
        lines = []
        for idx, (ps, pe) in enumerate(periods):
            group = assigned.get(idx)
            if not group:
                started = ps + tol <= now
                lines.append(dict(
                    base, sched_start=ps, sched_end=pe,
                    scheduled_minutes=_minutes(pe - ps),
                    day_status='no_punch' if started else 'not_yet',
                    f_no_punch=started, f_risk=started,
                    note=_('Βεβαιωθείτε ότι δεν εργάστηκε.') if started else False))
                continue
            worked_total = timedelta(0)
            all_closed = True
            # Declared flexible arrival: arriving up to `flex` after the start is
            # on time and moves the end by the same amount (guide σ. 94–96).
            first_in = group[0][0].event_datetime
            shift = min(max(first_in - ps, timedelta(0)), flex)
            pe_eff = pe + shift
            for pos, (in_card, out_card) in enumerate(group):
                first, last = pos == 0, pos == len(group) - 1
                line = self._ergani_pair(base, in_card, out_card, now, open_since, day, open_dates)
                line.update(sched_start=ps, sched_end=pe)
                in_dt = in_card.event_datetime
                if first:
                    line['scheduled_minutes'] = _minutes(pe - ps)
                    line['before_start_minutes'] = _minutes(ps - in_dt)
                    line['late_minutes'] = _minutes(in_dt - ps - flex)
                    line['f_before_start'] = in_dt < ps
                    line['f_late'] = in_dt - ps - flex > tol
                if out_card:
                    worked_total += out_card.event_datetime - in_dt
                    if last:
                        out_dt = out_card.event_datetime
                        line['after_end_minutes'] = _minutes(out_dt - pe_eff)
                        line['early_minutes'] = _minutes(pe_eff - out_dt)
                        line['f_over'] = out_dt > pe_eff
                        line['f_early'] = pe_eff - out_dt > tol
                else:
                    all_closed = False
                lines.append(line)
            head = lines[-len(group)]
            if all_closed:
                # Work outside the schedule has no tolerance (PLAN_1.3 §2.3).
                head['f_over'] = head.get('f_over') or worked_total > pe - ps
                head['f_under'] = worked_total < (pe - ps) - tol
        for in_card, out_card in stray:
            line = self._ergani_pair(base, in_card, out_card, now, open_since, day, open_dates)
            if kind == 'none':
                line.update(day_status='no_schedule', f_no_schedule=True)
            elif kind in ('rest', 'leave', 'telework'):
                line.update(day_status='rest_work', f_rest_work=True,
                            note=_('Χτύπημα σε μέρα τηλεργασίας: η κάρτα είναι μόνο για φυσική '
                                   'παρουσία.') if kind == 'telework' else
                            _('Χτύπημα σε ρεπό ή αργία/άδεια.'))
            else:
                line.update(day_status='outside', f_over=True,
                            note=_('Χτύπημα έξω από κάθε περίοδο του ωραρίου.'))
            lines.append(line)
        for line in lines:
            line['f_risk'] = any(line.get(f) for f in RISK_FLAGS)
        return lines

    def _ergani_pair(self, base, in_card, out_card, now, open_since, day, open_dates):
        in_dt = in_card.event_datetime
        line = dict(base, in_card_id=in_card.id, in_dt=in_dt, f_present=True,
                    send_state=self._ergani_send_state(in_card | out_card))
        if out_card:
            line.update(out_card_id=out_card.id, out_dt=out_card.event_datetime,
                        worked_minutes=_minutes(out_card.event_datetime - in_dt),
                        day_status='out')
        elif in_dt >= open_since and day in open_dates:
            line['day_status'] = 'in'
        else:
            # Same condition as hr_employee._ergani_flag_forgotten.
            line.update(day_status='forgotten', f_unpaired=True, note=_(
                'Η επαναλαμβανόμενη μη υποβολή αποχώρησης είναι αιτία ελέγχου.'))
        return line
