# -*- coding: utf-8 -*-
"""Ψηφιακή Διακίνηση — AADE myDATA dispatch-lifecycle client (v2.0.1).

Issue/cancel of ΔΑ goes through the provider (ILYDA). The lifecycle events
(status, confirm receipt, reject) are AADE-direct endpoints using the myDATA
ERP credentials that core l10n_gr_edi already stores on the company
(l10n_gr_edi_aade_id / l10n_gr_edi_aade_key / l10n_gr_edi_test_env).

Schemas: mydata2.0.1/v2.0.1 XSDs (ConfirmDeliveryOutcome, RejectDeliveryNote,
GetDeliveryStatusResponse, TransportTypes).
Roles implemented: issuer (status/history) + recipient (confirm/reject).
RegisterTransfer (carrier role) intentionally not built — third-party carriers
make that call themselves.
"""
import logging
import re

import requests
from lxml import etree

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from .gr_mydata import TYPES_DISPATCH

_logger = logging.getLogger(__name__)

DELIVERY_STATES = [
    ('Registered',         'Καταχωρημένο'),
    ('InTransit',          'Σε Διακίνηση'),
    ('DeliveredByCarrier', 'Παραδόθηκε από Μεταφορέα'),
    ('Completed',          'Ολοκληρωμένο'),
    ('Rejected',           'Απορρίφθηκε'),
    ('Cancelled',          'Ακυρωμένο'),
    ('FailedDelivery',     'Αποτυχία Παράδοσης'),
]
DELIVERY_STATES_OPEN = ('Registered', 'InTransit', 'DeliveredByCarrier')


def _aade_dispatch_request(company, endpoint, xml_body=None, params=None, method='POST'):
    """Call an AADE dispatch endpoint; return the lxml root or raise UserError."""
    if not company.l10n_gr_edi_aade_id or not company.l10n_gr_edi_aade_key:
        raise UserError(_(
            'Συμπληρώστε τα διαπιστευτήρια myDATA (AADE User ID / Subscription Key) '
            'στις ρυθμίσεις Λογιστικής της εταιρείας.'))
    url = (f'https://mydataapidev.aade.gr/{endpoint}'
           if company.l10n_gr_edi_test_env
           else f'https://mydatapi.aade.gr/myDATA/{endpoint}')
    headers = {
        'aade-user-id': company.l10n_gr_edi_aade_id,
        'ocp-apim-subscription-key': company.l10n_gr_edi_aade_key,
    }
    _logger.info('AADE dispatch %s %s params=%s', method, url, params)
    try:
        if method == 'GET':
            resp = requests.get(url, params=params, headers=headers, timeout=30)
        else:
            resp = requests.post(url, data=xml_body, params=params, headers=headers, timeout=30)
        if resp.status_code == 404:
            raise UserError(_(
                'Το ΜΑΡΚ δεν βρέθηκε στο περιβάλλον AADE myDATA (%s). '
                'Προσοχή: ΜΑΡΚ που εκδόθηκαν μέσω του test περιβάλλοντος του παρόχου '
                'δεν υπάρχουν στο dev περιβάλλον της ΑΑΔΕ.',
                'dev' if company.l10n_gr_edi_test_env else 'production'))
        resp.raise_for_status()
        _logger.info('AADE dispatch response: %s', resp.text[:2000])
        return etree.fromstring(resp.content)
    except requests.RequestException as err:
        raise UserError(_('Σφάλμα επικοινωνίας με AADE myDATA: %s', err))
    except etree.XMLSyntaxError as err:
        raise UserError(_('Μη αναγνώσιμη απάντηση AADE: %s', err))


def _collect_errors(root):
    """Business errors from a ResponseDoc (statusCode != Success)."""
    errors = []
    for r in root.iter('response'):
        status = r.findtext('statusCode')
        if status and status != 'Success':
            found = [f"[{e.findtext('code')}] {e.findtext('message')}"
                     for e in r.iter('error')]
            errors.extend(found or [status])
    return errors


def _parse_dt(value):
    """xs:dateTime → naive datetime string Odoo accepts (tz/millis stripped)."""
    if not value:
        return False
    value = re.sub(r'(\.\d+)?(Z|[+-]\d{2}:?\d{2})?$', '', value.strip())
    return value.replace('T', ' ')[:19] or False


class L10nGrProvDeliveryEvent(models.Model):
    _name = 'l10n.gr.prov.delivery.event'
    _description = 'myDATA Γεγονός Κύκλου Ζωής Διακίνησης'
    _order = 'event_timestamp desc, id desc'

    move_id = fields.Many2one('account.move', required=True, ondelete='cascade', index=True)
    event_type = fields.Char('Γεγονός')
    event_timestamp = fields.Datetime('Χρονοσφραγίδα')
    actor_vat = fields.Char('ΑΦΜ Ενεργούντος')
    mark = fields.Char('MARK Γεγονότος')
    details = fields.Char('Λεπτομέρειες')


