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
"""
import logging

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


class L10nGrProvCateringOrder(models.Model):
    _name = 'l10n.gr.prov.catering.order'
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
        ('error', 'Σφάλμα'),
    ], default='draft', required=True, copy=False, string='Κατάσταση')
    mark = fields.Char(string='MARK', copy=False, index=True)
    invoice_id_provider = fields.Char(string='Provider Invoice ID', copy=False)
    verification_hash = fields.Char(string='Συμβ. Αυθεντικοποίησης', copy=False)
    qr_url = fields.Char(string='QR URL', copy=False)
    error_message = fields.Text(string='Σφάλμα', copy=False)
    series = fields.Char(string='Σειρά', default='ΔΠΕ')
    serial = fields.Char(string='Αριθμός', copy=False)

    @api.depends('line_ids.net_value', 'line_ids.vat_amount')
    def _compute_amounts(self):
        for order in self:
            order.amount_net = sum(order.line_ids.mapped('net_value'))
            order.amount_vat = sum(order.line_ids.mapped('vat_amount'))
            order.amount_total = order.amount_net + order.amount_vat

    @api.depends('table_aa', 'serial', 'mark')
    def _compute_display_name(self):
        for order in self:
            order.display_name = _(
                'ΔΠΕ %(serial)s — Τραπέζι %(table)s',
                serial=order.serial or '—', table=order.table_aa or '—')

    # ── Issue ────────────────────────────────────────────────────────────────

    @api.model
    def l10n_gr_prov_issue_note(self, vals):
        """Create and transmit one order note. Called from the POS when a round
        is sent to the kitchen.

        `vals`: config_id, table_aa, pos_order_uuid, lines
        [{name, quantity, net, vat_amount, vat_rate}]. Returns a dict the POS
        can show on the ticket; never raises, so a provider failure cannot
        block service.
        """
        lines = [line for line in (vals.get('lines') or [])
                 if line.get('quantity') and (line.get('net') or 0) >= 0]
        if not lines:
            return {}
        config = self.env['pos.config'].browse(vals['config_id'])
        # The front end asks on every round; the server decides. A till that is
        # not wired to the provider issues nothing.
        if not config.l10n_gr_prov_enabled:
            return {}
        order = self.create({
            'company_id': config.company_id.id,
            'config_id': config.id,
            'session_id': config.current_session_id.id,
            'table_aa': vals.get('table_aa') or '—',
            'pos_order_uuid': vals.get('pos_order_uuid'),
            'serial': self.env['ir.sequence'].next_by_code(
                'l10n.gr.prov.catering.order') or False,
            'line_ids': [(0, 0, {
                'name': (line.get('name') or '')[:200],
                'quantity': line['quantity'],
                'net_value': _r2(line.get('net') or 0),
                'vat_amount': _r2(line.get('vat_amount') or 0),
                'vat_rate': line.get('vat_rate') or 0,
            }) for line in lines],
        })
        order._l10n_gr_prov_send()
        return order._l10n_gr_prov_ticket_values()

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
            order._l10n_gr_prov_send()

    # ── Payload ──────────────────────────────────────────────────────────────

    def _l10n_gr_prov_build_payload(self):
        """The 8.6 body. Deliberately compact: an order note carries no buyer,
        no extra taxes and no E3 classification."""
        self.ensure_one()
        company = self.company_id
        company_partner = company.partner_id
        Move = self.env['account.move']

        invoice_lines, row_types, vat_buckets = [], [], {}
        for number, line in enumerate(self.line_ids, start=1):
            net, vat = _r2(line.net_value), _r2(line.vat_amount)
            rate = line.vat_rate or 0
            vat_category = VAT_CATEGORY_MAP.get(int(rate), 7)
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
                    'vatCategoryCode': 'S' if rate else 'E',
                },
            })

        total_net = _r2(sum(b[0] for b in vat_buckets.values()))
        total_vat = _r2(sum(b[1] for b in vat_buckets.values()))
        total_gross = _r2(total_net + total_vat)

        return {
            'b2g': False,
            'selfPricing': False,
            'vatPaidByBuyer': False,
            'invoiceTypeCode': '380',
            'seriesNumber': self.series or 'ΔΠΕ',
            'serialNumber': self.serial or '1',
            'invoiceIssueDate': f'{fields.Date.context_today(self)}T00:00:00',
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
                'categoryCode': 'S' if rate else 'E',
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
            },
        }


class L10nGrProvCateringOrderLine(models.Model):
    _name = 'l10n.gr.prov.catering.order.line'
    _description = 'Είδος Δελτίου Παραγγελίας Εστίασης'

    order_id = fields.Many2one(
        'l10n.gr.prov.catering.order', required=True, ondelete='cascade', index=True)
    currency_id = fields.Many2one(related='order_id.currency_id')
    name = fields.Char(string='Είδος', required=True)
    quantity = fields.Float(string='Ποσότητα', default=1.0)
    net_value = fields.Monetary(string='Καθαρή Αξία', currency_field='currency_id')
    vat_amount = fields.Monetary(string='ΦΠΑ', currency_field='currency_id')
    vat_rate = fields.Float(string='Συντελεστής ΦΠΑ')
