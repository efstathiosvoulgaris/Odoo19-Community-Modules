from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .res_company import ERGANI_MODES

# Bodies kept on failures are personal data: cleared after this, the row stays
# (PLAN_1.3 §2.4, same horizon as IP/user-agent on cards).
CLEAR_BODIES_AFTER_DAYS = 730


class ErganiSubmission(models.Model):
    """One row per HTTP call to ΕΡΓΑΝΗ, written by ErganiClient in its own
    transaction. Append-only; nobody creates or edits rows by hand."""
    _name = 'ergani.submission'
    _description = 'ΕΡΓΑΝΗ: αρχείο υποβολών'
    _order = 'id desc'

    date = fields.Datetime(string='Ώρα', default=fields.Datetime.now, required=True,
                           readonly=True, index=True)
    company_id = fields.Many2one('res.company', required=True, readonly=True, index=True)
    environment = fields.Selection(ERGANI_MODES, string='Περιβάλλον', readonly=True)
    kind = fields.Selection([
        ('card', 'Κάρτα εργασίας'),
        ('wto', 'Δήλωση ωραρίου / άδειας'),
        ('receipt', 'Αποδεικτικό'),
        ('service', 'Υπηρεσία'),
        ('login', 'Σύνδεση'),
        ('refresh', 'Ανανέωση token'),
    ], string='Είδος', required=True, readonly=True)
    method = fields.Char(string='Μέθοδος', readonly=True)
    endpoint = fields.Char(string='Endpoint', readonly=True)
    http_status = fields.Integer(string='HTTP', readonly=True)
    outcome = fields.Selection([
        ('ok', 'Εντάξει'),
        ('not_sent', 'Δεν στάλθηκε'),
        ('unknown', 'Άγνωστη έκβαση'),
        ('rejected', 'Απόρριψη'),
        ('auth', 'Μη εξουσιοδότηση'),
        ('throttled', 'Πολλά αιτήματα'),
        ('error', 'Σφάλμα'),
    ], string='Έκβαση', required=True, readonly=True, index=True)
    duration_ms = fields.Integer(string='Διάρκεια (ms)', readonly=True)
    card_id = fields.Many2one('ergani.card', string='Κάρτα', readonly=True, index='btree_not_null')
    wto_id = fields.Many2one('ergani.wto', string='Δήλωση ωραρίου', readonly=True,
                             index='btree_not_null')
    card_hash = fields.Char(string='Hash κάρτας', readonly=True,
                            help='Το row_hash της κάρτας τη στιγμή της κλήσης.')
    message = fields.Char(string='Μήνυμα', readonly=True)
    request_body = fields.Text(string='Αίτημα', readonly=True)
    response_body = fields.Text(string='Απάντηση', readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su:
            raise UserError(_('Το αρχείο υποβολών γράφεται μόνο από την επικοινωνία με το ΕΡΓΑΝΗ.'))
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.context.get('ergani_clear_bodies') or set(vals) - {
                'request_body', 'response_body'}:
            raise UserError(_('Το αρχείο υποβολών δεν αλλάζει.'))
        return super().write(vals)

    def unlink(self):
        raise UserError(_('Το αρχείο υποβολών δεν διαγράφεται.'))

    @api.model
    def _ergani_clear_old_bodies(self):
        old = self.sudo().search([
            ('date', '<', fields.Datetime.now() - timedelta(days=CLEAR_BODIES_AFTER_DAYS)),
            '|', ('request_body', '!=', False), ('response_body', '!=', False)])
        old.with_context(ergani_clear_bodies=True).write(
            {'request_body': False, 'response_body': False})