class L10nGrProvVehicle(models.Model):
    """Reusable vehicle plates for dispatch documents (Οχήματα)."""
    _name = 'l10n.gr.prov.vehicle'
    _description = 'Όχημα Διακίνησης'
    _order = 'name'

    name = fields.Char(string='Αριθμός Μεταφορικού Μέσου', size=50, required=True)
    company_id = fields.Many2one(
        'res.company', default=lambda self: self.env.company)

    _sql_constraints = [
        ('name_company_uniq', 'unique(name, company_id)',
         'Το όχημα υπάρχει ήδη.'),
    ]


class AccountMove(models.Model):
    _inherit = 'account.move'

    l10n_gr_prov_delivery_status = fields.Selection(
        DELIVERY_STATES, string='Κατάσταση Διακίνησης', copy=False, tracking=True)
    l10n_gr_prov_delivery_event_ids = fields.One2many(
        'l10n.gr.prov.delivery.event', 'move_id', string='Ιστορικό Διακίνησης')
    l10n_gr_prov_is_dispatch = fields.Boolean(
        compute='_compute_l10n_gr_prov_is_dispatch')
    # pure dispatch note (9.x/10.x, not a combined ΤΔΑ/ΠΤΔΑ): carries no values
    l10n_gr_prov_is_dispatch_only = fields.Boolean(
        compute='_compute_l10n_gr_prov_is_dispatch')
    # Planned dispatch data (§5.3 v2.0.1 — estimates; actuals come via RegisterTransfer)
    l10n_gr_prov_dispatch_datetime = fields.Datetime(
        string='Έναρξη Αποστολής', copy=False)
    l10n_gr_prov_vehicle_id = fields.Many2one(
        'l10n.gr.prov.vehicle', string='Αριθμός Μεταφορικού Μέσου', copy=False,
        check_company=True)
    l10n_gr_prov_start_shipping_branch = fields.Char(
        string='Εγκατάσταση Έναρξης (Εκδότη)', copy=False,
        help='Αριθμός εγκατάστασης ΑΑΔΕ. Κενό = έδρα.')
    l10n_gr_prov_complete_shipping_branch = fields.Char(
        string='Εγκατάσταση Ολοκλήρωσης (Λήπτη)', copy=False,
        help='Αριθμός εγκατάστασης ΑΑΔΕ. Κενό = έδρα.')
    l10n_gr_prov_other_move_purpose = fields.Char(
        string='Τίτλος Λοιπής Αιτίας Διακίνησης', copy=False,
        help='Συμπληρώνεται μόνο όταν ο Σκοπός Διακίνησης είναι 19 - Λοιπές Διακινήσεις.')
    # Αντίστροφη Διακίνηση (§5.3, only accepted for type 9.3): the recipient
    # issues the ΔΑ that the supplier did not.
    l10n_gr_prov_reverse_delivery = fields.Boolean(
        string='Αντίστροφη Διακίνηση', copy=False)
    l10n_gr_prov_reverse_purpose = fields.Selection(
        selection=[
            ('1', '1 - Μη Υπόχρεος Έκδοσης'),
            ('2', '2 - Άρνηση Έκδοσης / Εκ Παραδρομής Μη Έκδοση'),
            ('3', '3 - Ενδοκοινοτική Απόκτηση'),
            ('4', '4 - Απόκτηση Τρίτη Χώρα'),
            ('5', '5 - Αντιστροφή Υποχρέωσης'),
        ],
        string='Αιτία Αντίστροφης Διακίνησης', copy=False,
        help='Αιτία έκδοσης αντίστροφης διακίνησης (§8.21). Μόνο για τύπο 9.3.')
    # Δελτίο Ποσοτικής Παραλαβής (10.1/10.2). AADE code — not enumerated in the
    # provided ILYDA/myDATA v2.0.1 docs, so kept as a free numeric code.
    # ponytail: Char not Selection — no sourced enum to model; user sets the code.
    l10n_gr_prov_receiving_purpose = fields.Char(
        string='Σκοπός Παραλαβής', size=2, copy=False, default='1',
        help='Κωδικός σκοπού ποσοτικής παραλαβής (receivingNotePurpose). '
             'Υποχρεωτικό μόνο για τύπους 10.1/10.2.')

    @api.depends('journal_id.l10n_gr_edi_inv_type_default',
                 'journal_id.l10n_gr_prov_delivery_note')
    def _compute_l10n_gr_prov_is_dispatch(self):
        for move in self:
            is_type = move.journal_id.l10n_gr_edi_inv_type_default in TYPES_DISPATCH
            delivery_note = move.journal_id.l10n_gr_prov_delivery_note
            move.l10n_gr_prov_is_dispatch = is_type or delivery_note
            move.l10n_gr_prov_is_dispatch_only = is_type and not delivery_note

    @api.onchange('journal_id')
    def _onchange_l10n_gr_prov_move_purpose_default(self):
        if self.l10n_gr_prov_is_dispatch:
            if not self.l10n_gr_prov_move_purpose:
                # ΠΤΔΑ (credit + dispatch) → 5 Επιστροφή, otherwise 1 Πώληση
                self.l10n_gr_prov_move_purpose = (
                    '5' if self.move_type == 'out_refund' else '1')
            # dispatch start defaults to "now" until marked
            if not self.l10n_gr_prov_mark:
                self.l10n_gr_prov_dispatch_datetime = fields.Datetime.now()

    # ── ΔΑ follow-up documents (correlation routine) ──────────────────────────
    def _l10n_gr_prov_copy_correlated(self, inv_type, extra_defaults=None):
        """Copy this marked ΔΑ to the journal of `inv_type`, correlated to it."""
        self.ensure_one()
        if not self.l10n_gr_prov_mark:
            raise UserError(_('Το %s δεν έχει MARK — στείλτε το πρώτα.', self.name))
        journal = self.env['account.journal'].search([
            ('company_id', '=', self.company_id.id),
            ('type', '=', 'sale'),
            ('l10n_gr_edi_inv_type_default', '=', inv_type),
            ('l10n_gr_prov_delivery_note', '=', False),
        ], limit=1)
        if not journal:
            raise UserError(_(
                'Δεν βρέθηκε ημερολόγιο πωλήσεων με τύπο myDATA %s.', inv_type))
        new_move = self.copy(default={
            'journal_id': journal.id,
            'invoice_date': fields.Date.context_today(self),
            'l10n_gr_edi_correlation_id': self.id,
            # copy() keeps the stored myDATA type of the source — force the target's
            'l10n_gr_edi_inv_type': inv_type,
            **(extra_defaults or {}),
        })
        # copy() keeps the source classifications (e.g. category3 from a ΔΑ) —
        # rederive them for the target document type
        product_lines = new_move.invoice_line_ids.filtered(
            lambda l: l.display_type == 'product' and l.product_id)
        product_lines.write({
            'l10n_gr_prov_cls_category': False, 'l10n_gr_prov_cls_type': False})
        product_lines._onchange_l10n_gr_prov_cls_from_product()
        # ΔΑ lines default to 0 — re-price from the product on the invoice
        if inv_type == '1.1':
            product_lines._compute_price_unit()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': new_move.id,
            'view_mode': 'form',
        }

    def action_l10n_gr_prov_create_invoice(self):
        """ΔΑ → ΤΙΜ (1.1) referencing the ΔΑ MARK in correlatedInvoices."""
        return self._l10n_gr_prov_copy_correlated('1.1')

    def action_l10n_gr_prov_create_reverse(self):
        """ΔΑ → Αντίστροφη Διακίνηση: a 9.3 ΔΑ with reverseDeliveryNote=true
        (the recipient issues the note the supplier did not, §5.3/§8.21)."""
        return self._l10n_gr_prov_copy_correlated('9.3', {
            'l10n_gr_prov_reverse_delivery': True,
            'l10n_gr_prov_reverse_purpose': '1',
        })

    def action_l10n_gr_prov_refresh_delivery_status(self):
        for move in self:
            if not move.l10n_gr_prov_mark:
                raise UserError(_(
                    'Το %s δεν έχει MARK — στείλτε το πρώτα στον πάροχο.', move.name))
            root = _aade_dispatch_request(
                move.company_id, 'GetDeliveryNoteStatus',
                params={'mark': move.l10n_gr_prov_mark}, method='GET')
            status = root.findtext('.//status')
            events = []
            for ev in root.iter('lifecycleHistory'):
                bits = []
                td = ev.find('transportDetails')
                if td is not None:
                    bits.append('Μεταφορά: %s / ΑΦΜ %s' % (
                        td.findtext('vehicleNumber') or '—',
                        td.findtext('carrierVatNumber') or '—'))
                od = ev.find('outcomeDetails')
                if od is not None:
                    bits.append('Αποτέλεσμα: %s' % (od.findtext('outcome') or '—'))
                rd = ev.find('rejectionDetails')
                if rd is not None:
                    bits.append('Απόρριψη: %s' % (rd.findtext('reason') or '—'))
                events.append((0, 0, {
                    'event_type': ev.findtext('eventType'),
                    'event_timestamp': _parse_dt(ev.findtext('eventTimestamp')),
                    'actor_vat': ev.findtext('actorVat'),
                    'mark': ev.findtext('mark'),
                    'details': ' | '.join(bits) or False,
                }))
            move.l10n_gr_prov_delivery_event_ids.unlink()
            move.write({
                'l10n_gr_prov_delivery_status':
                    status if status in dict(DELIVERY_STATES) else False,
                'l10n_gr_prov_delivery_event_ids': events,
            })

    @api.model
    def _l10n_gr_prov_cron_poll_delivery(self):
        """Poll AADE for open dispatch notes (called by scheduled job)."""
        moves = self.search([
            ('state', '=', 'posted'),
            ('l10n_gr_prov_mark', '!=', False),
            '|',
            ('journal_id.l10n_gr_edi_inv_type_default', 'in', list(TYPES_DISPATCH)),
            ('journal_id.l10n_gr_prov_delivery_note', '=', True),
            '|',
            ('l10n_gr_prov_delivery_status', 'in', list(DELIVERY_STATES_OPEN)),
            ('l10n_gr_prov_delivery_status', '=', False),
        ], limit=50)
        for move in moves:
            try:
                with self.env.cr.savepoint():
                    move.action_l10n_gr_prov_refresh_delivery_status()
            except UserError as err:
                _logger.warning('Delivery poll failed for %s: %s', move.name, err)


