from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .ergani_client import ErganiClient, ErganiError
from .ergani_sync import _company_ready, _dicts


class ErganiDelayReason(models.Model):
    """Λόγοι εκπρόθεσμης δήλωσης έναρξης/λήξης (EX_BASE_03, Parameter =
    WorkCardDelayReason — Ενιαίος Οδηγός 01.01.2024 σ. 102–103). Loaded from
    ΕΡΓΑΝΗ instead of guessed; the law allows only technical reasons."""
    _name = 'ergani.delay.reason'
    _description = 'ΕΡΓΑΝΗ: αιτιολογία εκπρόθεσμης δήλωσης'
    _order = 'code'

    code = fields.Char(string='Κωδικός', required=True)
    name = fields.Char(string='Περιγραφή', required=True)
    active = fields.Boolean(default=True)
    last_sync = fields.Datetime(string='Συγχρονισμός', readonly=True)

    _code_unique = models.Constraint('UNIQUE (code)', 'Ο κωδικός υπάρχει ήδη.')

    def _compute_display_name(self):
        for reason in self:
            reason.display_name = '%s — %s' % (reason.code, reason.name or '')

    @api.model
    def _ergani_sync(self):
        company = self.env.company
        _company_ready(company)
        try:
            data = ErganiClient(company).execute_service(
                'EX_BASE_03', {'Parameter': 'WorkCardDelayReason'})
        except ErganiError as e:
            raise UserError(_('ΕΡΓΑΝΗ: %s', e)) from e
        found = 0
        # Response shape is not in the guide: take every object that has one
        # short numeric value (the code) and one text value (the description).
        for row in _dicts(data):
            values = [str(v).strip() for v in row.values() if isinstance(v, (str, int))]
            code = next((v for v in values if v.isdigit() and len(v) <= 10), None)
            name = next((v for v in values if v and not v.isdigit()), None)
            if not (code and name):
                continue
            vals = {'name': name, 'last_sync': fields.Datetime.now(), 'active': True}
            reason = self.with_context(active_test=False).search([('code', '=', code)], limit=1)
            if reason:
                reason.write(vals)
            else:
                self.create(dict(vals, code=code))
            found += 1
        if not found:
            raise UserError(_('Το ΕΡΓΑΝΗ δεν επέστρεψε αιτιολογίες σε μορφή που αναγνωρίζεται. '
                              'Δείτε το «Αρχείο υποβολών».'))
        return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {
            'type': 'success', 'message': _('Αιτιολογίες από το ΕΡΓΑΝΗ: %s.', found)}}
