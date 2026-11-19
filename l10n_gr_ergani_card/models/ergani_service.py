"""What the ΕΡΓΑΝΗ account can do, and the type codes of working-time
organisation (2.0, PLAN_2.0 §3, §6α).

`ergani.service` is refreshed by «Δοκιμή σύνδεσης»: it answers the open
question whether ΕΡΓΑΝΗ lets us *read* declared schedules and leaves, and
which document codes exist for leaves and cancellation.

`ergani.worktime.type` holds the f_type codes (ΕΡΓ, ΤΗΛ, ΑΝ, ΜΕ, άδειες). The
four schedule codes are seeded from the guide (§4); the full list comes from
EX_BASE_03 «WorkTimeType», because the sample says «ΑΔ.ΚΑΝ» where the guide
says «ΑΔΚΑΝ» and only ΕΡΓΑΝΗ can settle it.
"""
import json

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .ergani_client import ErganiClient, ErganiError
from .ergani_sync import _company_ready, _dicts


class ErganiService(models.Model):
    _name = 'ergani.service'
    _description = 'ΕΡΓΑΝΗ: διαθέσιμη υπηρεσία'
    _order = 'kind, code'
    _rec_name = 'code'

    company_id = fields.Many2one('res.company', required=True, readonly=True)
    kind = fields.Selection([('service', 'Υπηρεσία (ExecuteService)'),
                             ('submission', 'Υποβολή (Documents)')],
                            string='Είδος', required=True, readonly=True)
    code = fields.Char(string='Κωδικός', required=True, readonly=True)
    ergani_id = fields.Char(string='ID ΕΡΓΑΝΗ', readonly=True)
    description = fields.Char(string='Περιγραφή', readonly=True)
    parameters = fields.Text(string='Παράμετροι', readonly=True)
    last_seen = fields.Datetime(string='Τελευταία φορά', readonly=True)

    @api.model
    def _ergani_refresh(self, company):
        """Store ServicesList + Lookup/Submissions. Never blocks the test:
        a failure here is logged in «Αρχείο υποβολών» and ignored."""
        client = ErganiClient(company)
        now = fields.Datetime.now()
        for kind, fetch in (('service', client.list_services),
                            ('submission', client.list_submissions)):
            try:
                rows = fetch()
            except ErganiError:
                continue
            for row in rows if isinstance(rows, list) else []:
                if not isinstance(row, dict):
                    continue
                code = str(row.get('name') or row.get('code') or '').strip()
                if not code:
                    continue
                vals = {
                    'ergani_id': str(row.get('id') or '') or False,
                    'description': str(row.get('description') or '') or False,
                    'parameters': json.dumps(row.get('parameters'), ensure_ascii=False)
                    if row.get('parameters') else False,
                    'last_seen': now,
                }
                rec = self.sudo().search([('company_id', '=', company.id),
                                          ('kind', '=', kind), ('code', '=', code)], limit=1)
                if rec:
                    rec.write(vals)
                else:
                    self.sudo().create(dict(vals, company_id=company.id, kind=kind, code=code))


class ErganiWorktimeType(models.Model):
    _name = 'ergani.worktime.type'
    _description = 'ΕΡΓΑΝΗ: τύπος οργάνωσης χρόνου εργασίας'
    _order = 'category, code'

    code = fields.Char(string='Κωδικός (f_type)', required=True)
    name = fields.Char(string='Περιγραφή', required=True)
    category = fields.Selection([
        ('work', 'Εργασία'),
        ('telework', 'Τηλεργασία'),
        ('no_work', 'Χωρίς εργασία (ρεπό / μη εργασία)'),
        ('leave', 'Άδεια'),
        ('hourly_leave', 'Ωροάδεια'),
    ], string='Κατηγορία', required=True)
    verified = fields.Boolean(string='Από το ΕΡΓΑΝΗ', readonly=True,
                              help='Ήρθε από το ΕΡΓΑΝΗ (EX_BASE_03). Χωρίς σημάδι: από τον οδηγό, '
                                   'μη επιβεβαιωμένο.')
    active = fields.Boolean(default=True)

    _code_unique = models.Constraint('UNIQUE (code)', 'Ο κωδικός υπάρχει ήδη.')

    def _compute_display_name(self):
        for t in self:
            t.display_name = '%s — %s' % (t.code, t.name or '')

    @staticmethod
    def _ergani_category(code):
        compact = code.replace('.', '').upper()
        if compact == 'ΤΗΛ':
            return 'telework'
        if compact in ('ΑΝ', 'ΜΕ', 'ΧΥΠ'):
            return 'no_work'
        if compact.startswith('ΩΑ'):
            return 'hourly_leave'
        if compact.startswith('ΑΔ'):
            return 'leave'
        return 'work'

    def action_ergani_sync(self):
        if not self.env.user.has_group('base.group_system'):
            raise UserError(_('Μόνο ο διαχειριστής.'))
        return self._ergani_sync()

    @api.model
    def _ergani_sync(self):
        company = self.env.company
        _company_ready(company)
        try:
            data = ErganiClient(company).execute_service('EX_BASE_03', {'Parameter': 'WorkTimeType'})
        except ErganiError as e:
            raise UserError(_('ΕΡΓΑΝΗ: %s', e)) from e
        found = 0
        for row in _dicts(data):
            values = [str(v).strip() for v in row.values() if isinstance(v, (str, int))]
            # a short code without spaces (ΕΡΓ, ΑΔ.ΚΑΝ) and a longer description
            code = next((v for v in values if v and len(v) <= 10 and ' ' not in v), None)
            name = next((v for v in values if v and v != code), None)
            if not (code and name):
                continue
            vals = {'name': name, 'verified': True, 'active': True,
                    'category': self._ergani_category(code)}
            rec = self.with_context(active_test=False).search([('code', '=', code)], limit=1)
            if rec:
                rec.write(vals)
            else:
                self.create(dict(vals, code=code))
            found += 1
        if not found:
            raise UserError(_('Το ΕΡΓΑΝΗ δεν επέστρεψε τύπους σε μορφή που αναγνωρίζεται. '
                              'Δείτε το «Αρχείο υποβολών».'))
        return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {
            'type': 'success', 'message': _('Τύποι από το ΕΡΓΑΝΗ: %s.', found)}}