class L10nGrProvDeliveryWizard(models.TransientModel):
    """Recipient actions on an incoming ΔΑ: confirm receipt or reject."""
    _name = 'l10n.gr.prov.delivery.wizard'
    _description = 'Παραλαβή / Απόρριψη Δελτίου Αποστολής'

    action = fields.Selection([
        ('confirm', 'Επιβεβαίωση Παραλαβής'),
        ('reject', 'Απόρριψη'),
    ], string='Ενέργεια', required=True, default='confirm')
    qr_url = fields.Char(
        'QR URL', help='Το URL του QR code του Δελτίου Αποστολής (σκανάρετε ή επικολλήστε).')
    invoice_mark = fields.Char(
        'MARK Παραστατικού', help='Εναλλακτικά του QR URL — μόνο για απόρριψη.')
    outcome = fields.Selection([
        ('FULL', 'Πλήρης Παράδοση'),
        ('PARTIAL', 'Μερική Παράδοση'),
        ('NONE', 'Καμία Παράδοση'),
    ], string='Αποτέλεσμα', default='FULL')
    delivered_without_recipient = fields.Boolean('Παράδοση χωρίς παρουσία παραλήπτη')
    rejection_reason = fields.Char('Αιτιολογία Απόρριψης', size=150)

    def action_send(self):
        self.ensure_one()
        company = self.env.company
        if self.action == 'confirm':
            if not self.qr_url:
                raise UserError(_('Το QR URL είναι υποχρεωτικό για την επιβεβαίωση παραλαβής.'))
            root = etree.Element('ConfirmDeliveryOutcomeRequest')
            etree.SubElement(root, 'qrUrl').text = self.qr_url
            etree.SubElement(root, 'outcome').text = self.outcome
            if self.delivered_without_recipient:
                etree.SubElement(root, 'deliveredWithoutRecipient').text = 'true'
            endpoint = 'ConfirmDeliveryOutcome'
        else:
            if not self.qr_url and not self.invoice_mark:
                raise UserError(_('Δώστε QR URL ή MARK παραστατικού.'))
            root = etree.Element('RejectDeliveryNoteRequest')
            if self.qr_url:
                etree.SubElement(root, 'qrUrl').text = self.qr_url
            else:
                etree.SubElement(root, 'invoiceMark').text = self.invoice_mark
            if self.rejection_reason:
                etree.SubElement(root, 'rejectionReason').text = self.rejection_reason
            endpoint = 'RejectDeliveryNote'

        xml_body = etree.tostring(root, xml_declaration=True, encoding='UTF-8')
        resp = _aade_dispatch_request(company, endpoint, xml_body=xml_body)
        errors = _collect_errors(resp)
        if errors:
            raise UserError(_('Η AADE απέρριψε το αίτημα:\n%s', '\n'.join(errors)))
        mark = (resp.findtext('.//deliveryOutcomeMark')
                or resp.findtext('.//rejectMark') or '—')
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'title': _('Επιτυχής καταχώρηση'),
                'message': _('Η δήλωση καταχωρήθηκε στην AADE (MARK: %s).', mark),
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }
