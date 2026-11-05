from odoo import _, fields, models
from odoo.exceptions import UserError


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    dias_org_code = fields.Char(related='company_id.dias_org_code', readonly=False)
    dias_env = fields.Selection(related='company_id.dias_env', readonly=False)
    dias_journal_id = fields.Many2one(related='company_id.dias_journal_id', readonly=False)
    dias_manager_id = fields.Many2one(related='company_id.dias_manager_id', readonly=False)
    dias_start = fields.Datetime(related='company_id.dias_start', readonly=False)
    dias_basic_user = fields.Char(related='company_id.dias_basic_user', readonly=False,
        groups='base.group_system')
    # Ποτέ αποθηκευμένος: το inverse τον κάνει αμέσως hash στην εταιρεία.
    dias_basic_password_new = fields.Char(
        'Νέος κωδικός Basic Auth', groups='base.group_system', store=False,
        compute='_compute_dias_basic_password_new', inverse='_inverse_dias_basic_password_new',
        help='Γράψτε τον μόνο για να τον αλλάξετε. Αποθηκεύεται ως hash και δεν εμφανίζεται ξανά.')
    dias_has_basic = fields.Boolean(compute='_compute_dias_has_basic')
    dias_allowed_ips = fields.Char(related='company_id.dias_allowed_ips', readonly=False,
        groups='base.group_system')
    dias_org_id = fields.Char(related='company_id.dias_org_id', readonly=False,
        groups='base.group_system')
    dias_ftp_password = fields.Char(related='company_id.dias_ftp_password', readonly=False,
        groups='base.group_system')
    dias_rest_url = fields.Char(related='company_id.dias_rest_url', readonly=False,
        groups='base.group_system')
    dias_pno_cycles = fields.Char(related='company_id.dias_pno_cycles', readonly=False)
    dias_pno_ext = fields.Selection(related='company_id.dias_pno_ext', readonly=False)
    dias_pno_lobid = fields.Char(related='company_id.dias_pno_lobid', readonly=False)
    dias_send_ilyda = fields.Boolean(related='company_id.dias_send_ilyda', readonly=False)
    dias_last_message_at = fields.Datetime(related='company_id.dias_last_message_at')
    dias_last_file_at = fields.Datetime(related='company_id.dias_last_file_at')
    dias_last_file_name = fields.Char(related='company_id.dias_last_file_name')
    dias_last_error = fields.Text(related='company_id.dias_last_error')

    def _compute_dias_has_basic(self):
        for rec in self:
            rec.dias_has_basic = bool(rec.company_id.sudo().dias_basic_hash)

    def _compute_dias_basic_password_new(self):
        for rec in self:
            rec.dias_basic_password_new = False

    def _inverse_dias_basic_password_new(self):
        for rec in self:
            if rec.dias_basic_password_new:
                if not self.env.user.has_group('base.group_system'):
                    raise UserError(_('Μόνο ο διαχειριστής αλλάζει τον κωδικό Basic Auth.'))
                rec.company_id._dias_set_basic_password(rec.dias_basic_password_new)

    def action_dias_fetch_now(self):
        self.env['dias.file']._fetch_company(self.company_id.sudo(), manual=True)
        return {'type': 'ir.actions.client', 'tag': 'reload'}
