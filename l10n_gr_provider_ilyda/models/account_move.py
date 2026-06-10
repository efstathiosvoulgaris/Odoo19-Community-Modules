# -*- coding: utf-8 -*-
"""ILYDA Y.PA.H.E.S. driver.

Implements the operations dispatched by l10n_gr_provider_base:
  _l10n_gr_prov_send_ilyda            POST /api/invoice
  _l10n_gr_prov_upload_pdf_ilyda      POST /api/invoice/upload/{invoiceId}
  _l10n_gr_prov_poll_b2g_status_ilyda GET  /api/invoice/status/{invoiceId}

API reference: ILYDA "Οδηγίες υλοποίησης eInvoicing" v1.0.6.
"""
import logging

import requests

from odoo import models, _
from odoo.exceptions import UserError
from odoo.addons.l10n_gr_edi.models.preferred_classification import (
    TYPES_WITH_VAT_CATEGORY_8,
    TYPES_WITH_VAT_EXEMPT,
    VALID_TAX_CATEGORY_MAP,
)

_logger = logging.getLogger(__name__)

ILYDA_PROD_BASE = 'https://vs.gr'
ILYDA_TEST_BASE = 'https://test.vs.gr'
TIMEOUT = 30

# UBL document type codes
UBL_INVOICE = '380'
UBL_CREDIT_NOTE = '381'


class IlydaClient:
    """Thin HTTP client for the ILYDA eInvoicing API."""

    def __init__(self, company):
        self.base = ILYDA_TEST_BASE if company.l10n_gr_prov_test_env else ILYDA_PROD_BASE
        self.auth_key = company.sudo().l10n_gr_prov_ilyda_auth_key
        self.username = company.sudo().l10n_gr_prov_ilyda_username
        self.password = company.sudo().l10n_gr_prov_ilyda_password
        if not self.auth_key:
            raise UserError(_(
                'ILYDA X-Auth-Key is not configured. '
                'Set it in Settings > Accounting > Greek E-Invoicing Provider.'))

    def _headers(self, json_content=True):
        headers = {'X-Auth-Key': self.auth_key}
        if json_content:
            headers['Content-Type'] = 'application/json'
        if self.username and self.password:
            headers['X-Auth-Username'] = self.username
            headers['X-Auth-Password'] = self.password
        return headers

    def submit_invoice(self, payload):
        resp = requests.post(
            f'{self.base}/api/invoice',
            json=payload, headers=self._headers(), timeout=TIMEOUT)
        return self._parse(resp)

    def upload_pdf(self, invoice_id, filename, pdf_bytes):
        resp = requests.post(
            f'{self.base}/api/invoice/upload/{invoice_id}',
            files={'FileUpload': (filename, pdf_bytes, 'application/pdf')},
            headers=self._headers(json_content=False), timeout=TIMEOUT)
        return self._parse(resp)

    def get_status(self, invoice_id):
        resp = requests.get(
            f'{self.base}/api/invoice/status/{invoice_id}',
            headers=self._headers(json_content=False), timeout=TIMEOUT)
        return self._parse(resp)

    @staticmethod
    def _parse(resp):
        try:
            data = resp.json()
        except ValueError:
            data = {}
        if not resp.ok and not data:
            raise UserError(_(
                'ILYDA API error %s: %s', resp.status_code, resp.text[:500]))
        return data


def _r2(amount):
    return round(amount or 0.0, 2)


