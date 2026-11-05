import logging
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from psycopg2 import errors as pg_errors

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..lib import rf

_logger = logging.getLogger(__name__)
MANAGER = 'account.group_account_manager'
STALE_VALIDATED_DAYS = 2
ATHENS = ZoneInfo('Europe/Athens')
AMOUNT_TOLERANCE = 0.005

STATES = [
    ('validated', 'Εγκρίθηκε κωδικός (αναμονή πληρωμής)'),
    ('rejected', 'Απορρίφθηκε κωδικός'),
    ('new', 'Προς καταχώρηση'),
    ('matched', 'Συμψηφίστηκε'),
    ('credit', 'Πίστωση πελάτη'),
    ('unmatched', 'Χωρίς αντιστοίχιση'),
    ('v13', 'Κωδικός v13'),
    ('ignored', 'Αγνοήθηκε'),
    ('error', 'Σφάλμα'),
]
# Καταστάσεις όπου τα χρήματα ήρθαν αλλά κανείς δεν τα κατένειμε ακόμα.
NEEDS_HUMAN = ('unmatched', 'v13', 'error')


class DiasPayment(models.Model):
    _name = 'dias.payment'
    _description = 'ΔΙΑΣ: εισερχόμενη πληρωμή'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char('RID', required=True, index=True, readonly=True)
    company_id = fields.Many2one('res.company', required=True, readonly=True, index=True)
    ri_mid = fields.Char('Κωδικός πληρωμής (RF)', index=True, readonly=True)
    amount = fields.Monetary('Ποσό', readonly=True, currency_field='currency_id')
    currency_id = fields.Many2one(related='company_id.currency_id')
    bk_date = fields.Date('Ημ/νία πίστωσης', readonly=True)
    payment_dt = fields.Char('Ημ/νία & ώρα πληρωμής', readonly=True)
    debtor_name = fields.Char('Πληρωτής', readonly=True)
    debtor_bic = fields.Char('Τράπεζα πληρωτή', readonly=True)
    transaction_id = fields.Char('TransactionID', readonly=True, index=True)
    remittance = fields.Char('Αιτιολογία', readonly=True)
    source = fields.Selection([('request', 'Online: έλεγχος κωδικού'), ('online', 'Online'),
                               ('file', 'Αρχείο PNO')], readonly=True)
    state = fields.Selection(STATES, default='new', required=True, index=True, tracking=True)
    kind = fields.Selection([('invoice', 'Τιμολόγιο'), ('order', 'Παραγγελία'),
                             ('partner', 'Πάγιος πελάτη'), ('v13', 'Κωδικός v13')],
                            'Είδος κωδικού', readonly=True)
    partner_id = fields.Many2one('res.partner', 'Πελάτης', tracking=True,
                                 help='Για «Χωρίς αντιστοίχιση» / «Κωδικός v13»: ορίστε τον πελάτη '
                                      'και πατήστε «Καταχώρηση ως πίστωση».')
    move_id = fields.Many2one('account.move', 'Τιμολόγιο κωδικού', readonly=True)
    order_id = fields.Many2one('sale.order', 'Παραγγελία', readonly=True)
    payment_id = fields.Many2one('account.payment', 'Πληρωμή Odoo', readonly=True)
    message = fields.Text('Σχόλιο', readonly=True)
    raw = fields.Text('Αρχικά δεδομένα', readonly=True, groups=MANAGER)
    validated_at = fields.Datetime('Έλεγχος κωδικού', readonly=True)
    stale_alerted = fields.Boolean(readonly=True)

    _rid_company_uniq = models.Constraint('unique(name, company_id)', 'Το RID υπάρχει ήδη.')

    # ── Αξιολόγηση κωδικού ───────────────────────────────────────────────────

    @api.model
    def _dias_evaluate(self, company, code, amount):
        """Τι είναι ο κωδικός. dict με: error (κείμενο ή None), v13, kind, partner, move,
        order, amount_ok, paid. Δεν γράφει τίποτα."""
        res = {'error': None, 'v13': False, 'kind': False, 'partner': self.env['res.partner'],
               'move': self.env['account.move'], 'order': self.env['sale.order'],
               'amount_ok': True, 'paid': False}
        info = rf.parse_rf(code)
        if not info:
            res['error'] = _('Μη έγκυρος κωδικός πληρωμής: %s', code or '')
            return res
        if info['org'] != (company.sudo().dias_org_code or ''):
            res['error'] = _('Ο κωδικός ανήκει σε άλλο οργανισμό (%s).', info['org'])
            return res
        if info['kind'] == rf.KIND_V13:
            res.update(v13=True, kind='v13')
            return res
        res['amount_ok'] = rf.check_amount(info, amount)
        Partner = self.env['res.partner'].sudo().with_context(active_test=False)
        partner = Partner.browse(info['partner_id']).exists()
        if info['kind'] == rf.KIND_INVOICE:
            res['kind'] = 'invoice'
            entry = self.env['dias.rf.code'].sudo().search(
                [('code', '=', info['code']), ('company_id', '=', company.id)], limit=1)
            move = entry.move_id
            if not move:
                res['error'] = _('Άγνωστος κωδικός τιμολογίου.')
            elif move.state != 'posted':
                res['error'] = _('Το τιμολόγιο %s δεν είναι επικυρωμένο.', move.name or move.id)
            else:
                res.update(move=move, partner=move.commercial_partner_id,
                           paid=move.amount_residual <= 0 or move.payment_state in ('paid', 'reversed'))
        elif info['kind'] == rf.KIND_ORDER:
            res['kind'] = 'order'
            order = self.env['sale.order'].sudo().browse(info['doc_id']).exists()
            if not order or order.company_id != company or (order.name or '').startswith('IST/'):
                res['error'] = _('Άγνωστη παραγγελία.')
            elif order.state == 'cancel':
                res['error'] = _('Η παραγγελία %s είναι ακυρωμένη.', order.name)
            elif order.partner_id.commercial_partner_id != partner:
                res['error'] = _('Ο κωδικός δεν ανήκει στον πελάτη της παραγγελίας %s.', order.name)
            else:
                res.update(order=order, partner=partner)
        else:
            res['kind'] = 'partner'
            if not partner or partner._dias_rf_partner_code() != info['code']:
                res['error'] = _('Άγνωστος πελάτης.')
            else:
                res['partner'] = partner.commercial_partner_id
        if not res['error'] and not res['amount_ok']:
            res['error'] = _('Το ποσό %s δεν συμφωνεί με τον κωδικό.', amount)
        return res

    @api.model
    def _dias_request_verdict(self, company, code, amount):
        """DPG_ONRequest (πριν την πληρωμή): (accepted, μήνυμα). Απόφαση χρήστη 2026-10-22:
        τιμολόγιο ήδη εξοφλημένο → απόρριψη. Κωδικός v13 → αποδοχή, για χειρισμό από άνθρωπο."""
        ev = self._dias_evaluate(company, code, amount)
        if ev['v13']:
            return True, _('Κωδικός v13: γίνεται δεκτός, κατανέμεται με το χέρι.')
        if ev['error']:
            return False, ev['error']
        if ev['paid']:
            return False, _('Το τιμολόγιο %s είναι ήδη εξοφλημένο.', ev['move'].name)
        return True, False

    # ── Καταχώριση εγγραφής (online / αρχείο) ────────────────────────────────

    @api.model
    def _dias_register(self, company, vals, confirmed, _retried=False):
        """Νέα εγγραφή ή η υπάρχουσα με το ίδιο RID. confirmed = τα χρήματα κινήθηκαν
        (DPG_ON ή αρχείο). Επιστρέφει την εγγραφή που πρέπει να επεξεργαστεί, ή κενό."""
        Payment = self.sudo()
        existing = Payment.search([('name', '=', vals['name']), ('company_id', '=', company.id)],
                                  limit=1)
        if existing:
            updates = {}
            if vals.get('bk_date') and not existing.bk_date:
                updates['bk_date'] = vals['bk_date']
            if confirmed and existing.state in ('validated', 'rejected'):
                # Η ΔΙΑΣ επιβεβαιώνει ότι η πληρωμή έγινε: από εδώ και πέρα μετράει ως χρήματα,
                # και μετράει το ποσό της επιβεβαίωσης, όχι της ερώτησης.
                paid = vals.get('amount') or 0.0
                updates.update(source=vals.get('source') or existing.source,
                               transaction_id=vals.get('transaction_id') or existing.transaction_id,
                               ri_mid=vals.get('ri_mid') or existing.ri_mid,
                               payment_dt=vals.get('payment_dt') or existing.payment_dt)
                if abs(paid - existing.amount) > AMOUNT_TOLERANCE:
                    updates.update(state='unmatched', amount=paid, message=_(
                        'Το ποσό της πληρωμής (%(paid)s) διαφέρει από το ποσό του ελέγχου κωδικού '
                        '(%(asked)s). Ελέγξτε πριν καταχωρήσετε.', paid=paid, asked=existing.amount))
                else:
                    updates.update(state='new', amount=paid)
            if updates:
                existing.write(updates)
                if updates.get('state') == 'unmatched':
                    existing._dias_alert(_('ΔΙΑΣ: διαφορά ποσού'), existing.message)
            return existing if existing.state == 'new' else Payment
        vals = dict(vals, company_id=company.id)
        if confirmed:
            vals['state'] = 'new'
            if self._dias_before_start(company, vals):
                vals.update(state='ignored', message=_(
                    'Πριν την έναρξη ΔΙΑΣ σε αυτή τη βάση (%s): ανήκει στο προηγούμενο σύστημα.',
                    company.sudo().dias_start))
            elif vals.get('transaction_id') and Payment.search_count([
                    ('company_id', '=', company.id), ('transaction_id', '=', vals['transaction_id']),
                    ('amount', '=', vals.get('amount')), ('state', 'not in', ('validated', 'rejected'))]):
                vals.update(state='unmatched', message=_(
                    'Ίδιο TransactionID και ποσό με άλλη εγγραφή, με διαφορετικό RID: πιθανή '
                    'διπλή ειδοποίηση. Ελέγξτε πριν καταχωρήσετε.'))
        try:
            with self.env.cr.savepoint():
                rec = Payment.create(vals)
        except pg_errors.UniqueViolation:
            # Η ίδια πληρωμή έφτασε ταυτόχρονα από άλλο κανάλι. Μία μόνο επανάληψη: αν η άλλη
            # εγγραφή δεν φαίνεται ακόμα (REPEATABLE READ), το σφάλμα ανεβαίνει και το Odoo
            # ξανατρέχει όλο το αίτημα με νέο στιγμιότυπο.
            if _retried:
                raise
            return Payment._dias_register(company, vals, confirmed, _retried=True)
        if rec.state == 'unmatched':
            rec._dias_alert(_('ΔΙΑΣ: πιθανή διπλή πληρωμή'), rec.message)
        return rec if rec.state == 'new' else Payment

    @api.model
    def _dias_register_request(self, company, vals, accepted, reason):
        """DPG_ONRequest: καταγραφή του ελέγχου, χωρίς καμία λογιστική κίνηση (τα χρήματα δεν
        έχουν κινηθεί ακόμα). Αν το RID υπάρχει ήδη, δεν αλλάζει τίποτα."""
        Payment = self.sudo()
        if Payment.search_count([('name', '=', vals['name']), ('company_id', '=', company.id)]):
            return
        vals = dict(vals, company_id=company.id, source='request',
                    state='validated' if accepted else 'rejected',
                    validated_at=fields.Datetime.now(), message=reason or False)
        try:
            with self.env.cr.savepoint():
                Payment.create(vals)
        except pg_errors.UniqueViolation:
            pass  # η ίδια ερώτηση ήρθε δύο φορές ταυτόχρονα

    @api.model
    def _dias_before_start(self, company, vals):
        """Ανήκει η πληρωμή στο προηγούμενο σύστημα; Η ώρα πληρωμής (ώρα Ελλάδας) συγκρίνεται με
        την «Έναρξη ΔΙΑΣ»· χωρίς ώρα, η ημερομηνία πίστωσης ως και την ημέρα της έναρξης."""
        start = company.sudo().dias_start
        if not start:
            return False
        stamp = (vals.get('payment_dt') or '').strip()
        try:
            local = datetime.fromisoformat(stamp[:19])
        except ValueError:
            local = None
        if local:
            when = local.replace(tzinfo=ATHENS).astimezone(ZoneInfo('UTC')).replace(tzinfo=None)
            return when < start
        day = vals.get('bk_date')
        start_day = start.replace(tzinfo=ZoneInfo('UTC')).astimezone(ATHENS).date()
        return bool(day) and str(day) <= start_day.isoformat()

    @staticmethod
    def _dias_day(payment_dt):
        m = re.match(r'^(\d{4}-\d{2}-\d{2})', (payment_dt or '').strip())
        return m.group(1) if m else False

    # ── Επεξεργασία: πληρωμή Odoo + συμψηφισμός ──────────────────────────────

    def _dias_process(self):
        for rec in self:
            try:
                with self.env.cr.savepoint(flush=False):
                    self.env.cr.execute(
                        'SELECT state FROM dias_payment WHERE id = %s FOR UPDATE NOWAIT', [rec.id])
            except pg_errors.LockNotAvailable:
                continue  # την επεξεργάζεται ήδη άλλη διεργασία
            rec.invalidate_recordset(['state'])
            if rec.state != 'new':
                continue
            try:
                with self.env.cr.savepoint():
                    rec._dias_do_process()
            except Exception as e:  # noqa: BLE001 — κάθε αποτυχία γίνεται «Σφάλμα» με ειδοποίηση
                _logger.exception('ΔΙΑΣ: αποτυχία επεξεργασίας RID %s', rec.name)
                rec.write({'state': 'error', 'message': str(e)})
                rec._dias_alert(_('ΔΙΑΣ: σφάλμα πληρωμής'), str(e))

    def _dias_do_process(self):
        self.ensure_one()
        company = self.company_id
        problems = company._dias_ready_problems()
        if problems:
            raise UserError(_('Λείπουν ρυθμίσεις ΔΙΑΣ: %s', ', '.join(problems)))
        if self.amount <= 0:
            raise UserError(_('Μη έγκυρο ποσό.'))
        ev = self._dias_evaluate(company, self.ri_mid, self.amount)
        if ev['v13']:
            self.write({'state': 'v13', 'kind': 'v13', 'message': _(
                'Κωδικός του παλιού συστήματος (v13). Βρείτε τον πελάτη, ορίστε τον στο πεδίο '
                '«Πελάτης» και πατήστε «Καταχώρηση ως πίστωση».')})
            self._dias_alert(_('ΔΙΑΣ: πληρωμή με κωδικό v13'), self.message)
            return
        if ev['error']:
            self.write({'state': 'unmatched', 'kind': ev['kind'] or False,
                        'partner_id': ev['partner'].id or False, 'message': ev['error']})
            self._dias_alert(_('ΔΙΑΣ: πληρωμή χωρίς αντιστοίχιση'), ev['error'])
            return
        partner, move, order = ev['partner'], ev['move'], ev['order']
        Move = self.env['account.move'].sudo()
        if ev['kind'] == 'invoice':
            invoices = move.filtered(lambda m: m.amount_residual > 0)
        elif ev['kind'] == 'order':
            invoices = order.invoice_ids.filtered(
                lambda m: m.move_type == 'out_invoice' and m.state == 'posted' and m.amount_residual > 0)
        else:
            invoices = Move.search([
                ('commercial_partner_id', '=', partner.id), ('move_type', '=', 'out_invoice'),
                ('state', '=', 'posted'), ('amount_residual', '>', 0),
                ('company_id', '=', company.id)], order='invoice_date_due asc, id asc')
        payment = self._dias_book(partner)
        done = self._dias_allocate(payment, invoices)
        if done:
            msg = _('Συμψηφίστηκε σε: %s', ', '.join(done))
        elif ev['kind'] == 'invoice' and ev['paid']:
            msg = _('Το τιμολόγιο %s ήταν ήδη εξοφλημένο· η πληρωμή έμεινε πίστωση πελάτη.', move.name)
        else:
            msg = _('Δεν βρέθηκε ανοιχτό τιμολόγιο· η πληρωμή έμεινε πίστωση πελάτη.')
        left = self._dias_open_amount(payment)
        if done and not company.currency_id.is_zero(left):
            msg += _(' Υπόλοιπο πίστωσης: %s', left)
        self.write({'state': 'matched' if done else 'credit', 'kind': ev['kind'],
                    'partner_id': partner.id, 'move_id': move.id or False,
                    'order_id': order.id or False, 'payment_id': payment.id, 'message': msg})
        if ev['kind'] == 'invoice' and ev['paid']:
            self._dias_alert(_('ΔΙΑΣ: πληρωμή εξοφλημένου τιμολογίου'), msg)
        if order:
            order.sudo().message_post(body=_('Πληρωμή ΔΙΑΣ %(amount)s (RID %(rid)s). %(msg)s',
                                             amount=self.amount, rid=self.name, msg=msg))

    def _dias_book(self, partner):
        """Εισερχόμενη πληρωμή στο ημερολόγιο ΔΙΑΣ, επικυρωμένη."""
        company = self.company_id
        journal = company.sudo().dias_journal_id
        payment = self.env['account.payment'].sudo().with_company(company).create({
            'payment_type': 'inbound',
            'partner_type': 'customer',
            'partner_id': partner.id,
            'amount': self.amount,
            'currency_id': company.currency_id.id,
            'journal_id': journal.id,
            'payment_method_line_id': journal.inbound_payment_method_line_ids[:1].id,
            'date': self.bk_date or self._dias_day(self.payment_dt) or fields.Date.context_today(self),
            'memo': ('%s | ΔΙΑΣ RID %s' % (rf.clean(self.ri_mid), self.name))[:200],
            'company_id': company.id,
        })
        payment.action_post()
        if not payment.move_id:
            raise UserError(_('Η πληρωμή δεν δημιούργησε λογιστική εγγραφή: ορίστε λογαριασμό '
                              'εκκαθάρισης στη μέθοδο πληρωμής του ημερολογίου ΔΙΑΣ.'))
        return payment

    @staticmethod
    def _dias_receivable(payment):
        return payment.move_id.line_ids.filtered(
            lambda l: l.account_id.account_type == 'asset_receivable' and not l.reconciled)

    def _dias_open_amount(self, payment):
        return -sum(self._dias_receivable(payment).mapped('amount_residual'))

    def _dias_allocate(self, payment, invoices):
        done = []
        for inv in invoices:
            line = self._dias_receivable(payment)[:1]
            if not line:
                break
            before = inv.amount_residual
            inv.js_assign_outstanding_line(line.id)
            # Χωρίς πραγματικό συμψηφισμό (π.χ. άλλος λογαριασμός απαίτησης) δεν γράφεται ως «έγινε».
            if inv.currency_id.compare_amounts(inv.amount_residual, before) < 0:
                done.append(inv.name)
        return done

    # ── Ενέργειες υπευθύνου ──────────────────────────────────────────────────

    def _dias_check_manager(self):
        if not self.env.user.has_group(MANAGER):
            raise UserError(_('Μόνο ο υπεύθυνος λογιστηρίου.'))

    def action_retry(self):
        """Σφάλμα (π.χ. έλειπε ρύθμιση): ξανά «Προς καταχώρηση»."""
        self._dias_check_manager()
        recs = self.filtered(lambda r: r.state == 'error')
        recs.sudo().write({'state': 'new', 'message': False})
        recs.sudo()._dias_process()

    def action_book_credit(self):
        """Χωρίς αντιστοίχιση / κωδικός v13: καταχώρηση ως πίστωση στον πελάτη που όρισε ο χρήστης.
        Η κατανομή σε τιμολόγια γίνεται μετά από το ίδιο το τιμολόγιο (εκκρεμείς πιστώσεις)."""
        self._dias_check_manager()
        for rec in self.sudo():
            if rec.state not in ('unmatched', 'v13') or rec.payment_id:
                raise UserError(_('Μόνο για πληρωμές χωρίς αντιστοίχιση ή με κωδικό v13.'))
            if not rec.partner_id:
                raise UserError(_('Ορίστε πρώτα τον πελάτη.'))
            problems = rec.company_id._dias_ready_problems()
            if problems:
                raise UserError(_('Λείπουν ρυθμίσεις ΔΙΑΣ: %s', ', '.join(problems)))
            payment = rec._dias_book(rec.partner_id.commercial_partner_id)
            rec.write({'state': 'credit', 'payment_id': payment.id, 'message': _(
                'Καταχωρήθηκε ως πίστωση του %(p)s από %(u)s.',
                p=rec.partner_id.display_name, u=self.env.user.name)})
            rec.activity_ids.action_feedback(feedback=_('Καταχωρήθηκε.'))

    def action_ignore(self):
        """Χρήματα που δεν αφορούν αυτή τη βάση (π.χ. τα καταχώρησε το παλιό σύστημα)."""
        self._dias_check_manager()
        for rec in self.sudo():
            if rec.state not in NEEDS_HUMAN or rec.payment_id:
                raise UserError(_('Μόνο για πληρωμές που δεν έχουν καταχωρηθεί.'))
            rec.write({'state': 'ignored', 'message': (rec.message or '') + '\n' + _(
                'Αγνοήθηκε από %s.', self.env.user.name)})
            rec.activity_ids.action_feedback(feedback=_('Αγνοήθηκε.'))

    # ── Ειδοποιήσεις και cron ────────────────────────────────────────────────

    def _dias_alert(self, summary, note):
        for rec in self:
            user = rec.company_id.sudo().dias_manager_id
            if user:
                rec.sudo().activity_schedule('mail.mail_activity_data_todo', user_id=user.id,
                                             summary=summary, note=note)

    @api.model
    def _cron_dias_process(self):
        """Επεξεργάζεται ό,τι περιμένει (και ό,τι έμεινε από διακοπή), και ειδοποιεί για
        εγκρίσεις κωδικού που δεν επιβεβαιώθηκαν ποτέ ως πληρωμή."""
        pending = self.sudo().search([('state', '=', 'new')], order='id')
        Cron = self.env['ir.cron']
        Cron._commit_progress(remaining=len(pending))
        for rec in pending:
            rec._dias_process()
            if not Cron._commit_progress(1):
                return
        limit = fields.Datetime.now() - timedelta(days=STALE_VALIDATED_DAYS + 2)
        for rec in self.sudo().search([('state', '=', 'validated'), ('stale_alerted', '=', False),
                                       ('validated_at', '<', limit)]):
            rec.stale_alerted = True
            rec._dias_alert(_('ΔΙΑΣ: έγκριση χωρίς πληρωμή'), _(
                'Ο κωδικός %(code)s εγκρίθηκε στις %(at)s αλλά η πληρωμή δεν επιβεβαιώθηκε (ούτε online '
                'ούτε σε αρχείο). Ελέγξτε στο ΔΙΑΣ Portal.', code=rec.ri_mid, at=rec.validated_at))
