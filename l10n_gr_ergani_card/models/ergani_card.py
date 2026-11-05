import hashlib
import json
from zoneinfo import ZoneInfo

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .res_company import ERGANI_MODES

ATHENS = ZoneInfo('Europe/Athens')
STATES = [
    ('simulated', 'Προσομοίωση'),
    ('pending', 'Σε αναμονή'),
    ('sending', 'Αποστέλλεται'),
    ('sent', 'Στάλθηκε'),
    ('error', 'Σφάλμα'),
    ('unknown', 'Άγνωστη έκβαση'),
]
# What a punch IS — written once at creation, never again (DESIGN §3, §5.6).
IMMUTABLE = {'employee_id', 'user_id', 'company_id', 'card_type', 'event_datetime',
             'reference_date', 'branch_aa', 'environment', 'in_card_id',
             'employer_afm', 'worker_afm', 'worker_last_name', 'worker_first_name',
             'prev_hash', 'row_hash'}


class ErganiCard(models.Model):
    _name = 'ergani.card'
    _description = 'Κάρτα Εργασίας ΕΡΓΑΝΗ'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'event_datetime desc, id desc'
    _rec_name = 'display_label'
    _mail_post_access = 'read'  # notes stay possible although nobody may write cards
    # One check-out per check-in, whatever the timing of two requests.
    _one_out_per_in = models.UniqueIndex('(in_card_id) WHERE in_card_id IS NOT NULL')

    employee_id = fields.Many2one('hr.employee', string='Εργαζόμενος', required=True,
                                  readonly=True, index=True)
    user_id = fields.Many2one('res.users', string='Χρήστης', readonly=True)
    company_id = fields.Many2one('res.company', required=True, readonly=True, index=True)
    card_type = fields.Selection([('0', 'Προσέλευση'), ('1', 'Αποχώρηση')], string='Κίνηση',
                                 required=True, readonly=True)
    event_datetime = fields.Datetime(string='Ώρα χτυπήματος', required=True, readonly=True,
                                     index=True)
    reference_date = fields.Date(string='Ημ/νία αναφοράς', required=True, readonly=True)
    branch_aa = fields.Integer(string='Α/Α Παραρτήματος', readonly=True)
    # Who the card declares, frozen at the punch: a later edit of the employee
    # must not turn it into someone else's card (DESIGN §3).
    employer_afm = fields.Char(string='ΑΦΜ εργοδότη', readonly=True)
    worker_afm = fields.Char(string='ΑΦΜ εργαζομένου', readonly=True)
    worker_last_name = fields.Char(string='Επώνυμο', readonly=True)
    worker_first_name = fields.Char(string='Όνομα', readonly=True)
    environment = fields.Selection([m for m in ERGANI_MODES if m[0] != 'off'],
                                   string='Περιβάλλον', required=True, readonly=True)
    state = fields.Selection(STATES, string='Κατάσταση', required=True, readonly=True,
                             tracking=True, index=True)
    late = fields.Boolean(string='Εκπρόθεσμη', readonly=True)
    aitiologia = fields.Char(string='Αιτιολογία εκπρόθεσμου', readonly=True)
    in_card_id = fields.Many2one('ergani.card', string='Προσέλευση', readonly=True,
                                 index='btree_not_null')
    out_card_ids = fields.One2many('ergani.card', 'in_card_id', string='Αποχώρηση')
    ergani_id = fields.Char(string='ID ΕΡΓΑΝΗ', readonly=True)
    protocol = fields.Char(string='Πρωτόκολλο', readonly=True, tracking=True)
    submit_date_raw = fields.Char(string='Ημ/νία υποβολής (ΕΡΓΑΝΗ)', readonly=True)
    payload = fields.Text(readonly=True)
    response = fields.Text(readonly=True)
    attempts = fields.Integer(string='Προσπάθειες', readonly=True)
    last_error = fields.Text(string='Τελευταίο σφάλμα', readonly=True)
    technical_failure = fields.Boolean(readonly=True,
                                       help='Καταγεγραμμένη αποτυχία σύνδεσης/διακομιστή.')
    resolved_by_id = fields.Many2one('res.users', string='Επιλύθηκε από', readonly=True)
    forgotten_notified = fields.Boolean(readonly=True)
    client_ip = fields.Char(string='IP', readonly=True)
    user_agent = fields.Char(string='Συσκευή', readonly=True)
    session_hash = fields.Char(readonly=True)
    pseudonymised = fields.Boolean(readonly=True)
    prev_hash = fields.Char(readonly=True)
    row_hash = fields.Char(readonly=True)
    display_label = fields.Char(compute='_compute_display_label')

    @api.depends('employee_id', 'card_type', 'event_datetime')
    def _compute_display_label(self):
        for card in self:
            card.display_label = '%s · %s · %s' % (
                card.employee_id.name or '', dict(self._fields['card_type'].selection).get(
                    card.card_type, ''), card._ergani_local_label())

    # ── Creation: only from the gate (DESIGN §3) ─────────────────────────────

    @api.model
    def _ergani_create_punch(self, employee, card_type, request_meta):
        """The ONLY way a card comes to exist: the gate calls it, with sudo,
        for request.env.user's own employee after his PIN was verified."""
        company = employee.company_id
        mode = company.ergani_mode
        if mode == 'off':
            raise UserError(_('Η κάρτα ΕΡΓΑΝΗ είναι ανενεργή.'))
        now = fields.Datetime.now()
        in_card = self.browse()
        if card_type == '1':
            in_card = employee._ergani_open_in_card()
            if not in_card:
                raise UserError(_('Δεν υπάρχει ανοιχτή προσέλευση.'))
            reference_date = in_card.reference_date
        else:
            reference_date = fields.Datetime.context_timestamp(
                self.with_context(tz='Europe/Athens'), now).date()
        # Under REPEATABLE READ a lock taken now cannot show rows committed after
        # the request's snapshot. Updating the employee row instead makes a
        # concurrent punch for him fail to serialise, and Odoo retries it — it
        # then sees this card. The hash chain is therefore per employee.
        self.env.cr.execute('UPDATE hr_employee SET write_date = write_date WHERE id = %s',
                            [employee.id])
        prev = self.sudo().search([('employee_id', '=', employee.id)],
                                  order='id desc', limit=1)
        emp = employee.sudo()
        vals = {
            'employee_id': employee.id,
            'user_id': self.env.user.id,
            'company_id': company.id,
            'card_type': card_type,
            'event_datetime': now,
            'reference_date': reference_date,
            'branch_aa': (emp.ergani_branch_id.aa if emp.ergani_branch_id
                          else company.ergani_branch_aa),
            'environment': mode,
            'employer_afm': company._ergani_vat(),
            'worker_afm': emp.ergani_afm,
            'worker_last_name': emp.ergani_last_name,
            'worker_first_name': emp.ergani_first_name,
            'state': 'simulated' if mode == 'simulation' else 'pending',
            'in_card_id': in_card.id,
            'client_ip': (request_meta or {}).get('ip'),
            'user_agent': ((request_meta or {}).get('user_agent') or '')[:250],
            'session_hash': (request_meta or {}).get('session_hash'),
            'prev_hash': prev.row_hash or '',
        }
        vals['row_hash'] = self._ergani_hash(vals)
        card = self.sudo().with_context(ergani_gate_create=True).create(vals)
        card.payload = json.dumps(card._ergani_payload(), ensure_ascii=False)
        return card

    @staticmethod
    def _ergani_hash(vals):
        canonical = '|'.join(str(vals.get(k) or '') for k in (
            'prev_hash', 'employee_id', 'user_id', 'card_type', 'event_datetime',
            'reference_date', 'branch_aa', 'environment', 'in_card_id', 'client_ip',
            'employer_afm', 'worker_afm', 'worker_last_name', 'worker_first_name'))
        return hashlib.sha256(canonical.encode()).hexdigest()

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.context.get('ergani_gate_create'):
            raise UserError(_('Οι κάρτες ΕΡΓΑΝΗ δημιουργούνται μόνο από τον ίδιο τον '
                              'εργαζόμενο, στη σελίδα χτυπήματος.'))
        return super().create(vals_list)

    def write(self, vals):
        if IMMUTABLE & set(vals):
            raise UserError(_('Τα στοιχεία της κίνησης δεν αλλάζουν μετά το χτύπημα.'))
        return super().write(vals)

    def unlink(self):
        raise UserError(_('Οι κάρτες ΕΡΓΑΝΗ δεν διαγράφονται.'))

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _ergani_local_dt(self):
        self.ensure_one()
        return self.event_datetime.replace(tzinfo=ZoneInfo('UTC')).astimezone(ATHENS)

    def _ergani_local_label(self):
        self.ensure_one()
        return self._ergani_local_dt().strftime('%d/%m/%Y %H:%M') if self.event_datetime else ''

    def _ergani_payload(self):
        """WRKCardSE body (guide γρ. 722), one CardDetail."""
        self.ensure_one()
        # Cards punched before the details were frozen fall back to the employee.
        emp = self.employee_id.sudo()
        return {'Cards': {'Card': [{
            'f_afm_ergodoti': self.employer_afm or self.company_id._ergani_vat(),
            'f_aa': str(self.branch_aa or 0),
            'f_comments': '',
            'Details': {'CardDetails': [{
                'f_afm': self.worker_afm or emp.ergani_afm or '',
                'f_eponymo': self.worker_last_name or emp.ergani_last_name or '',
                'f_onoma': self.worker_first_name or emp.ergani_first_name or '',
                'f_type': self.card_type,
                'f_reference_date': self.reference_date.strftime('%Y-%m-%d'),
                'f_date': self._ergani_local_dt().isoformat(timespec='seconds'),
                # Card_v1.xsd: non-nillable, digits or blank; Card.json sends "".
                'f_aitiologia': self.aitiologia or '',
            }]},
        }]}}

    def _ergani_notify(self, summary, note):
        """Activity + email to the ΕΡΓΑΝΗ manager (DESIGN §5.8)."""
        for card in self:
            manager = card.company_id.ergani_manager_id
            if not manager:
                continue
            card.sudo().activity_schedule('mail.mail_activity_data_todo', user_id=manager.id,
                                          summary=summary, note=note)
            card.sudo().message_post(body=note, partner_ids=manager.partner_id.ids,
                                     subtype_xmlid='mail.mt_comment')

    def action_view_payload(self):
        self.ensure_one()
        raise UserError(json.dumps(self._ergani_payload(), ensure_ascii=False, indent=2))
