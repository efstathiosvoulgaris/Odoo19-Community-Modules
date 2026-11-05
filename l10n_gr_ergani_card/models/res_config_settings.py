from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    ergani_mode = fields.Selection(related='company_id.ergani_mode', readonly=False)
    ergani_username = fields.Char(related='company_id.ergani_username', readonly=False)
    ergani_password = fields.Char(related='company_id.ergani_password', readonly=False)
    ergani_branch_aa = fields.Integer(related='company_id.ergani_branch_aa', readonly=False)
    ergani_late_reason_code = fields.Char(
        related='company_id.ergani_late_reason_code', readonly=False)
    ergani_manager_id = fields.Many2one(related='company_id.ergani_manager_id', readonly=False)
    ergani_late_reason_id = fields.Many2one(
        related='company_id.ergani_late_reason_id', readonly=False)
    ergani_night_shift = fields.Boolean(related='company_id.ergani_night_shift', readonly=False)

    def action_ergani_sync_reasons(self):
        self.execute()
        return self.env['ergani.delay.reason']._ergani_sync()
    ergani_tolerance_minutes = fields.Integer(
        related='company_id.ergani_tolerance_minutes', readonly=False)
    ergani_paused = fields.Boolean(related='company_id.ergani_paused')
    ergani_pause_reason = fields.Char(related='company_id.ergani_pause_reason')

    def action_ergani_test_connection(self):
        self.ensure_one()
        from .ergani_client import ErganiClient, ErganiError
        company = self.company_id
        if company.ergani_mode not in ('trial', 'production'):
            raise UserError(_('Η δοκιμή σύνδεσης γίνεται μόνο σε trial ή παραγωγικό.'))
        try:
            data = ErganiClient(company).test_connection()
        except ErganiError as e:
            raise UserError(_('Αποτυχία σύνδεσης με ΕΡΓΑΝΗ: %s', e)) from e
        # What this account can do — decides how far 2.x can go (PLAN_2.0 §6α).
        self.env['ergani.service']._ergani_refresh(company)
        in_sector = str(data.get('IsInCardSector')) == '1'
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {
                'type': 'success' if in_sector else 'warning',
                'sticky': not in_sector,
                'message': _('%(name)s — ΑΦΜ %(afm)s — %(sector)s',
                             name=data.get('Eponimia') or '?', afm=data.get('Afm') or '?',
                             sector=_('στην ψηφιακή κάρτα') if in_sector
                             else _('ΔΕΝ εμφανίζεται στην ψηφιακή κάρτα (IsInCardSector=0)')),
            },
        }

    def action_ergani_resume(self):
        self.company_id.write({'ergani_paused': False, 'ergani_pause_reason': False})
        self.env.ref('l10n_gr_ergani_card.ir_cron_ergani_send').sudo()._trigger()