class ErganiServiceProbe(models.TransientModel):
    """«Δοκιμή» of a read service (EX_BASE_05/07/08…): fills the parameters the
    ServicesList names and shows ΕΡΓΑΝΗ's raw answer, so the shape can be seen
    before code depends on it. Only for the system admin: EX_BASE_07 returns
    every employee's punches."""
    _name = 'ergani.service.probe'
    _description = 'ΕΡΓΑΝΗ: δοκιμή υπηρεσίας'

    service_id = fields.Many2one('ergani.service', required=True, readonly=True)
    date = fields.Date(string='Ημερομηνία', default=fields.Date.context_today)
    # ponytail: the Date format of ExecuteService is undocumented — a knob until the trial shows it.
    date_format = fields.Selection([('%Y-%m-%d', 'ΕΕΕΕ-ΜΜ-ΗΗ'), ('%d/%m/%Y', 'ΗΗ/ΜΜ/ΕΕΕΕ'),
                                    ('%Y%m%d', 'ΕΕΕΕΜΜΗΗ')],
                                   string='Μορφή ημερομηνίας', default='%Y-%m-%d', required=True)
    branch_aa = fields.Integer(string='Α/Α παραρτήματος',
                               default=lambda self: self.env.company.ergani_branch_aa)
    afm = fields.Char(string='ΑΦΜ')
    parameters_sent = fields.Text(string='Παράμετροι που στάλθηκαν', readonly=True)
    result = fields.Text(string='Απάντηση ΕΡΓΑΝΗ', readonly=True)

    def _ergani_params(self):
        try:
            spec = json.loads(self.service_id.parameters or '[]')
        except ValueError:
            spec = []
        date = self.date or fields.Date.context_today(self)
        values = {'pararthmaaa': self.branch_aa or 0, 'date': date.strftime(self.date_format),
                  'afm': self.afm or '', 'reportyear': date.year, 'reportmonth': date.month}
        params = {}
        for p in spec if isinstance(spec, list) else []:
            name = str((p or {}).get('name') or '')
            value = values.get(name.lower())
            if value in (None, '') and not (p or {}).get('isRequired'):
                continue
            if value in (None, ''):
                raise UserError(_('Η παράμετρος «%s» δεν συμπληρώνεται αυτόματα.', name))
            params[name] = value
        return params

    def action_run(self):
        self.ensure_one()
        if not self.env.user.has_group('base.group_system'):
            raise UserError(_('Μόνο για τον διαχειριστή.'))
        company = self.service_id.company_id
        _company_ready(company)
        params = self._ergani_params()
        try:
            data = ErganiClient(company).execute_service(self.service_id.code, params)
            result = json.dumps(data, ensure_ascii=False, indent=2)
        except ErganiError as e:
            result = _('Σφάλμα: %s', e)
        self.write({'parameters_sent': json.dumps(params, ensure_ascii=False),
                    'result': result[:200000]})
        return {'type': 'ir.actions.act_window', 'res_model': self._name, 'res_id': self.id,
                'view_mode': 'form', 'target': 'new'}


class ErganiServiceProbeAction(models.Model):
    _inherit = 'ergani.service'

    def action_ergani_probe(self):
        self.ensure_one()
        if self.kind != 'service':
            raise UserError(_('Δοκιμή μόνο για υπηρεσίες ανάγνωσης (ExecuteService).'))
        probe = self.env['ergani.service.probe'].create({'service_id': self.id})
        return {'type': 'ir.actions.act_window', 'res_model': probe._name, 'res_id': probe.id,
                'view_mode': 'form', 'target': 'new', 'name': self.code}
