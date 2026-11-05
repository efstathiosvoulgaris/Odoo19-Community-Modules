"""«Νέα αλλαγή ωραρίου» and «Παράταση σήμερα» (PLAN_2.0 §4 screens 2–3).

Makes one draft declaration per employee covering every day of the range,
optionally submitting at once. «Παράταση» keeps today's schedule as it is and
moves the end of the last period to the new time — the only legal way to stay
longer once work has started (PLAN_2.0 §2.2).
"""
from datetime import datetime, timedelta

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .ergani_status import _is_manager
from .ergani_wto import DAY_TYPE_CODES

ATHENS = pytz.timezone('Europe/Athens')


def _local_hours(dt_utc):
    local = pytz.utc.localize(dt_utc).astimezone(ATHENS)
    return local.hour + local.minute / 60.0


class ErganiWtoWizard(models.TransientModel):
    _name = 'ergani.wto.wizard'
    _description = 'ΕΡΓΑΝΗ: νέα αλλαγή ωραρίου'

    mode = fields.Selection([('change', 'Αλλαγή ωραρίου'), ('extend', 'Παράταση σήμερα')],
                            default='change', required=True)
    employee_ids = fields.Many2many('hr.employee', string='Εργαζόμενοι', required=True,
                                    domain="[('ergani_enabled', '=', True)]")
    date_from = fields.Date(string='Από', required=True, default=fields.Date.context_today)
    date_to = fields.Date(string='Έως', required=True, default=fields.Date.context_today)
    day_type = fields.Selection([
        ('work', 'Εργασία'), ('telework', 'Τηλεργασία'),
        ('rest', 'Ανάπαυση / ρεπό'), ('no_work', 'Μη εργασία'),
    ], string='Τύπος ημέρας', default='work', required=True)
    interval_ids = fields.One2many('ergani.wto.wizard.interval', 'wizard_id', string='Διαστήματα')
    extend_until = fields.Float(string='Παράταση έως')
    current_schedule = fields.Char(string='Τρέχον ωράριο', readonly=True)
    comments = fields.Char(string='Σχόλια', size=200)

    @api.onchange('employee_ids', 'date_from', 'mode')
    def _onchange_prefill(self):
        """Start from what applies today, so a change edits rather than retypes."""
        emp = self.employee_ids[:1]
        if self.mode == 'extend':
            self.date_from = self.date_to = fields.Date.context_today(self)
        if not emp or not self.date_from:
            return
        _kind, periods = emp._origin._ergani_expected_periods(self.date_from)
        text = ', '.join('%s–%s' % (self._fmt(_local_hours(s)), self._fmt(_local_hours(e)))
                         for s, e in periods)
        self.current_schedule = text or _('χωρίς ωράριο')
        if self.mode == 'change' and not self.interval_ids and periods:
            self.interval_ids = [(0, 0, {'time_from': _local_hours(s), 'time_to': _local_hours(e)})
                                 for s, e in periods]

    @staticmethod
    def _fmt(value):
        minutes = int(round(value * 60))
        return '%02d:%02d' % divmod(minutes, 60)

    def _ergani_type(self, day_type):
        code = DAY_TYPE_CODES[day_type]
        wtype = self.env['ergani.worktime.type'].search([('code', '=', code)], limit=1)
        if not wtype:
            raise UserError(_('Λείπει ο τύπος %s. Διαμόρφωση → Τύποι ωραρίου.', code))
        return wtype

    def _ergani_day_lines(self, day):
        if self.mode == 'extend':
            emp = self.employee_ids
            _kind, periods = emp._ergani_expected_periods(day)
            if not periods:
                raise UserError(_('%s δεν έχει ωράριο σήμερα για να παραταθεί.', emp.name))
            spans = [[_local_hours(s), _local_hours(e)] for s, e in periods]
            if self.extend_until <= spans[-1][1]:
                raise UserError(_('Η παράταση πρέπει να είναι μετά το %s.', self._fmt(spans[-1][1])))
            spans[-1][1] = self.extend_until
            wtype = self._ergani_type('work')
            return [{'date': day, 'type_id': wtype.id, 'time_from': f, 'time_to': t}
                    for f, t in spans]
        wtype = self._ergani_type(self.day_type)
        if self.day_type in ('rest', 'no_work'):
            return [{'date': day, 'type_id': wtype.id, 'time_from': 0.0, 'time_to': 0.0}]
        if not self.interval_ids:
            raise UserError(_('Προσθέστε τουλάχιστον ένα διάστημα.'))
        return [{'date': day, 'type_id': wtype.id, 'time_from': i.time_from, 'time_to': i.time_to}
                for i in self.interval_ids.sorted('time_from')]

    def _ergani_create(self):
        if not _is_manager(self.env):
            raise UserError(_('Μόνο για τον υπεύθυνο.'))
        if self.date_to < self.date_from:
            raise UserError(_('Η ημερομηνία «Έως» είναι πριν την «Από».'))
        if (self.date_to - self.date_from).days > 62:
            raise UserError(_('Έως δύο μήνες ανά δήλωση.'))
        if self.mode == 'extend' and len(self.employee_ids) != 1:
            raise UserError(_('Η παράταση γίνεται για έναν εργαζόμενο.'))
        Wto = self.env['ergani.wto']
        created = Wto.browse()
        for emp in self.employee_ids:
            lines, day = [], self.date_from
            while day <= self.date_to:
                lines += [(0, 0, vals) for vals in self._ergani_day_lines(day)]
                day += timedelta(days=1)
            created |= Wto.create({
                'kind': 'daily', 'employee_id': emp.id, 'date_from': self.date_from,
                'date_to': self.date_to, 'comments': self.comments, 'line_ids': lines,
            })
        return created

    def _ergani_open(self, records):
        if len(records) == 1:
            return {'type': 'ir.actions.act_window', 'res_model': 'ergani.wto',
                    'res_id': records.id, 'view_mode': 'form'}
        return {'type': 'ir.actions.act_window', 'res_model': 'ergani.wto', 'name': _('Δηλώσεις'),
                'view_mode': 'list,form', 'domain': [('id', 'in', records.ids)]}

    def action_draft(self):
        return self._ergani_open(self._ergani_create())

    def action_submit(self):
        records = self._ergani_create()
        records.action_submit()
        return self._ergani_open(records)


class ErganiWtoWizardInterval(models.TransientModel):
    _name = 'ergani.wto.wizard.interval'
    _description = 'ΕΡΓΑΝΗ: διάστημα αλλαγής ωραρίου'
    _order = 'time_from'

    wizard_id = fields.Many2one('ergani.wto.wizard', required=True, ondelete='cascade')
    time_from = fields.Float(string='Από', required=True)
    time_to = fields.Float(string='Έως', required=True)
