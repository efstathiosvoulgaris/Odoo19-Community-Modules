# -*- coding: utf-8 -*-
"""Δελτίο Παραγγελίας Εστίασης (AADE 8.6).

An order note is an informational document, not a document of value: it is
deliberately NOT an account.move, because posting an invoice per kitchen round
would book revenue that the closing ΑΛΠ books again.

Rules implemented here (ILYDA «Οδηγίες υλοποίησης Διαβίβασης Δελτίων
Παραγγελίας Εστίασης», AADE Α.1138/2020 as amended by Α.1170/2023):
  - type 8.6 with the table number (tableAA), one note per round;
  - income classified exclusively as category1_95, never an E3 code;
  - real VAT per rate (categories 1–7); 0% uses exemption 27;
  - the note is closed by a document of value that carries its MARK.

Cancellation (§4 and use cases §5.2 / §5.4 of the ILYDA guide) — an open note
blocks every further catering transaction of the entity, so both routes exist:
  - items removed from a round → a NEW note whose rows carry `recType: 7`
    («αρνητικό δελτίο»), amounts positive, within 24h of the original;
  - the whole table walked out → a zero-value note with
    `totalCancelDeliveryOrders: true` and the cancelled MARKs in
    `multipleConnectedMarks` («Καθολική Ακύρωση 8.6»), which closes them
    without any correlation.
"""
import hashlib
import logging
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError

from odoo.addons.l10n_gr_provider_base.models.gr_mydata import VAT_CATEGORY_MAP
from odoo.addons.l10n_gr_provider_ilyda.models.account_move import (
    IlydaClient, _r2,
)

_logger = logging.getLogger(__name__)

# «Λοιπές Εξαιρέσεις ΦΠΑ» — the exemption the spec prescribes for 0% lines
CATERING_VAT_EXEMPTION = 27
# AADE special category «Παραστατικό Εστίασης», mandatory on the closing document
CATERING_SPECIAL_CATEGORY = 12
# «Χωρίς ΦΠΑ» — the VAT category the guide prescribes on a Καθολική Ακύρωση row
CANCEL_VAT_CATEGORY = 8


