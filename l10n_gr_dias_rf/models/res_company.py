from passlib.context import CryptContext

from odoo import _, fields, models

_crypt = CryptContext(['pbkdf2_sha512'])
SECRET = 'base.group_system'


class ResCompany(models.Model):
    _inherit = 'res.company'

    dias_org_code = fields.Char('Κωδικός Οργανισμού ΔΙΑΣ (9nnnn)')
    dias_env = fields.Selection([('T', 'Δοκιμές (T)'), ('P', 'Παραγωγή (P)')],
                                'Περιβάλλον ΔΙΑΣ', default='T')
    dias_journal_id = fields.Many2one(
        'account.journal', 'Ημερολόγιο τράπεζας ΔΙΑΣ',
        domain="[('type', '=', 'bank'), ('company_id', '=', id)]")
    dias_manager_id = fields.Many2one(
        'res.users', 'Υπεύθυνος πληρωμών ΔΙΑΣ',
        help='Παίρνει δραστηριότητα για κάθε πληρωμή που θέλει χειρισμό.')
    dias_start = fields.Datetime(
        'Έναρξη ΔΙΑΣ σε αυτή τη βάση',
        help='Πληρωμές παλαιότερες από αυτή τη στιγμή ανήκουν στο προηγούμενο σύστημα και '
             'αγνοούνται (καταγράφονται, δεν καταχωρούνται).')
    # Υποδοχή /dias/online: ο κωδικός Basic Auth κρατιέται μόνο ως hash.
    dias_basic_user = fields.Char('Basic Auth – χρήστης', groups=SECRET)
    dias_basic_hash = fields.Char(groups=SECRET, copy=False)
    dias_allowed_ips = fields.Char(
        'Επιτρεπόμενες IP', groups=SECRET,
        help='Χωρισμένες με κόμμα (ΔΙΑΣ: 194.30.224.10). Κενό = η υποδοχή απορρίπτει τα πάντα.')
    # Λήψη αρχείων PNO (File Transfer REST, HTTPS)
    dias_org_id = fields.Char('OrgID ΔΙΑΣ', groups=SECRET)
    dias_ftp_password = fields.Char('Κωδικός File Transfer', groups=SECRET, copy=False)
    dias_rest_url = fields.Char('URL λήψης (REST)', groups=SECRET,
                                default='https://apps.dias.com.gr/dias-fti/rest/file/download')
    dias_pno_cycles = fields.Char('Κύκλοι παραλαβής', default='01,02,07',
                                  help='Παράμετρος 9: 1=10:45, 2=13:00, 3=14:20, 4=16:15, '
                                       '5=17:45, 6=18:15, 7=19:15.')
    dias_pno_ext = fields.Selection([('xml', 'xml (.XOO)'), ('csv', 'csv'), ('xlsx', 'xlsx')],
                                    'Τύπος αρχείου πληρωμών', default='xml')
    dias_pno_lobid = fields.Char('LobID στο όνομα αρχείου')
    dias_send_ilyda = fields.Boolean(
        'Κωδικός RF στο ηλεκτρονικό τιμολόγιο (ΙΛΥΔΑ)',
        help='Στέλνει το RF στο paymentInstruction.remittanceInfo. ΑΝΕΠΙΒΕΒΑΙΩΤΟ στην ΙΛΥΔΑ· '
             'ενεργοποιήστε αφού δοκιμαστεί.')
    dias_last_message_at = fields.Datetime('Τελευταίο μήνυμα ΔΙΑΣ', readonly=True)
    dias_last_file_at = fields.Datetime('Τελευταίο αρχείο ΔΙΑΣ', readonly=True)
    dias_last_file_name = fields.Char('Όνομα τελευταίου αρχείου', readonly=True)
    dias_last_error = fields.Text('Τελευταίο σφάλμα λήψης', readonly=True)

    def _dias_set_basic_password(self, password):
        self.ensure_one()
        self.sudo().dias_basic_hash = _crypt.hash(password) if password else False

    def _dias_check_basic(self, user, password):
        self.ensure_one()
        me = self.sudo()
        if not (me.dias_basic_user and me.dias_basic_hash and user and password):
            return False
        try:
            return user == me.dias_basic_user and _crypt.verify(password, me.dias_basic_hash)
        except (ValueError, TypeError):
            return False

    def _dias_ready_problems(self):
        """Τι λείπει για να καταχωρούνται πληρωμές (κενή λίστα = έτοιμο)."""
        self.ensure_one()
        me = self.sudo()
        issues = []
        if not me.dias_org_code:
            issues.append(_('Κωδικός Οργανισμού'))
        journal = me.dias_journal_id
        if not journal:
            issues.append(_('Ημερολόγιο τράπεζας'))
        else:
            line = journal.inbound_payment_method_line_ids[:1]
            if not line:
                issues.append(_('Μέθοδος εισερχόμενης πληρωμής στο ημερολόγιο'))
        if not me.dias_manager_id:
            # Χωρίς υπεύθυνο, ό,τι θέλει χειρισμό θα έμενε αθέατο.
            issues.append(_('Υπεύθυνος πληρωμών ΔΙΑΣ'))
        return issues

    def _dias_notify_manager(self, summary, note):
        """Δραστηριότητα στον υπεύθυνο, πάνω στην επαφή της εταιρείας (για ό,τι δεν αφορά μία πληρωμή)."""
        self.ensure_one()
        user = self.sudo().dias_manager_id
        if user:
            self.sudo().partner_id.activity_schedule(
                'mail.mail_activity_data_todo', user_id=user.id, summary=summary, note=note)
        else:
            self.sudo().partner_id.message_post(body='%s: %s' % (summary, note))