class AccountMove(models.Model):
    _inherit = 'account.move'

    # ── Operations dispatched by the base module ─────────────────────────────

    def _l10n_gr_prov_send_ilyda(self):
        self.ensure_one()
        self._l10n_gr_prov_ilyda_validate()
        client = IlydaClient(self.company_id)
        payload = self._l10n_gr_prov_ilyda_build_payload()
        data = client.submit_invoice(payload)
        self._l10n_gr_prov_ilyda_handle_response(data)

    def _l10n_gr_prov_upload_pdf_ilyda(self):
        self.ensure_one()
        if not self.l10n_gr_prov_invoice_id:
            raise UserError(_('No provider invoice ID; submit the document first.'))
        client = IlydaClient(self.company_id)
        filename, pdf = self._l10n_gr_prov_get_pdf()
        data = client.upload_pdf(self.l10n_gr_prov_invoice_id, filename, pdf)
        fatal = [e for e in (data.get('errors') or []) if e.get('fatal')]
        if fatal:
            raise UserError(_(
                'ILYDA PDF upload failed: %s',
                '; '.join(f"{e.get('code')}: {e.get('defaultMessage')}" for e in fatal)))

    def _l10n_gr_prov_poll_b2g_status_ilyda(self):
        self.ensure_one()
        client = IlydaClient(self.company_id)
        data = client.get_status(self.l10n_gr_prov_invoice_id)
        status = data.get('status') or data.get('state') or str(data)[:200]
        if status and status != self.l10n_gr_prov_b2g_status:
            self.l10n_gr_prov_b2g_status = status
            self.message_post(body=_('B2G status update: %s', status))

    # ── Validation ────────────────────────────────────────────────────────────

    def _l10n_gr_prov_ilyda_validate(self):
        self.ensure_one()
        errors = []
        company_partner = self.company_id.partner_id
        if not self.company_id.vat:
            errors.append(_('Company VAT number is missing.'))
        if not self.l10n_gr_edi_inv_type:
            errors.append(_('myDATA Invoice Type is missing (set it in the myDATA tab).'))
        lines = self._l10n_gr_prov_ilyda_lines()
        if not lines:
            errors.append(_('The document has no product lines.'))
        for line in lines:
            line_label = line.name or line.product_id.display_name
            if not line.l10n_gr_edi_cls_category or not line.l10n_gr_edi_cls_type:
                errors.append(_(
                    'Line "%s": myDATA income classification (category/type) is missing.',
                    line_label))
            # VAT category is derived from the tax rate (as l10n_gr_edi does)
            tax = line.tax_ids[:1]
            if not tax:
                if self.l10n_gr_edi_inv_type not in TYPES_WITH_VAT_CATEGORY_8:
                    errors.append(_('Line "%s": no VAT tax is set.', line_label))
            elif int(tax.amount) not in VALID_TAX_CATEGORY_MAP:
                errors.append(_(
                    'Line "%s": tax rate %s%% is not a valid Greek VAT rate '
                    '(24, 13, 6, 17, 9, 4 or 0).', line_label, tax.amount))
            elif (
                int(tax.amount) == 0
                and self.l10n_gr_edi_inv_type not in TYPES_WITH_VAT_EXEMPT
                and self.l10n_gr_edi_inv_type not in TYPES_WITH_VAT_CATEGORY_8
                and not line.l10n_gr_edi_tax_exemption_category
            ):
                errors.append(_(
                    'Line "%s": 0%% VAT requires a Tax Exemption Category '
                    '(myDATA tab on the line).', line_label))
        if self.move_type == 'out_refund' and self.reversed_entry_id \
                and not self.reversed_entry_id.l10n_gr_prov_mark:
            errors.append(_(
                'The reversed invoice %s has no MARK; submit it first so the '
                'credit note can reference it.', self.reversed_entry_id.name))
        if self.l10n_gr_prov_b2g:
            if not self.l10n_gr_prov_contract_ref:
                errors.append(_('B2G documents require a Contract Reference (ΑΔΑΜ).'))
            if not self.l10n_gr_prov_budget_ref:
                errors.append(_('B2G documents require a Budget Identifier (ΑΔΑ/Ενάριθμος, BT-11).'))
            if not self.l10n_gr_prov_buyer_ref:
                errors.append(_('B2G documents require a Buyer Reference (BT-10). '
                                'Set the ΑΑΗΤ on the customer to default it.'))
            if not self.commercial_partner_id.vat:
                errors.append(_('B2G documents require the customer VAT number.'))
            for line in lines:
                if not line.product_id.l10n_gr_prov_cpv:
                    errors.append(_(
                        'Line "%s": CPV code is missing on the product (required for B2G).',
                        line.name or line.product_id.display_name))
        if not company_partner.zip or not company_partner.city:
            errors.append(_('Company address (city/ZIP) is incomplete.'))
        if errors:
            raise UserError('\n'.join(errors))

    def _l10n_gr_prov_ilyda_lines(self):
        return self.invoice_line_ids.filtered(
            lambda l: l.display_type == 'product')

    # ── Payload builder ───────────────────────────────────────────────────────

    @staticmethod
    def _ilyda_vat(vat, prefixed=True):
        """Return VAT in the requested form. ILYDA examples use the bare 9-digit
        number for AADE-related fields and the EL-prefixed one for EN16931."""
        vat = (vat or '').replace(' ', '').upper()
        bare = vat[2:] if vat.startswith('EL') or vat.startswith('GR') else vat
        return f'EL{bare}' if prefixed else bare

    def _l10n_gr_prov_ilyda_build_payload(self):
        self.ensure_one()
        company = self.company_id
        partner = self.commercial_partner_id
        lines = self._l10n_gr_prov_ilyda_lines()
        sign = 1  # amounts are sent positive for both invoices and credit notes

        # ── Lines, VAT breakdown buckets, classifications ────────────────────
        invoice_lines, row_types = [], []
        vat_buckets = {}      # (rate, aade_vat_category, exemption) -> [taxable, tax]
        cls_totals = {}       # (category, type) -> amount
        for number, line in enumerate(lines, start=1):
            net = _r2(sign * line.price_subtotal)
            vat_amount = _r2(sign * (line.price_total - line.price_subtotal))
            tax = line.tax_ids[:1]
            rate = tax.amount if tax else 0.0
            # Derive the myDATA VAT category from the tax rate, mirroring l10n_gr_edi
            if tax and self.l10n_gr_edi_inv_type not in TYPES_WITH_VAT_EXEMPT:
                aade_vat_cat = VALID_TAX_CATEGORY_MAP.get(int(rate), 7)
            else:
                aade_vat_cat = 8
            if aade_vat_cat == 7 and self.l10n_gr_edi_inv_type in TYPES_WITH_VAT_CATEGORY_8:
                aade_vat_cat = 8
            exemption = (
                line.l10n_gr_edi_tax_exemption_category
                if aade_vat_cat == 7 else None
            ) or None
            category_code = 'S' if rate else 'E'

            key = (rate, aade_vat_cat, exemption)
            bucket = vat_buckets.setdefault(key, [0.0, 0.0])
            bucket[0] += net
            bucket[1] += vat_amount

            cls_key = (line.l10n_gr_edi_cls_category, line.l10n_gr_edi_cls_type)
            cls_totals[cls_key] = _r2(cls_totals.get(cls_key, 0.0) + net)

            line_cls = [{
                'classificationCategory': line.l10n_gr_edi_cls_category,
                'classificationType': line.l10n_gr_edi_cls_type,
                'amount': f'{net:.2f}',
            }]
            line_vals = {
                'lineNumber': number,
                'invoicedQuantity': line.quantity,
                'netAmount': net,
                'itemInfo': {
                    'itemInfoName': (line.product_id.name or line.name or '')[:200],
                    'itemInfoDescription': (line.name or line.product_id.name or '')[:200],
                },
                'priceDetails': {
                    'itemNetPrice': _r2(line.price_unit * (1 - (line.discount or 0.0) / 100.0)),
                    'itemPriceBaseQuantity': 1,
                },
                'lineVatInfo': {
                    'vatAmount': vat_amount,
                    'vatRate': rate,
                    'vatCategoryCode': category_code,
                    'aadeVatData': {
                        'aadeVatCategory': aade_vat_cat,
                        'aadeVatExemptionCategory': exemption,
                    },
                },
            }
            # CPV classification (BT-158, scheme STI) — mandatory on B2G lines
            cpv = line.product_id.l10n_gr_prov_cpv
            if cpv:
                line_vals['itemClassificationIdentifiers'] = [{
                    'classificationIdentifier': cpv,
                    'classificationIdentifierScheme': 'STI',
                }]
            invoice_lines.append(line_vals)
            row_types.append({
                'lineNumber': number,
                'netValue': net,
                'vatAmount': vat_amount,
                'vatCategory': aade_vat_cat,
                'incomeClassification': line_cls,
            })

        vat_breakdowns = [{
            'categoryCode': 'S' if rate else 'E',
            'categoryRate': rate,
            'categoryTaxableAmount': _r2(taxable),
            'categoryTaxAmount': _r2(tax),
            'exemptionReasonCode': None,
            'exemptionReasonText': None,
            'aadeVatData': {
                'aadeVatCategory': aade_cat,
                'aadeVatExemptionCategory': exemption,
            },
        } for (rate, aade_cat, exemption), (taxable, tax) in vat_buckets.items()]

        income_classifications = [{
            'classificationCategory': cat,
            'classificationType': cls_type,
            'amount': f'{amount:.2f}',
        } for (cat, cls_type), amount in cls_totals.items()]

        # ── Totals ────────────────────────────────────────────────────────────
        total_net = _r2(sum(b[0] for b in vat_buckets.values()))
        total_vat = _r2(sum(b[1] for b in vat_buckets.values()))
        total_gross = _r2(total_net + total_vat)
        doc_total = {
            'invoiceLinesNetAmountSum': total_net,
            'invoiceTotalWithoutVat': total_net,
            'invoiceTotalVatAmount': total_vat,
            'invoiceTotalAmountWithVat': total_gross,
            'amountDueForPayment': total_gross,
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
        }

        # ── Seller ────────────────────────────────────────────────────────────
        company_partner = company.partner_id
        seller = {
            'sellerVatIdentifier': self._ilyda_vat(company.vat),
            'sellerName': company.name,
            'branch': company_partner.l10n_gr_edi_branch_number or 0,
            'sellerContact': {
                'sellerContactEmail': company.email or '',
                'sellerContactPhoneNumber': company.phone or '',
            },
            'sellerPostalAddress': {
                'sellerCountryCode': company_partner.country_id.code or 'GR',
                'sellerAddressLine1': company_partner.street or '',
                'sellerAddressLine2': company_partner.street2 or '',
                'sellerCity': company_partner.city or '',
                'sellerPostCode': company_partner.zip or '',
                'sellerCountrySubdivision': company_partner.state_id.name or '',
            },
        }

        # ── Buyer (B2B/B2G only; retail stays anonymous) ─────────────────────
        buyer = None
        if partner.vat:
            buyer = {
                'buyerVatIdentifier': self._ilyda_vat(partner.vat),
                'buyerTradingName': partner.name,
                'buyerPostalAddress': {
                    'buyerCountryCode': partner.country_id.code or 'GR',
                    'buyerAddressLine1': partner.street or '',
                    'buyerAddressLine2': partner.street2 or '',
                    'buyerCity': partner.city or '',
                    'buyerPostCode': partner.zip or '',
                    'buyerCountrySubdivision': partner.state_id.name or '',
                },
            }
            if partner.email:
                buyer['buyerContact'] = {'buyerContactEmail': partner.email}

        # ── Series / serial, same convention as l10n_gr_edi's myDATA XML ─────
        # 'INV/2026/00042' -> series 'INV_2026', serial '00042'
        name_parts = (self.name or '').split('/')
        series = '_'.join(name_parts[:-1]) or self.journal_id.code
        serial = name_parts[-1] or str(self.sequence_number or 0)

        # ── AADE block ────────────────────────────────────────────────────────
        aade_data = {
            'aadeInvoiceTypeCode': self.l10n_gr_edi_inv_type,
            'incomeClassifications': income_classifications,
            'invoiceRowTypes': row_types,
        }

        payload = {
            'b2g': bool(self.l10n_gr_prov_b2g),
            'invoiceTypeCode': UBL_CREDIT_NOTE if self.move_type == 'out_refund' else UBL_INVOICE,
            'seriesNumber': series,
            'serialNumber': serial,
            'invoiceIssueDate': f'{self.invoice_date}T00:00:00',
            'invoiceCurrencyCode': self.currency_id.name or 'EUR',
            'seller': seller,
            'buyer': buyer,
            'invoiceLines': invoice_lines,
            'vatBreakdowns': vat_breakdowns,
            'docTotal': doc_total,
            'aadeData': aade_data,
        }

        # Payment method (myDATA codes '1'..'7' match ILYDA paymentMethods.type)
        method = self.l10n_gr_edi_payment_method
        payload['paymentMethods'] = [{
            'type': int(method) if method and method.isdigit() else 5,  # default: on credit
            'amount': total_gross,
        }]

        # Credit note: reference the reversed invoice
        # Format: MARK|dd/mm/yyyy|branch|aadeType|series|serial
        if self.move_type == 'out_refund' and self.reversed_entry_id \
                and self.reversed_entry_id.l10n_gr_prov_mark:
            origin = self.reversed_entry_id
            origin_parts = (origin.name or '').split('/')
            origin_series = '_'.join(origin_parts[:-1]) or origin.journal_id.code
            origin_serial = origin_parts[-1] or str(origin.sequence_number or 0)
            reference = '|'.join([
                origin.l10n_gr_prov_mark,
                origin.invoice_date.strftime('%d/%m/%Y') if origin.invoice_date else '',
                str(company_partner.l10n_gr_edi_branch_number or 0),
                origin.l10n_gr_edi_inv_type or '',
                origin_series,
                origin_serial,
            ])
            payload['precedingInvoices'] = [{
                'precedingInvoiceReference': reference,
                'precedingInvoiceIssueDate': f'{origin.invoice_date}T00:00:00',
            }]

        # B2G references and routing
        if self.l10n_gr_prov_b2g:
            project_ref = None
            if self.l10n_gr_prov_budget_ref:
                project_ref = f'{self.l10n_gr_prov_budget_type or "1"}|{self.l10n_gr_prov_budget_ref}'
            payload.update({
                'contractReference': self.l10n_gr_prov_contract_ref or None,
                'projectReference': project_ref,
                'buyerReference': self.l10n_gr_prov_buyer_ref or None,
                'purchaseOrderReference': self.l10n_gr_prov_purchase_order_ref or None,
            })
            # Peppol routing: scheme 9933 = Greek VAT (bare, no country prefix)
            if buyer:
                bare_vat = self._ilyda_vat(partner.vat, prefixed=False)
                buyer['buyerName'] = partner.name
                buyer['buyerElectronicAddress'] = {
                    'buyerElectronicAddress': f'9933:{bare_vat}',
                    'buyerElectronicAddressSchemeIdentifier': '9933',
                }
            # Delivery details (BT-70/75/77/78) from the shipping address
            ship = self.partner_shipping_id or partner
            if ship:
                payload['delivery'] = {
                    'partyName': ship.name or partner.name,
                    'deliveryAddress': {
                        'deliveryAddressLine1': ship.street or '',
                        'deliveryAddressLine2': ship.street2 or '',
                        'deliveryCity': ship.city or '',
                        'deliveryPostCode': ship.zip or '',
                        'deliveryCountryCode': ship.country_id.code or 'GR',
                    },
                }

        return payload

    # ── Response handling ─────────────────────────────────────────────────────

    @staticmethod
    def _l10n_gr_prov_ilyda_format_error(error):
        text = f"{error.get('code')}: {error.get('defaultMessage')}"
        fields = error.get('errorFields') or []
        if fields:
            details = ', '.join(
                f"{f.get('field')}={f.get('value')}" for f in fields)
            text += f' [{details}]'
        return text

    def _l10n_gr_prov_ilyda_handle_response(self, data):
        self.ensure_one()
        marking = data.get('invoiceMarking') or {}
        errors = data.get('errors') or []
        fatal = [e for e in errors if e.get('fatal')]
        non_fatal = [e for e in errors if not e.get('fatal')]

        if non_fatal:
            self.message_post(body=_(
                'ILYDA non-fatal warnings: %s',
                '; '.join(self._l10n_gr_prov_ilyda_format_error(e) for e in non_fatal)))

        if fatal or not marking.get('mark'):
            details = '; '.join(
                self._l10n_gr_prov_ilyda_format_error(e) for e in (fatal or errors)
            ) or _('No marking returned by the provider.')
            raise UserError(_('ILYDA rejected the document: %s', details))

        self.write({
            'l10n_gr_prov_mark': marking.get('mark'),
            'l10n_gr_prov_invoice_id': marking.get('invoiceId'),
            'l10n_gr_prov_verification_hash': marking.get('verificationHash'),
            'l10n_gr_prov_invoice_identifier': marking.get('invoiceIdentifier'),
            'l10n_gr_prov_qr_url': marking.get('qrCode'),
            'l10n_gr_prov_provider_url': marking.get('providerUrl'),
            'l10n_gr_prov_previously_submitted': bool(marking.get('previouslySubmitted')),
        })