class L10nGrProvCateringOrder(models.Model):
    _name = 'l10n.gr.prov.catering.order'
    # Both mixins: the 24h alert schedules an activity, and mail.activity
    # subscribes the assignee on create — which needs mail.thread.
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Δελτίο Παραγγελίας Εστίασης (8.6)'
    _order = 'create_date desc, id desc'
    _rec_name = 'display_name'

    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company)
    config_id = fields.Many2one('pos.config', string='Ταμείο POS')
    session_id = fields.Many2one('pos.session', string='Συνεδρία')
    table_aa = fields.Char(string='ΑΑ Τραπεζιού', required=True)
    # The POS order may not be synced server-side when the round is sent, so the
    # link is by uuid and resolved to the order when the table is closed.
    pos_order_uuid = fields.Char(string='POS Order UUID', index=True)
    pos_order_id = fields.Many2one('pos.order', string='Παραγγελία POS')
    closing_move_id = fields.Many2one(
        'account.move', string='Παραστατικό Κλεισίματος', copy=False,
        help='Το παραστατικό αξίας που έκλεισε το δελτίο (ΑΛΠ/ΤΙΜ).')

    kind = fields.Selection([
        ('order', 'Παραγγελία'),
        ('negative', 'Αρνητικό (ακύρωση ειδών)'),
        ('cancel', 'Καθολική Ακύρωση 8.6'),
    ], default='order', required=True, string='Είδος Δελτίου')
    cancelled_note_ids = fields.Many2many(
        'l10n.gr.prov.catering.order', 'l10n_gr_prov_catering_cancel_rel',
        'cancel_id', 'note_id', string='Ακυρωθέντα Δελτία', copy=False,
        help='Τα δελτία που κλείνει αυτή η Καθολική Ακύρωση.')

    line_ids = fields.One2many(
        'l10n.gr.prov.catering.order.line', 'order_id', string='Είδη')
    amount_net = fields.Monetary(
        compute='_compute_amounts', store=True, currency_field='currency_id')
    amount_vat = fields.Monetary(
        compute='_compute_amounts', store=True, currency_field='currency_id')
    amount_total = fields.Monetary(
        compute='_compute_amounts', store=True, currency_field='currency_id')
    currency_id = fields.Many2one(related='company_id.currency_id')

    # ── Provider markings ────────────────────────────────────────────────────
    state = fields.Selection([
        ('draft', 'Πρόχειρο'),
        ('sent', 'Διαβιβάστηκε'),
        ('closed', 'Έκλεισε'),
        ('cancelled', 'Ακυρώθηκε'),
        ('error', 'Σφάλμα'),
    ], default='draft', required=True, copy=False, string='Κατάσταση')
    mark = fields.Char(string='MARK', copy=False, index=True)
    invoice_id_provider = fields.Char(string='Provider Invoice ID', copy=False)
    verification_hash = fields.Char(string='Συμβ. Αυθεντικοποίησης', copy=False)
    qr_url = fields.Char(string='QR URL', copy=False)
    error_message = fields.Text(string='Σφάλμα', copy=False)
    series = fields.Char(string='Σειρά', default='ΔΠΕ')
    serial = fields.Char(string='Αριθμός', copy=False)
    # Fixed at the first attempt: the date is part of the document's UID, so
    # a retry after midnight must not turn it into a different document.
    issue_date = fields.Date(string='Ημερομηνία Έκδοσης', copy=False)

    @api.depends('line_ids.net_value', 'line_ids.vat_amount')
    def _compute_amounts(self):
        for order in self:
            order.amount_net = sum(order.line_ids.mapped('net_value'))
            order.amount_vat = sum(order.line_ids.mapped('vat_amount'))
            order.amount_total = order.amount_net + order.amount_vat

    @api.depends('table_aa', 'serial', 'mark', 'kind')
    def _compute_display_name(self):
        labels = {'negative': ' (αρνητικό)', 'cancel': ' (καθολική ακύρωση)'}
        for order in self:
            order.display_name = _(
                'ΔΠΕ %(serial)s — Τραπέζι %(table)s%(kind)s',
                serial=order.serial or '—', table=order.table_aa or '—',
                kind=labels.get(order.kind, ''))

    # ── Issue ────────────────────────────────────────────────────────────────

    @api.model
    def l10n_gr_prov_issue_note(self, vals):
        """Create and transmit one order note. Called from the POS when a round
        is sent to the kitchen.

        `vals`: config_id, table_aa, pos_order_uuid, lines
        [{name, prep_key, quantity, net, vat_amount, vat_rate}]. Returns a dict
        the POS can show on the ticket; never raises, so a provider failure
        cannot block service.

        Only additions: whatever went down — an item removed, a quantity cut,
        a discount or a treat — is found by l10n_gr_prov_reconcile.
        """
        lines = [line for line in (vals.get('lines') or [])
                 if (line.get('quantity') or 0) > 0 and (line.get('net') or 0) >= 0]
        if not lines:
            return {}
        config = self.env['pos.config'].browse(vals['config_id'])
        # The front end asks on every round; the server decides. A till that is
        # not wired to the provider, or has the automation switched off, issues
        # nothing.
        if not config.l10n_gr_prov_enabled or not config.l10n_gr_prov_catering_notes:
            return {}
        return self._l10n_gr_prov_issue(config, vals, 'order', lines)

    def _l10n_gr_prov_issue(self, config, vals, kind, lines):
        order = self.create({
            'company_id': config.company_id.id,
            'config_id': config.id,
            'session_id': config.current_session_id.id,
            'kind': kind,
            'table_aa': vals.get('table_aa') or '—',
            'pos_order_uuid': vals.get('pos_order_uuid'),
            'serial': self.env['ir.sequence'].next_by_code(
                'l10n.gr.prov.catering.order') or False,
            'line_ids': [(0, 0, {
                'name': (line.get('name') or '')[:200],
                'prep_key': line.get('prep_key'),
                'quantity': line['quantity'],
                'net_value': _r2(line.get('net') or 0),
                'vat_amount': _r2(line.get('vat_amount') or 0),
                'vat_rate': line.get('vat_rate') or 0,
            }) for line in lines],
        })
        order._l10n_gr_prov_send()
        return order._l10n_gr_prov_ticket_values()

    @api.model
    def l10n_gr_prov_relink(self, vals):
        """Tables merged or an order moved to another table.

        Odoo moves the lines into the destination order under new uuids and
        deletes the source order. Its notes would then belong to no order —
        nothing would ever close them — and a later cancellation could not
        find the row that transmitted the item. So the notes follow the order,
        and each row takes its line's new preparation key.

        `vals`: source_uuid, dest_uuid, keys {old preparationKey: new}.
        """
        source, dest = vals.get('source_uuid'), vals.get('dest_uuid')
        if not source or not dest or source == dest:
            return {}
        notes = self.search([
            ('pos_order_uuid', '=', source),
            ('state', 'in', ('draft', 'error', 'sent')),
        ])
        if not notes:
            return {}
        keys = vals.get('keys') or {}
        notes.write({'pos_order_uuid': dest})
        for row in notes.line_ids:
            if row.prep_key in keys:
                row.prep_key = keys[row.prep_key]
        for note in notes:
            note.message_post(body=_(
                'Μεταφέρθηκε στην παραγγελία του τραπεζιού %(table)s '
                '(συγχώνευση ή μεταφορά τραπεζιού).',
                table=vals.get('table_aa') or '—'))
        return {'relinked': len(notes)}

    @api.model
    def l10n_gr_prov_reconcile(self, vals):
        """Issue the «αρνητικό» note for whatever went down since transmission.

        Guide §4.3: an item removed, a quantity cut, and a discount or treat on
        an earlier round each need a note with the opposite sign (recType 7).
        The till sends every line as it stands now (`lines`: prep_key, name,
        quantity, net, vat_amount); per line, what AADE already holds is the
        sum of its transmitted rows, negatives subtracted. Anything above what
        the line is worth now is credited. Called on every send to the kitchen
        and before the payment screen — a deleted line alone is no «change»
        to Odoo, so Pay would otherwise skip it.

        Amounts are positive; recType 7 carries the sign. Quantity is what was
        taken off, or — for a price cut on an unchanged quantity — the line's
        quantity, with only the difference as value.
        """
        config = self.env['pos.config'].browse(vals['config_id'])
        if (not config.l10n_gr_prov_enabled or not config.l10n_gr_prov_catering_notes
                or not config.l10n_gr_prov_catering_auto_negative):
            return {}
        uuid = vals.get('pos_order_uuid')
        if not uuid:
            return {}
        # Credit only what AADE holds (positives that were sent), but subtract
        # every negative already issued — one stuck in error is retried later,
        # and issuing another now would credit the same item twice.
        rows = self.env['l10n.gr.prov.catering.order.line'].search([
            ('order_id.pos_order_uuid', '=', uuid),
            ('prep_key', '!=', False),
            '|',
            '&', ('order_id.kind', '=', 'order'), ('order_id.state', '=', 'sent'),
            '&', ('order_id.kind', '=', 'negative'),
                 ('order_id.state', 'in', ('draft', 'error', 'sent')),
        ])
        if not rows:
            return {}
        sent = {}
        for row in rows:
            sign = -1 if row.order_id.kind == 'negative' else 1
            acc = sent.setdefault(row.prep_key, {
                'quantity': 0.0, 'net': 0.0, 'vat': 0.0,
                'name': row.name, 'rate': row.vat_rate})
            acc['quantity'] += sign * row.quantity
            acc['net'] += sign * row.net_value
            acc['vat'] += sign * row.vat_amount
            if sign > 0:
                acc['name'], acc['rate'] = row.name, row.vat_rate
        now = {line.get('prep_key'): line for line in (vals.get('lines') or [])
               if line.get('prep_key')}
        credit = []
        for key, acc in sent.items():
            if acc['quantity'] <= 0 or acc['net'] <= 0.005:
                continue
            line = now.get(key) or {}
            quantity = max(line.get('quantity') or 0.0, 0.0)
            net = max(line.get('net') or 0.0, 0.0)
            vat = max(line.get('vat_amount') or 0.0, 0.0)
            less_qty = max(acc['quantity'] - quantity, 0.0)
            less_net = _r2(acc['net'] - net)
            if less_qty <= 0 and less_net < 0.01:
                continue
            credit.append({
                'name': acc['name'],
                'prep_key': key,
                'quantity': less_qty or acc['quantity'],
                'net': max(less_net, 0.0),
                'vat_amount': max(_r2(acc['vat'] - vat), 0.0),
                'vat_rate': acc['rate'],
            })
        if not credit:
            return {}
        return self._l10n_gr_prov_issue(config, vals, 'negative', credit)

    def _l10n_gr_prov_ticket_values(self):
        self.ensure_one()
        return {
            'id': self.id,
            'state': self.state,
            'mark': self.mark or '',
            'qr_url': self.qr_url or '',
            'serial': self.serial or '',
            'table_aa': self.table_aa or '',
            'error': self.error_message or '',
        }

    def _l10n_gr_prov_send(self):
        """Transmit to the provider. Failures are recorded, never raised: the
        kitchen round must go out even when the provider is unreachable."""
        self.ensure_one()
        if not self.issue_date:
            self.issue_date = fields.Date.context_today(self)
        try:
            client = IlydaClient(self.company_id)
            payload = self._l10n_gr_prov_build_payload()
            _logger.info('ILYDA 8.6 payload for %s: %s', self.display_name, payload)
            data = client.submit_invoice(payload)
            _logger.info('ILYDA 8.6 response for %s: %s', self.display_name, data)
            self._l10n_gr_prov_handle_response(data)
        except Exception as e:
            _logger.exception('Δελτίο Παραγγελίας transmission failed (%s)',
                              self.display_name)
            self.write({'state': 'error', 'error_message': str(e)})

    def _l10n_gr_prov_handle_response(self, data):
        self.ensure_one()
        marking = (data or {}).get('invoiceMarking') or {}
        errors = (data or {}).get('errors') or []
        if not marking.get('mark'):
            details = '; '.join(
                f"{e.get('code')}: {e.get('defaultMessage') or e.get('aadeMessage')}"
                for e in errors) or _('Ο πάροχος δεν επέστρεψε MARK.')
            self.write({'state': 'error', 'error_message': details})
            return
        self.write({
            'state': 'sent',
            'mark': str(marking['mark']),
            'invoice_id_provider': marking.get('invoiceId'),
            'verification_hash': marking.get('verificationHash'),
            'qr_url': marking.get('qrCode'),
            'error_message': False,
        })

    def action_retry(self):
        for order in self.filtered(lambda o: o.state in ('draft', 'error')):
            if order._l10n_gr_prov_table_closed():
                raise UserError(_(
                    '%(note)s: το τραπέζι έχει ήδη κλείσει. Αν το δελτίο σταλεί '
                    'τώρα, δεν θα το κλείσει κανένα παραστατικό και μετά από 24 '
                    'ώρες ο πάροχος θα αναστείλει τη διαβίβαση.',
                    note=order.display_name))
            order._l10n_gr_prov_retry()

    def _l10n_gr_prov_retry(self):
        """Resend a note that failed — but only after asking the provider.

        The request may have reached ILYDA even though the answer was lost; a
        blind resend would then transmit the same round twice. A failed lookup
        is recorded and nothing is sent.
        """
        self.ensure_one()
        try:
            if self._l10n_gr_prov_recover():
                return
        except Exception as e:
            _logger.exception('8.6 lookup failed (%s)', self.display_name)
            self.error_message = _(
                'Η αναζήτηση στον πάροχο απέτυχε — δεν έγινε επανάληψη: %s', e)
            return
        self._l10n_gr_prov_send()

    def _l10n_gr_prov_table_closed(self):
        """The table this note belongs to is already paid or cancelled.

        A positive or negative note sent after that is left open at AADE: the
        document that would have carried its MARK has already gone out. A
        Καθολική Ακύρωση is the exception — it closes notes, it opens none.
        """
        self.ensure_one()
        if self.kind == 'cancel' or not self.pos_order_uuid:
            return False
        return bool(self.env['pos.order'].sudo().search_count([
            ('uuid', '=', self.pos_order_uuid),
            ('state', '!=', 'draft'),
        ]))

    def _l10n_gr_prov_uid(self):
        """The note's UID as the provider computes it (A.1035 Appendix B2),
        the same formula the invoices use: SHA-1 of
        vat-date-branch-type-series-serial in ISO-8859-7."""
        self.ensure_one()
        company = self.company_id
        text = '-'.join([
            self.env['account.move']._ilyda_vat(company.vat, prefixed=False),
            str(self.issue_date or ''),
            str(company.partner_id.l10n_gr_edi_branch_number or 0),
            '8.6',
            self.series or 'ΔΠΕ',
            self.serial or '1',
        ])
        return hashlib.sha1(text.encode('iso-8859-7', 'replace')).hexdigest()

    def _l10n_gr_prov_recover(self):
        """Look the note up at ILYDA by UID and adopt what it has.

        True: the provider has it (marked, or still in its queue) — do not
        resend. False: unknown there, or rejected — safe to send. Raises when
        the lookup itself fails, which must never read as «unknown».
        """
        self.ensure_one()
        if not self.issue_date or not self.serial:
            return False  # never attempted: nothing to find
        client = IlydaClient(self.company_id)
        Move = self.env['account.move']
        doc_uid = self._l10n_gr_prov_uid()
        data = Move._l10n_gr_prov_ilyda_lookup(client.find_by_uid, doc_uid)
        if data and data.get('mark'):
            self._l10n_gr_prov_adopt(
                data['mark'], data.get('invoiceVerificationHash'),
                data.get('myDataQrCode'), data.get('invoiceId'))
            return True
        entry = Move._l10n_gr_prov_ilyda_lookup(client.pending_by_uid, doc_uid)
        if not entry or not entry.get('uid'):
            return False
        if entry.get('mark'):
            self._l10n_gr_prov_adopt(
                entry['mark'], entry.get('verificationHash'), None, entry.get('invoiceId'))
            return True
        if entry.get('invoiceState') in ('RESUBMIT_PENDING', 'SUBMITTED'):
            self.error_message = _(
                'Σε ουρά διαβίβασης στον πάροχο (αναμονή myDATA) — δεν ξαναστέλνεται.')
            return True
        return False

    def _l10n_gr_prov_adopt(self, mark, verification_hash, qr_url, invoice_id):
        self.write({
            'state': 'sent',
            'mark': str(mark),
            'verification_hash': verification_hash or self.verification_hash,
            'qr_url': qr_url or self.qr_url,
            'invoice_id_provider': invoice_id or self.invoice_id_provider,
            'error_message': False,
        })
        self.message_post(body=_(
            'Το MARK ανακτήθηκε από τον πάροχο χωρίς επανυποβολή: %s', self.mark))

    @api.model
    def _cron_l10n_gr_prov_retry_failed(self):
        """Resend failed notes whose table is still open — after a lookup.

        One commit per note: a provider outage halfway through must not roll
        back the MARKs already obtained.
        """
        failed = self.search([('state', 'in', ('draft', 'error'))], order='id')
        for note in failed:
            if note._l10n_gr_prov_table_closed():
                continue
            note._l10n_gr_prov_retry()
            self.env['ir.cron']._commit_progress(1)

    @api.model
    def _cron_l10n_gr_prov_alert_open(self):
        """Warn about notes running out of their 24 hours.

        An unclosed note suspends transmission for the whole entity once the
        window passes, and the only cure is to close or cancel it — which
        nobody does if nobody notices. One activity per till per run, on the
        POS responsible, pointing at the till's open notes.
        """
        Note = self.env['l10n.gr.prov.catering.order']
        self._cron_l10n_gr_prov_retry_failed()
        for config in self.env['pos.config'].search(
                [('l10n_gr_prov_catering_alert_hours', '>', 0)]):
            deadline = fields.Datetime.now() - timedelta(
                hours=config.l10n_gr_prov_catering_alert_hours)
            # Open at AADE = transmitted and not closed by a MARKED document.
            # A closing document that failed to transmit closes nothing.
            notes = Note.search([
                ('config_id', '=', config.id),
                ('state', '=', 'sent'),
                '|', ('closing_move_id', '=', False),
                     ('closing_move_id.l10n_gr_prov_mark', '=', False),
                ('create_date', '<=', deadline),
            ])
            # Never transmitted, even after the retry above: the waiter's
            # round is not at AADE at all. Shown at once, not after N hours.
            # A table already closed is past help (sending now would leave the
            # note open), so it is not flagged again every hour.
            failed = Note.search([
                ('config_id', '=', config.id),
                ('state', 'in', ('draft', 'error')),
            ]).filtered(lambda n: not n._l10n_gr_prov_table_closed())
            notes |= failed
            if not notes:
                continue
            # Hourly cron, same notes every run — one open activity per till is
            # a reminder, twenty-four is noise nobody reads.
            if self.env['mail.activity'].search_count([
                    ('res_model', '=', self._name),
                    ('res_id', 'in', notes.ids)]):
                continue
            # The cron runs as OdooBot, who never looks at anything: give it to
            # whoever last worked that till.
            session = self.env['pos.session'].search(
                [('config_id', '=', config.id)], order='id desc', limit=1)
            user = session.user_id or self.env.user
            notes[0].activity_schedule(
                'mail.mail_activity_data_todo',
                user_id=user.id,
                summary=_('%(count)s Δελτία Παραγγελίας Εστίασης θέλουν ενέργεια',
                          count=len(notes)),
                note=_(
                    'Ταμείο %(config)s: %(open)s δελτία παραμένουν ανοιχτά '
                    'πάνω από %(hours)s ώρες και %(failed)s δεν διαβιβάστηκαν '
                    '(συνολικά %(total).2f €). Κλείστε τα ανοιχτά με το '
                    'παραστατικό του τραπεζιού ή ακυρώστε τα — μετά τις 24 ώρες '
                    'ο πάροχος αναστέλλει τη διαβίβαση για όλη την επιχείρηση. '
                    'Για όσα δεν διαβιβάστηκαν, δείτε το σφάλμα στο δελτίο.',
                    config=config.name, open=len(notes - failed),
                    failed=len(failed),
                    hours=config.l10n_gr_prov_catering_alert_hours,
                    total=sum(notes.mapped('amount_total'))))

    # ── Cancellation ─────────────────────────────────────────────────────────

    @api.model
    def l10n_gr_prov_cancel_order(self, vals):
        """«Καθολική Ακύρωση 8.6» for a POS order the waiter cancelled.

        Called from the POS. Never raises: the till already cancelled the
        order, and an unsent cancellation is recoverable from the back office.
        """
        config = self.env['pos.config'].browse(vals['config_id'])
        if not config.l10n_gr_prov_catering_auto_cancel:
            # The notes stay open on purpose; they are cancelled by hand from
            # Λογιστική → Δελτία Παραγγελίας Εστίασης before the 24h limit.
            return {}
        notes = self.search([
            ('pos_order_uuid', '=', vals.get('pos_order_uuid')),
            ('state', '=', 'sent'),
            ('closing_move_id', '=', False),
        ])
        if not notes:
            return {}
        return notes._l10n_gr_prov_total_cancel()._l10n_gr_prov_ticket_values()

    def action_total_cancel(self):
        """Back-office «Καθολική Ακύρωση» over the selected open notes."""
        # A closing document the cron gave up on (abandoned) will never close
        # its notes, so they must be cancellable here before the 24h limit.
        notes = self.filtered(
            lambda n: n.state == 'sent' and n.mark and (
                not n.closing_move_id
                or n.closing_move_id.l10n_gr_prov_state == 'abandoned'))
        if not notes:
            raise UserError(_('Επιλέξτε διαβιβασμένα δελτία που δεν έχουν κλείσει.'))
        for _company, group in notes.grouped('company_id').items():
            group._l10n_gr_prov_total_cancel()

    def _l10n_gr_prov_total_cancel(self):
        """Issue ONE zero-value note carrying every MARK of `self`.

        On success the cancelled notes close at the provider without any
        further correlation, so they stop counting as open (guide §5.4).
        """
        marks = self.filtered(lambda n: n.mark)
        if not marks:
            return self.browse()
        company = marks[0].company_id
        cancel = self.create({
            'company_id': company.id,
            'config_id': marks[0].config_id.id,
            'session_id': marks[0].session_id.id,
            'kind': 'cancel',
            'table_aa': marks[0].table_aa,
            'pos_order_uuid': marks[0].pos_order_uuid,
            'serial': self.env['ir.sequence'].next_by_code(
                'l10n.gr.prov.catering.order') or False,
            'cancelled_note_ids': [(6, 0, marks.ids)],
            'line_ids': [(0, 0, {
                'name': 'Καθολική Ακύρωση',
                'quantity': 1.0,
                'net_value': 0.0,
                'vat_amount': 0.0,
                'vat_rate': 0.0,
            })],
        })
        cancel._l10n_gr_prov_send()
        if cancel.state == 'sent':
            # Detach from an abandoned closing document: resent by hand later,
            # it must not correlate notes that are cancelled at AADE.
            marks.write({'state': 'cancelled', 'closing_move_id': False})
        return cancel

    # ── Payload ──────────────────────────────────────────────────────────────

    def _l10n_gr_prov_vat_code(self, rate):
        """EN16931 VAT category code: Z on a Καθολική Ακύρωση (zero-rated),
        S on a taxed line, E on an exempt one."""
        if self.kind == 'cancel':
            return 'Z'
        return 'S' if rate else 'E'

    def _l10n_gr_prov_build_payload(self):
        """The 8.6 body. Deliberately compact: an order note carries no buyer,
        no extra taxes and no E3 classification."""
        self.ensure_one()
        company = self.company_id
        company_partner = company.partner_id
        Move = self.env['account.move']

        is_cancel = self.kind == 'cancel'
        invoice_lines, row_types, vat_buckets = [], [], {}
        for number, line in enumerate(self.line_ids, start=1):
            net, vat = _r2(line.net_value), _r2(line.vat_amount)
            rate = line.vat_rate or 0
            vat_category = (CANCEL_VAT_CATEGORY if is_cancel
                            else VAT_CATEGORY_MAP.get(int(rate), 7))
            bucket = vat_buckets.setdefault(rate, [0.0, 0.0, vat_category])
            bucket[0] += net
            bucket[1] += vat
            income = [{'classificationCategory': 'category1_95', 'amount': net}]
            row = {
                'lineNumber': number,
                'itemDescr': line.name or '',
                'quantity': line.quantity,
                'measurementUnit': 1,
                'netValue': net,
                'vatAmount': vat,
                'vatCategory': vat_category,
                'incomeClassification': income,
            }
            if vat_category == 7:
                row['vatExemptionCategory'] = CATERING_VAT_EXEMPTION
            if self.kind == 'negative':
                # The «αρνητικό» note carries positive amounts; recType 7 is
                # what makes AADE subtract them (guide §5.2).
                row['recType'] = 7
            row_types.append(row)
            invoice_lines.append({
                'lineNumber': number,
                'invoicedQuantity': line.quantity,
                'invoicedQuantityUnits': 'EA',
                'netAmount': net,
                'itemInfo': {
                    'itemInfoName': (line.name or '')[:200],
                    'itemInfoDescription': (line.name or '')[:200],
                },
                'priceDetails': {
                    'itemNetPrice': _r2(net / line.quantity) if line.quantity else net,
                    'itemPriceBaseQuantity': 1,
                },
                'lineVatInfo': {
                    'vatAmount': vat,
                    'vatRate': rate,
                    'vatCategoryCode': self._l10n_gr_prov_vat_code(rate),
                },
            })

        total_net = _r2(sum(b[0] for b in vat_buckets.values()))
        total_vat = _r2(sum(b[1] for b in vat_buckets.values()))
        total_gross = _r2(total_net + total_vat)

        aade_extra = {}
        if is_cancel:
            aade_extra = {
                'totalCancelDeliveryOrders': True,
                'multipleConnectedMarks': [
                    int(n.mark) for n in self.cancelled_note_ids if n.mark],
            }

        return {
            'b2g': False,
            'selfPricing': False,
            'vatPaidByBuyer': False,
            'invoiceTypeCode': '380',
            'seriesNumber': self.series or 'ΔΠΕ',
            'serialNumber': self.serial or '1',
            'invoiceIssueDate': f'{self.issue_date or fields.Date.context_today(self)}T00:00:00',
            'invoiceCurrencyCode': company.currency_id.name or 'EUR',
            'seller': {
                'sellerVatIdentifier': Move._ilyda_vat(company.vat),
                'sellerName': company.name,
                'sellerTradingName': company.name,
                'branch': company_partner.l10n_gr_edi_branch_number or 0,
                'sellerPostalAddress': {
                    'sellerCountryCode': company_partner.country_id.code or 'GR',
                    'sellerAddressLine1': company_partner.street or '',
                    'sellerCity': company_partner.city or '',
                    'sellerPostCode': company_partner.zip or '',
                },
            },
            'buyer': None,
            'invoiceLines': invoice_lines,
            'vatBreakdowns': [{
                'categoryCode': self._l10n_gr_prov_vat_code(rate),
                'categoryRate': rate,
                'categoryTaxableAmount': _r2(net),
                'categoryTaxAmount': _r2(vat),
            } for rate, (net, vat, _cat) in vat_buckets.items()],
            'docTotal': {
                'invoiceLinesNetAmountSum': total_net,
                'invoiceTotalWithoutVat': total_net,
                'invoiceTotalVatAmount': total_vat,
                'invoiceTotalAmountWithVat': total_gross,
                'amountDueForPayment': total_gross,
                'paidAmount': 0.0,
                'roundingAmount': 0.0,
                'documentLevelAllowancesSum': 0.0,
                'documentLevelChargesSum': 0.0,
                'exchangeRate': 0.0,
                'aadeDocTotals': {
                    'aadeTotalNetValue': total_net,
                    'aadeTotalVatAmount': total_vat,
                    'aadeTotalGrossValue': total_gross,
                    'aadeTotalWitheldAmount': 0.0,
                    'aadeTotalFeesAmount': 0.0,
                    'aadeTotalStampDutyAmount': 0.0,
                    'aadeTotalOtherTaxesAmount': 0.0,
                    'aadeTotalDeductionsAmount': 0.0,
                },
            },
            # «Επί Πιστώσει»: an order note is not paid, it is closed by a
            # document of value later.
            'paymentMethods': [{'type': 5, 'amount': total_gross}],
            'aadeData': {
                'aadeInvoiceTypeCode': '8.6',
                'tableAA': self.table_aa or '',
                'incomeClassifications': [{
                    'classificationCategory': 'category1_95',
                    'amount': total_net,
                }],
                'invoiceRowTypes': row_types,
                **aade_extra,
            },
        }


class L10nGrProvCateringOrderLine(models.Model):
    _name = 'l10n.gr.prov.catering.order.line'
    _description = 'Είδος Δελτίου Παραγγελίας Εστίασης'

    order_id = fields.Many2one(
        'l10n.gr.prov.catering.order', required=True, ondelete='cascade', index=True)
    currency_id = fields.Many2one(related='order_id.currency_id')
    name = fields.Char(string='Είδος', required=True)
    # POS preparationKey of the line this row came from — the handle a later
    # «αρνητικό» note uses to price a cancelled item off what was transmitted.
    prep_key = fields.Char(string='POS Key', index=True)
    quantity = fields.Float(string='Ποσότητα', default=1.0)
    net_value = fields.Monetary(string='Καθαρή Αξία', currency_field='currency_id')
    vat_amount = fields.Monetary(string='ΦΠΑ', currency_field='currency_id')
    vat_rate = fields.Float(string='Συντελεστής ΦΠΑ')
