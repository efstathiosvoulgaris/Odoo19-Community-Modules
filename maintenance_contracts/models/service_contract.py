from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

STATES = [
    ('active', 'Ενεργό'),
    ('expiring', 'Λήγει σύντομα'),
    ('expired', 'Ληγμένο'),
    ('renewed', 'Ανανεώθηκε'),
    ('not_renewed', 'Δεν ανανεώθηκε'),
]
# Decided by a person; the date-driven refresh never overrides these.
CLOSED_STATES = ('renewed', 'not_renewed')


def _one_year_end(start):
    """A yearly contract starting 01/11/2026 ends 31/10/2027."""
    return start + relativedelta(years=1, days=-1)


class ServiceContract(models.Model):
    _name = 'service.contract'
    _description = 'Συμβόλαιο Συντήρησης'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_end asc, id desc'

    name = fields.Char(string='Τίτλος', required=True, tracking=True)
    partner_id = fields.Many2one(
        'res.partner', string='Πελάτης', required=True, tracking=True, index=True)
    date_start = fields.Date(
        string='Έναρξη', required=True, tracking=True,
        default=fields.Date.context_today)
    date_end = fields.Date(
        string='Λήξη', required=True, tracking=True,
        default=lambda self: _one_year_end(fields.Date.context_today(self)))
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    amount = fields.Monetary(
        string='Ποσό', currency_field='currency_id', tracking=True,
        help='Η τιμή της γραμμής του προτιμολογίου. Με ΦΠΑ «συμπεριλαμβάνεται '
             'στην τιμή» είναι το τελικό ποσό.')
    user_id = fields.Many2one(
        'res.users', string='Υπεύθυνος', tracking=True,
        default=lambda self: self.env.user, domain="[('share', '=', False)]")
    notice_days = fields.Integer(
        string='Ειδοποίηση (ημέρες πριν)',
        default=lambda self: self.env.company.contract_notice_days)
    notes = fields.Html(string='Τι καλύπτει')
    state = fields.Selection(STATES, string='Κατάσταση', default='active',
                             required=True, tracking=True, index=True)
    reminder_sent = fields.Boolean(copy=False, readonly=True)
    previous_contract_id = fields.Many2one(
        'service.contract', string='Προηγούμενο', readonly=True, copy=False)
    next_contract_id = fields.Many2one(
        'service.contract', string='Επόμενο', readonly=True, copy=False)
    invoice_ids = fields.One2many(
        'account.move', 'service_contract_id', string='Τιμολόγια')
    invoice_count = fields.Integer(compute='_compute_invoice_count')

    _check_dates = models.Constraint(
        'CHECK (date_end >= date_start)',
        'Η λήξη δεν μπορεί να είναι πριν την έναρξη.')

    @api.depends('invoice_ids.state')
    def _compute_invoice_count(self):
        for contract in self:
            contract.invoice_count = len(
                contract.invoice_ids.filtered(lambda m: m.state != 'cancel'))

    @api.onchange('date_start')
    def _onchange_date_start(self):
        if self.date_start:
            self.date_end = _one_year_end(self.date_start)

    # ── State from the dates ─────────────────────────────────────────────────

    def _date_state(self, today):
        self.ensure_one()
        if self.date_end < today:
            return 'expired'
        if self.date_end - relativedelta(days=self.notice_days or 0) <= today:
            return 'expiring'
        return 'active'

    def _refresh_state(self):
        today = fields.Date.context_today(self)
        for contract in self.filtered(lambda c: c.state not in CLOSED_STATES):
            state = contract._date_state(today)
            if contract.state != state:
                contract.state = state

    @api.model_create_multi
    def create(self, vals_list):
        contracts = super().create(vals_list)
        contracts._refresh_state()
        return contracts

    def write(self, vals):
        if 'date_end' in vals or 'notice_days' in vals:
            # A new end date is a new reminder.
            vals = dict(vals, reminder_sent=False)
        res = super().write(vals)
        if {'date_end', 'notice_days', 'date_start'} & set(vals):
            self._refresh_state()
        return res

    # ── Reminder ─────────────────────────────────────────────────────────────

    @api.model
    def _cron_contract_reminders(self):
        """Daily: move contracts to «Λήγει σύντομα» / «Ληγμένο» and give the
        responsible one «Ανανέωση συμβολαίου» activity per contract."""
        contracts = self.search([('state', 'not in', CLOSED_STATES)])
        contracts._refresh_state()
        for contract in contracts.filtered(
                lambda c: c.state in ('expiring', 'expired') and not c.reminder_sent):
            note = (_('Το συμβόλαιο «%(name)s» του πελάτη %(partner)s έληξε '
                      'στις %(end)s.') if contract.state == 'expired' else
                    _('Το συμβόλαιο «%(name)s» του πελάτη %(partner)s λήγει '
                      'στις %(end)s.'))
            contract.activity_schedule(
                'mail.mail_activity_data_todo',
                date_deadline=contract.date_end,
                summary=_('Ανανέωση συμβολαίου'),
                note=note % {'name': contract.name,
                             'partner': contract.partner_id.display_name,
                             'end': contract.date_end.strftime('%d/%m/%Y')},
                user_id=(contract.user_id or self.env.user).id,
            )
            contract.reminder_sent = True

    def _close_reminders(self, feedback):
        self.activity_feedback(['mail.mail_activity_data_todo'], feedback=feedback)

    # ── Buttons ──────────────────────────────────────────────────────────────

    def action_renew(self):
        self.ensure_one()
        if self.next_contract_id:
            raise UserError(_('Το συμβόλαιο έχει ήδη ανανεωθεί.'))
        start = self.date_end + relativedelta(days=1)
        new = self.copy({
            'date_start': start,
            'date_end': _one_year_end(start),
            'previous_contract_id': self.id,
            'state': 'active',
        })
        self.write({'state': 'renewed', 'next_contract_id': new.id})
        self._close_reminders(_('Ανανεώθηκε: %s', new.display_name))
        return self._open(new)

    def action_not_renewed(self):
        self.write({'state': 'not_renewed'})
        self._close_reminders(_('Δεν ανανεώθηκε.'))

    def action_reopen(self):
        self.write({'state': 'active'})
        self._refresh_state()

    def action_create_invoice(self):
        """A DRAFT customer invoice for this contract period; the user
        confirms it — nothing is posted or transmitted from here."""
        self.ensure_one()
        company = self.company_id
        journal = company.contract_journal_id
        if not journal:
            raise UserError(_(
                'Ορίστε «Ημερολόγιο Προτιμολογίου» στις Ρυθμίσεις Συμβολαίων. '
                'Δεν επιλέγεται αυτόματα: σε λάθος ημερολόγιο το τιμολόγιο '
                'δεν θα διαβιβαζόταν σωστά.'))
        product = company._contract_product()
        if not product:
            raise UserError(_('Ορίστε «Είδος Συμβολαίου» στις Ρυθμίσεις Συμβολαίων.'))
        period = '%s – %s' % (self.date_start.strftime('%d/%m/%Y'),
                              self.date_end.strftime('%d/%m/%Y'))
        move = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner_id.id,
            'journal_id': journal.id,
            'invoice_payment_term_id': company.contract_payment_term_id.id,
            'invoice_origin': self.name,
            'service_contract_id': self.id,
            'invoice_line_ids': [(0, 0, {
                'product_id': product.id,
                'name': '%s, %s' % (self.name, period),
                'quantity': 1,
                'price_unit': self.amount,
            })],
        })
        self.message_post(body=_('Δημιουργήθηκε προτιμολόγιο (πρόχειρο).'))
        return self._open(move)

    def action_view_invoices(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'account.action_move_out_invoice_type')
        action['domain'] = [('service_contract_id', '=', self.id)]
        action['context'] = {'default_move_type': 'out_invoice', 'create': False}
        return action

    @staticmethod
    def _open(record):
        return {
            'type': 'ir.actions.act_window',
            'res_model': record._name,
            'res_id': record.id,
            'view_mode': 'form',
            'target': 'current',
        }
