import base64
import logging
import re
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .ergani_client import (ErganiAuthError, ErganiClient, ErganiError, ErganiNotSent,
                            ErganiRejected, ErganiThrottled, ErganiUnknown)

_logger = logging.getLogger(__name__)
BATCH = 20
LATE_MINUTES = 14
STALE_SENDING_MINUTES = 10
PSEUDONYMISE_AFTER_DAYS = 730
RECEIPT_BATCH = 5


def _yyyymmdd(submit_date_raw):
    """ΕΡΓΑΝΗ's submitDate «04/05/2022 01:13» → «20220504» (guide γρ. 371)."""
    m = re.search(r'(\d{2})/(\d{2})/(\d{4})', submit_date_raw or '')
    if m:
        return m.group(3) + m.group(2) + m.group(1)
    m = re.search(r'(\d{4})-(\d{2})-(\d{2})', submit_date_raw or '')
    return ''.join(m.groups()) if m else False


class ErganiCard(models.Model):
    _inherit = 'ergani.card'

    # The same limit the sender uses to call a card late — never a «margin».
    deadline = fields.Datetime(string='Εμπρόθεσμη έως', compute='_compute_deadline')
    receipt_requested = fields.Boolean(readonly=True)
    receipt_attachment_id = fields.Many2one('ir.attachment', string='Αποδεικτικό',
                                            readonly=True)
    receipt_error = fields.Char(string='Σφάλμα αποδεικτικού', readonly=True)
    receipt_available = fields.Boolean(compute='_compute_receipt_available')

    @api.depends('event_datetime')
    def _compute_deadline(self):
        for card in self:
            card.deadline = card.event_datetime and (
                card.event_datetime + timedelta(minutes=LATE_MINUTES))

    @api.depends('state', 'submit_date_raw', 'protocol', 'environment')
    def _compute_receipt_available(self):
        for card in self:
            card.receipt_available = bool(
                card.state == 'sent' and card.protocol and card.environment != 'simulation'
                and _yyyymmdd(card.submit_date_raw))

    # ── Sender (DESIGN §5.7) ─────────────────────────────────────────────────

    @api.model
    def _cron_ergani_send(self):
        Cron = self.env['ir.cron']
        now = fields.Datetime.now()
        # A card left 'sending' by a crash may have reached ΕΡΓΑΝΗ.
        stale = self.sudo().search([
            ('state', '=', 'sending'),
            ('write_date', '<', now - timedelta(minutes=STALE_SENDING_MINUTES))])
        for card in stale:
            card.write({'state': 'unknown', 'last_error': _('Έμεινε «Αποστέλλεται» (διακοπή).')})
            card._ergani_notify(_('ΕΡΓΑΝΗ: άγνωστη έκβαση'), card.last_error)
        for company in self.env['res.company'].sudo().search(
                [('ergani_mode', 'in', ('trial', 'production')), ('ergani_paused', '=', False)]):
            cards = self.sudo().search([
                ('company_id', '=', company.id), ('state', '=', 'pending'),
                ('environment', '=', company.ergani_mode)], order='event_datetime asc, id asc')
            # Schedule changes first: they have a hard deadline (before work starts).
            self.env['ergani.wto']._ergani_send_pending(company)
            sent = 0
            for card in cards:
                if sent >= BATCH or company.ergani_paused:
                    break
                if card.in_card_id and card.in_card_id.state in ('pending', 'sending'):
                    continue  # an out card never overtakes its in card
                if not card._ergani_prepare_late():
                    continue
                card._ergani_send_one(company)
                sent += 1
                remaining = Cron._commit_progress(1)
                if remaining is not None and remaining <= 0:
                    return
            if not company.ergani_paused:
                self._ergani_fetch_receipts(company)

    def _ergani_fetch_receipts(self, company):
        """Receipts are fetched here, by the single sender, never inside a UI
        request (token row lock, commits). Read-only: a failure never touches
        the card's state."""
        Cron = self.env['ir.cron']
        cards = self.sudo().search([
            ('company_id', '=', company.id), ('receipt_requested', '=', True),
            ('environment', '=', company.ergani_mode)], limit=RECEIPT_BATCH)
        for card in cards:
            vals = {'receipt_requested': False}
            try:
                pdf = ErganiClient(company).get_receipt(
                    card.protocol, _yyyymmdd(card.submit_date_raw), card=card)
            except ErganiError as e:
                vals['receipt_error'] = str(e)[:250]
            else:
                attachment = self.env['ir.attachment'].sudo().create({
                    'name': 'ΕΡΓΑΝΗ_%s.pdf' % card.protocol,
                    'datas': base64.b64encode(pdf),
                    'mimetype': 'application/pdf',
                    'res_model': 'ergani.card',
                    'res_id': card.id,
                })
                vals.update(receipt_attachment_id=attachment.id, receipt_error=False)
            card.write(vals)
            Cron._commit_progress(0)

    def _ergani_prepare_late(self):
        """Late (> 14' after the punch) needs f_aitiologia. A recorded
        technical failure gets the «σύνδεση ΕΡΓΑΝΗ» code automatically;
        anything else waits for a person (DESIGN §3, §5.7)."""
        self.ensure_one()
        late = fields.Datetime.now() - self.event_datetime > timedelta(minutes=LATE_MINUTES)
        if not late or self.aitiologia:
            if late and not self.late:
                self.late = True
            return True
        code = (self.company_id.ergani_late_reason_id.code
                or self.company_id.ergani_late_reason_code)
        if self.technical_failure and code:
            self.write({'late': True, 'aitiologia': code})
            self.payload = self._ergani_json_payload()
            return True
        if not self.late:
            self.late = True
            self._ergani_notify(_('ΕΡΓΑΝΗ: εκπρόθεσμη κάρτα'), _(
                'Η κάρτα %s δεν στάλθηκε εγκαίρως και δεν υπάρχει καταγεγραμμένη '
                'τεχνική αιτία. Εκπρόθεσμη δήλωση επιτρέπεται μόνο για τεχνική αδυναμία '
                '(συστήματα εργοδότη, ηλεκτροδότηση/τηλεπικοινωνίες, σύνδεση ΕΡΓΑΝΗ): ορίστε '
                'αιτιολογία και ειδοποιήστε την Επιθεώρηση Εργασίας όταν άρχισε και όταν έληξε '
                'η αδυναμία.', self.display_label))
        return False

    def _ergani_json_payload(self):
        import json
        return json.dumps(self._ergani_payload(), ensure_ascii=False)

    def _ergani_send_one(self, company):
        self.ensure_one()
        Cron = self.env['ir.cron']
        self.write({'state': 'sending', 'attempts': self.attempts + 1})
        Cron._commit_progress(0)  # 'sending' is durable before the POST
        try:
            entry, raw = ErganiClient(company).post_card(self._ergani_payload(), card=self)
        except ErganiNotSent as e:
            self.write({'state': 'pending', 'last_error': str(e), 'technical_failure': True})
        except ErganiUnknown as e:
            self.write({'state': 'unknown', 'last_error': str(e), 'technical_failure': True})
            self._ergani_notify(_('ΕΡΓΑΝΗ: άγνωστη έκβαση'), _(
                '%(card)s: %(err)s. Ελέγξτε στο ΕΡΓΑΝΗ αν καταχωρίστηκε πριν την '
                'ξαναστείλετε.', card=self.display_label, err=e))
        except ErganiRejected as e:
            self.write({'state': 'error', 'last_error': str(e), 'response': str(e)})
            self._ergani_notify(_('ΕΡΓΑΝΗ: απόρριψη κάρτας'), _(
                '%(card)s: %(err)s', card=self.display_label, err=e))
            self._ergani_pause_if_repeated(company, str(e))
        except (ErganiAuthError, ErganiThrottled) as e:
            self.write({'state': 'pending', 'last_error': str(e)})
            self._ergani_pause(company, str(e))
        except Exception as e:  # anything unexpected after 'sending': be safe
            _logger.exception('ΕΡΓΑΝΗ send failed for card %s', self.id)
            self.write({'state': 'unknown', 'last_error': str(e)})
            self._ergani_notify(_('ΕΡΓΑΝΗ: άγνωστη έκβαση'), str(e))
        else:
            self.write({'state': 'sent', 'ergani_id': str(entry.get('id') or ''),
                        'protocol': str(entry.get('protocol') or ''),
                        'submit_date_raw': str(entry.get('submitDate') or ''),
                        'response': raw, 'last_error': False})

    def _ergani_pause_if_repeated(self, company, message):
        same = self.sudo().search_count([
            ('company_id', '=', company.id), ('state', '=', 'error'),
            ('last_error', '=', message)])
        if same >= 2:
            self._ergani_pause(company, message)

    def _ergani_pause(self, company, reason):
        if company.ergani_paused:
            return
        company.write({'ergani_paused': True, 'ergani_pause_reason': reason[:250]})
        self._ergani_notify(_('ΕΡΓΑΝΗ: παύση αποστολής'), _(
            'Η αποστολή καρτών σταμάτησε: %s. Διορθώστε και πατήστε «Συνέχιση '
            'αποστολής» στις Ρυθμίσεις ΕΡΓΑΝΗ.', reason))

    # ── Unknown / late resolution (manager) ──────────────────────────────────

    def _ergani_check_manager(self):
        if not self.env.user.has_group('base.group_system'):
            raise UserError(_('Μόνο ο διαχειριστής.'))

    # Nobody has write access on cards (ir.model.access): every change below
    # goes through sudo, only from the states the action is meant for, and
    # leaves «resolved by» plus a chatter line.

    def action_ergani_found(self):
        """«Βρέθηκε στο ΕΡΓΑΝΗ»: the card reached ΕΡΓΑΝΗ; record its protocol."""
        self._ergani_check_manager()
        self.ensure_one()
        if self.state != 'unknown':
            raise UserError(_('Μόνο για κάρτα με άγνωστη έκβαση.'))
        return {
            'type': 'ir.actions.act_window', 'res_model': 'ergani.card.resolve',
            'view_mode': 'form', 'target': 'new',
            'context': {'default_card_id': self.id, 'default_action': 'found'},
        }

    def action_ergani_resend(self):
        self._ergani_check_manager()
        for card in self.sudo().filtered(lambda c: c.state in ('unknown', 'error')):
            card.write({'state': 'pending', 'resolved_by_id': self.env.user.id})
            card.message_post(body=_('Επαναποστολή από %s.', self.env.user.name))
        self.env.ref('l10n_gr_ergani_card.ir_cron_ergani_send').sudo()._trigger()

    def action_ergani_ignore(self):
        self._ergani_check_manager()
        for card in self.sudo().filtered(lambda c: c.state in ('unknown', 'error')):
            card.write({'resolved_by_id': self.env.user.id})
            card.message_post(body=_('Αγνοήθηκε από %s.', self.env.user.name))
            card.activity_ids.action_feedback(feedback=_('Αγνοήθηκε.'))

    def action_ergani_set_reason(self):
        self._ergani_check_manager()
        self.ensure_one()
        if not self._ergani_needs_reason():
            raise UserError(_('Αιτιολογία ορίζεται μόνο σε εκπρόθεσμη κάρτα σε αναμονή.'))
        return {
            'type': 'ir.actions.act_window', 'res_model': 'ergani.card.resolve',
            'view_mode': 'form', 'target': 'new',
            'context': {'default_card_id': self.id, 'default_action': 'reason'},
        }

    def action_ergani_receipt(self):
        """Open the stored receipt, or ask the sender to fetch it. The employee
        may do this for his own cards («Οι κάρτες μου»)."""
        self.ensure_one()
        self.check_access('read')
        card = self.sudo()
        if card.receipt_attachment_id:
            return {'type': 'ir.actions.act_url', 'target': 'new',
                    'url': '/web/content/%s?download=true' % card.receipt_attachment_id.id}
        if not card.receipt_available:
            raise UserError(_('Αποδεικτικό υπάρχει μόνο για κάρτα που στάλθηκε στο ΕΡΓΑΝΗ.'))
        card.write({'receipt_requested': True, 'receipt_error': False})
        self.env.ref('l10n_gr_ergani_card.ir_cron_ergani_send').sudo()._trigger()
        return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {
            'type': 'info', 'message': _('Το αποδεικτικό ζητήθηκε από το ΕΡΓΑΝΗ. '
                                         'Ξαναπατήστε σε λίγο για να ανοίξει.')}}

    def _ergani_needs_reason(self):
        self.ensure_one()
        return self.state == 'pending' and self.late and not self.aitiologia

    # ── Housekeeping (DESIGN §3, §5.3) ───────────────────────────────────────

    @api.model
    def _cron_ergani_housekeeping(self):
        self.env['hr.employee'].sudo().search(
            [('ergani_enabled', '=', True)])._ergani_flag_forgotten()
        self.env['ergani.submission']._ergani_clear_old_bodies()
        import hashlib
        old = self.sudo().search([
            ('pseudonymised', '=', False),
            ('event_datetime', '<', fields.Datetime.now() - timedelta(days=PSEUDONYMISE_AFTER_DAYS))])
        for card in old:
            card.write({
                key: hashlib.sha256((card[key] or '').encode()).hexdigest()[:12]
                for key in ('client_ip', 'user_agent', 'session_hash') if card[key]
            } | {'pseudonymised': True})


