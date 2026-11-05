"""ΕΡΓΑΝΗ → «Εργαζόμενοι» (1.4): the employee data ΕΡΓΑΝΗ holds, the list
screen and its actions. Only what the work card needs is kept — no pay,
birth date, parents, family or education (GDPR minimisation, user 2026-10-24)."""
from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .ergani_status import _is_manager


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    ergani_amka = fields.Char(string='ΑΜΚΑ', groups='hr.group_hr_user')
    ergani_hire_date = fields.Date(string='Ημ/νία πρόσληψης (ΕΡΓΑΝΗ)', groups='hr.group_hr_user')
    ergani_branch_id = fields.Many2one(
        'ergani.branch', string='Παράρτημα ΕΡΓΑΝΗ', groups='hr.group_hr_user',
        help='Το παράρτημα που δηλώνεται στις κάρτες του. Κενό = το παράρτημα των Ρυθμίσεων.')
    ergani_relation = fields.Char(string='Σχέση εργασίας', groups='hr.group_hr_user',
                                  help='Π.χ. «Αορίστου Χρόνου» (από το ΕΡΓΑΝΗ).')
    ergani_employment = fields.Char(string='Καθεστώς', groups='hr.group_hr_user',
                                    help='Πλήρης / Μερική (από το ΕΡΓΑΝΗ).')
    ergani_weekly_hours = fields.Float(string='Ώρες / εβδομάδα (ΕΡΓΑΝΗ)', groups='hr.group_hr_user')
    ergani_specialty = fields.Char(string='Ειδικότητα (ΕΡΓΑΝΗ)', groups='hr.group_hr_user')
    ergani_last_sync = fields.Datetime(string='Συγχρονισμός ΕΡΓΑΝΗ', readonly=True,
                                       groups='hr.group_hr_user')
    ergani_in_ergani = fields.Boolean(
        string='Στο ΕΡΓΑΝΗ', readonly=True, groups='hr.group_hr_user',
        help='Βρέθηκε στον τελευταίο συγχρονισμό με τη μηνιαία κατάσταση του ΕΡΓΑΝΗ.')
    ergani_today_state = fields.Selection(
        [('in', 'Μέσα'), ('out', 'Έξω'), ('none', '—')], string='Σήμερα',
        compute='_compute_ergani_today_state', groups='hr.group_hr_user')
    ergani_card_count = fields.Integer(compute='_compute_ergani_card_count',
                                       groups='hr.group_hr_user')

    def _compute_ergani_today_state(self):
        today = self._ergani_today()
        Card = self.env['ergani.card'].sudo()
        for emp in self:
            if not emp.id:
                emp.ergani_today_state = 'none'
            elif emp._ergani_open_in_card():
                emp.ergani_today_state = 'in'
            elif Card.search_count([('employee_id', '=', emp.id),
                                    ('reference_date', '=', today)], limit=1):
                emp.ergani_today_state = 'out'
            else:
                emp.ergani_today_state = 'none'

    def _compute_ergani_card_count(self):
        counts = dict(self.env['ergani.card'].sudo()._read_group(
            [('employee_id', 'in', self.ids)], ['employee_id'], ['__count']))
        for emp in self:
            emp.ergani_card_count = counts.get(emp, 0)

    def _ergani_check_manager(self):
        if not _is_manager(self.env):
            raise UserError(_('Μόνο για τον υπεύθυνο.'))

    def action_ergani_cards(self):
        self.ensure_one()
        self._ergani_check_manager()
        return {
            'type': 'ir.actions.act_window', 'name': _('Κάρτες — %s', self.name),
            'res_model': 'ergani.card', 'view_mode': 'list,form',
            'domain': [('employee_id', '=', self.id)],
        }

    def action_ergani_report(self):
        self._ergani_check_manager()
        return {
            'type': 'ir.actions.act_window', 'name': _('Κατάσταση κινήσεων'),
            'res_model': 'ergani.status.wizard', 'view_mode': 'form', 'target': 'new',
            'context': {'default_employee_ids': self.ids},
        }

    def action_ergani_sync_employees(self):
        self._ergani_check_manager()
        return self.env['ergani.sync.employee'].create({})._ergani_load()

    def action_ergani_sync_branches(self):
        self._ergani_check_manager()
        return self.env['ergani.branch']._ergani_sync()
