"""Συγχρονισμός από το ΕΡΓΑΝΗ (1.4).

Employees come from EX_BASE_04 (μηνιαία κατάσταση, guide γρ. 474–704) and are
matched by ΑΦΜ only — names are not unique and a wrong match would declare one
person's hours under another's name. Nothing is created or changed until the
manager presses «Εφαρμογή» (user 2026-10-24). Branches come from EX_BASE_02,
whose response shape is not in the guide: the parser is deliberately loose
and UNVERIFIED until trial.
"""
from datetime import date

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .ergani_client import ErganiClient, ErganiError
from .hr_employee import _ergani_name


def _company_ready(company):
    if company.ergani_mode not in ('trial', 'production'):
        raise UserError(_(
            'Ο συγχρονισμός χρειάζεται σύνδεση με το ΕΡΓΑΝΗ: Ρυθμίσεις ΕΡΓΑΝΗ → κατάσταση '
            '«Δοκιμαστικό (trial)» ή «Παραγωγικό», με χρήστη και κωδικό ΕΡΓΑΝΗ.'))


def _dicts(data):
    """Every dict inside a JSON value, depth-first."""
    stack, out = [data], []
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            out.append(item)
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)
    return out


def _date(value):
    try:
        return date.fromisoformat(str(value or '')[:10])
    except ValueError:
        return False


def _float(value):
    try:
        return float(str(value).replace(',', '.'))
    except (TypeError, ValueError):
        return 0.0


class ErganiBranch(models.Model):
    _inherit = 'ergani.branch'

    @api.model
    def _ergani_sync(self):
        company = self.env.company
        _company_ready(company)
        try:
            data = ErganiClient(company).execute_service('EX_BASE_02')
        except ErganiError as e:
            raise UserError(_('ΕΡΓΑΝΗ: %s', e)) from e
        found = 0
        for row in _dicts(data):
            keys = {k.lower(): k for k in row}
            aa_key = next((keys[k] for k in keys if k in ('aa', 'f_aa', 'pararthma_aa', 'parartima_aa',
                                                          'f_pararthma_aa', 'kodikos')), None)
            if not aa_key or not str(row[aa_key]).strip().isdigit():
                continue
            name_key = next((keys[k] for k in keys if any(
                s in k for s in ('perigraf', 'onomas', 'eponim', 'name', 'titlos'))), None)
            addr_key = next((keys[k] for k in keys if any(
                s in k for s in ('dieuth', 'odos', 'address'))), None)
            aa = int(row[aa_key])
            vals = {'name': str(row.get(name_key) or _('Παράρτημα %s', aa)),
                    'address': str(row.get(addr_key) or '') or False,
                    'last_sync': fields.Datetime.now(), 'active': True}
            branch = self.with_context(active_test=False).search(
                [('company_id', '=', company.id), ('aa', '=', aa)], limit=1)
            if branch:
                branch.write(vals)
            else:
                self.create(dict(vals, aa=aa, company_id=company.id))
            found += 1
        if not found:
            raise UserError(_('Το ΕΡΓΑΝΗ δεν επέστρεψε παραρτήματα σε μορφή που αναγνωρίζεται. '
                              'Δείτε το «Αρχείο υποβολών».'))
        return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {
            'type': 'success', 'message': _('Παραρτήματα από το ΕΡΓΑΝΗ: %s.', found),
            'next': {'type': 'ir.actions.act_window_close'}}}