class ErganiCardResolve(models.TransientModel):
    _name = 'ergani.card.resolve'
    _description = 'ΕΡΓΑΝΗ: επίλυση κάρτας'

    card_id = fields.Many2one('ergani.card', required=True)
    action = fields.Selection([('found', 'Βρέθηκε στο ΕΡΓΑΝΗ'), ('reason', 'Αιτιολογία')],
                              required=True)
    protocol = fields.Char(string='Πρωτόκολλο ΕΡΓΑΝΗ')
    reason_id = fields.Many2one('ergani.delay.reason', string='Αιτιολογία')

    def action_confirm(self):
        self.ensure_one()
        card = self.card_id.sudo()
        if not self.env.user.has_group('base.group_system'):
            raise UserError(_('Μόνο ο διαχειριστής.'))
        if self.action == 'found':
            if card.state != 'unknown':
                raise UserError(_('Μόνο για κάρτα με άγνωστη έκβαση.'))
            if not self.protocol:
                raise UserError(_('Συμπληρώστε το πρωτόκολλο.'))
            card.write({'state': 'sent', 'protocol': self.protocol,
                        'resolved_by_id': self.env.user.id})
            card.message_post(body=_('Βρέθηκε στο ΕΡΓΑΝΗ (πρωτόκολλο %(p)s) — %(u)s.',
                                     p=self.protocol, u=self.env.user.name))
        else:
            if not card._ergani_needs_reason():
                raise UserError(_('Αιτιολογία ορίζεται μόνο σε εκπρόθεσμη κάρτα σε αναμονή.'))
            if not self.reason_id:
                raise UserError(_('Επιλέξτε αιτιολογία. Αν η λίστα είναι κενή: Ρυθμίσεις ΕΡΓΑΝΗ → '
                                  '«Αιτιολογίες από ΕΡΓΑΝΗ».'))
            card.write({'aitiologia': self.reason_id.code, 'resolved_by_id': self.env.user.id})
            card.payload = card._ergani_json_payload()
            card.message_post(body=_('Αιτιολογία %(a)s από %(u)s. Ειδοποιήστε την Επιθεώρηση '
                                     'Εργασίας για την έναρξη και τη λήξη της αδυναμίας.',
                                     a=self.reason_id.display_name, u=self.env.user.name))
            self.env.ref('l10n_gr_ergani_card.ir_cron_ergani_send').sudo()._trigger()
        card.activity_ids.action_feedback(feedback=_('Επιλύθηκε.'))