class ErganiSyncEmployee(models.TransientModel):
    _name = 'ergani.sync.employee'
    _description = 'ΕΡΓΑΝΗ: συγχρονισμός εργαζομένων'

    period = fields.Char(string='Μηνιαία κατάσταση', readonly=True)
    line_ids = fields.One2many('ergani.sync.employee.line', 'wizard_id')

    def _ergani_fetch(self, company):
        """EX_BASE_04 of this month, else last month (the current month may be
        empty early on)."""
        client = ErganiClient(company)
        for back in (0, 1):
            day = date.today() - relativedelta(months=back)
            try:
                data = client.execute_service('EX_BASE_04', {
                    'ReportYear': day.year, 'ReportMonth': day.month})
            except ErganiError as e:
                raise UserError(_('ΕΡΓΑΝΗ: %s', e)) from e
            rows = [d for d in _dicts(data) if d.get('f_afm')]
            if rows:
                return rows, '%02d/%s' % (day.month, day.year)
        return [], False

    def _ergani_load(self):
        self.ensure_one()
        company = self.env.company
        _company_ready(company)
        rows, period = self._ergani_fetch(company)
        if not rows:
            raise UserError(_('Η μηνιαία κατάσταση του ΕΡΓΑΝΗ δεν έχει εργαζόμενους '
                              '(τρέχων και προηγούμενος μήνας).'))
        Employee = self.env['hr.employee'].sudo().with_context(active_test=False)
        by_afm = {e.ergani_afm: e for e in Employee.search(
            [('company_id', '=', company.id), ('ergani_afm', '!=', False)])}
        branches = {b.aa: b for b in self.env['ergani.branch'].search(
            [('company_id', '=', company.id)])}
        lines, seen = [], set()
        for row in rows:
            afm = ''.join(c for c in str(row.get('f_afm')) if c.isdigit())
            if not afm or afm in seen:
                continue
            seen.add(afm)
            aa = str(row.get('f_pararthma_aa') or '').strip()
            emp = by_afm.get(afm)
            lines.append((0, 0, {
                'afm': afm,
                'last_name': _ergani_name(row.get('f_eponimo') or ''),
                'first_name': _ergani_name(row.get('f_onoma') or ''),
                'amka': str(row.get('f_amka') or '') or False,
                'hire_date': _date(row.get('f_date_proslipsis')),
                'branch_aa': int(aa) if aa.isdigit() else False,
                'branch_id': branches[int(aa)].id if aa.isdigit() and int(aa) in branches else False,
                'relation': row.get('f_sxesh_apasxolhshs') or False,
                'employment': row.get('f_kathestos') or False,
                'weekly_hours': _float(row.get('f_week_wres')),
                'specialty': row.get('f_step') or False,
                'status': 'match' if emp else 'new',
                'employee_id': emp.id if emp else False,
                'action': 'update' if emp else 'create',
            }))
        # In Odoo with a ΑΦΜ but not in ΕΡΓΑΝΗ this month: shown, never touched.
        for afm, emp in by_afm.items():
            if afm not in seen:
                lines.append((0, 0, {
                    'afm': afm, 'last_name': emp.ergani_last_name,
                    'first_name': emp.ergani_first_name, 'status': 'missing',
                    'employee_id': emp.id, 'action': 'skip'}))
        self.write({'period': period, 'line_ids': lines})
        return {
            'type': 'ir.actions.act_window', 'name': _('Συγχρονισμός από ΕΡΓΑΝΗ'),
            'res_model': self._name, 'res_id': self.id, 'view_mode': 'form', 'target': 'new',
        }

    def action_apply(self):
        self.ensure_one()
        if not self.env.user.has_group('hr.group_hr_manager') and \
                not self.env.user.has_group('base.group_system'):
            raise UserError(_('Μόνο για τον υπεύθυνο.'))
        Employee = self.env['hr.employee'].sudo()
        now = fields.Datetime.now()
        linked = self.line_ids.filtered(lambda l: l.action in ('update', 'link')).employee_id
        if len(linked) != len(self.line_ids.filtered(lambda l: l.action in ('update', 'link'))):
            raise UserError(_('Ο ίδιος εργαζόμενος του Odoo επιλέχθηκε σε δύο γραμμές.'))
        done = 0
        for line in self.line_ids:
            vals = line._ergani_vals(now)
            if line.action in ('update', 'link'):
                if not line.employee_id:
                    raise UserError(_('%s: επιλέξτε εργαζόμενο του Odoo για σύνδεση.', line.afm))
                other = Employee.search([('ergani_afm', '=', line.afm),
                                         ('id', '!=', line.employee_id.id)], limit=1)
                if other:
                    raise UserError(_('Ο ΑΦΜ %(afm)s ανήκει ήδη στον %(emp)s.',
                                      afm=line.afm, emp=other.name))
                line.employee_id.sudo().write(vals)
                done += 1
            elif line.action == 'create':
                Employee.create(dict(vals, name=' '.join(
                    filter(None, [line.first_name, line.last_name])).title() or line.afm))
                done += 1
        missing = self.line_ids.filtered(lambda l: l.status == 'missing').employee_id
        missing.sudo().write({'ergani_in_ergani': False})
        return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {
            'type': 'success', 'message': _('Ενημερώθηκαν / δημιουργήθηκαν %s εργαζόμενοι.', done),
            'next': {'type': 'ir.actions.act_window_close'}}}


class ErganiSyncEmployeeLine(models.TransientModel):
    _name = 'ergani.sync.employee.line'
    _description = 'ΕΡΓΑΝΗ: εργαζόμενος συγχρονισμού'
    _order = 'status, last_name'

    wizard_id = fields.Many2one('ergani.sync.employee', required=True, ondelete='cascade')
    status = fields.Selection([
        ('match', 'Υπάρχει (ίδιος ΑΦΜ)'),
        ('new', 'Νέος — δεν υπάρχει στο Odoo'),
        ('missing', 'Στο Odoo, όχι στο ΕΡΓΑΝΗ'),
    ], string='Αντιστοίχιση', readonly=True)
    action = fields.Selection([
        ('update', 'Ενημέρωση'),
        ('create', 'Δημιουργία εργαζομένου'),
        ('link', 'Σύνδεση με υπάρχοντα'),
        ('skip', 'Παράλειψη'),
    ], string='Ενέργεια', required=True, default='skip')
    employee_id = fields.Many2one('hr.employee', string='Εργαζόμενος Odoo')
    afm = fields.Char(string='ΑΦΜ', readonly=True)
    last_name = fields.Char(string='Επώνυμο', readonly=True)
    first_name = fields.Char(string='Όνομα', readonly=True)
    amka = fields.Char(string='ΑΜΚΑ', readonly=True)
    hire_date = fields.Date(string='Πρόσληψη', readonly=True)
    branch_aa = fields.Integer(string='Α/Α παραρτ.', readonly=True)
    branch_id = fields.Many2one('ergani.branch', string='Παράρτημα', readonly=True)
    relation = fields.Char(string='Σχέση', readonly=True)
    employment = fields.Char(string='Καθεστώς', readonly=True)
    weekly_hours = fields.Float(string='Ώρες/εβδ.', readonly=True)
    specialty = fields.Char(string='Ειδικότητα', readonly=True)

    def _ergani_vals(self, now):
        self.ensure_one()
        vals = {
            'ergani_afm': self.afm, 'ergani_last_name': self.last_name,
            'ergani_first_name': self.first_name, 'ergani_amka': self.amka,
            'ergani_hire_date': self.hire_date, 'ergani_relation': self.relation,
            'ergani_employment': self.employment, 'ergani_weekly_hours': self.weekly_hours,
            'ergani_specialty': self.specialty, 'ergani_last_sync': now,
            'ergani_in_ergani': True,
        }
        if self.branch_id:
            vals['ergani_branch_id'] = self.branch_id.id
        return vals
