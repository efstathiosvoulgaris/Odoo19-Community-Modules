# -*- coding: utf-8 -*-
"""ILYDA Y.PA.H.E.S. driver.

Implements the operations dispatched by l10n_gr_provider_base:
  _l10n_gr_prov_send_ilyda            POST /api/invoice
  _l10n_gr_prov_upload_pdf_ilyda      POST /api/invoice/upload/{invoiceId}
  _l10n_gr_prov_poll_b2g_status_ilyda GET  /api/invoice/status/{invoiceId}

API reference: ILYDA "Οδηγίες υλοποίησης eInvoicing" v1.0.6.
"""
import logging
import unicodedata

import requests

from odoo import fields, models, _
from odoo.exceptions import UserError
from odoo.addons.l10n_gr_provider_base.models.gr_mydata import (
    VAT_CATEGORY_MAP,
    TYPES_NO_BUYER,
    TYPES_NO_VAT,
    TYPES_NO_CLASSIFICATION,
    TYPES_CREDIT,
    TYPES_NEED_CORRELATED,
    PAYMENT_METHOD_MAP,
    PROVIDER_SUBMITTABLE_TYPES,
    TYPES_DISPATCH,
    MOVE_PURPOSE_NOT_SENDABLE,
    WITHHOLDING_CATEGORY_SELECTION,
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
        self.username = company.sudo().l10n_gr_prov_ilyda_username
        self.password = company.sudo().l10n_gr_prov_ilyda_password
        if not self.username or not self.password:
            raise UserError(_(
                'ILYDA credentials are not configured. '
                'Set Username and Password in Settings > Accounting > Greek E-Invoicing Provider.'))
        self._auth = (self.username, self.password)

    def _headers(self, json_content=True):
        headers = {}
        if json_content:
            headers['Content-Type'] = 'application/json'
        return headers

    def submit_invoice(self, payload):
        resp = requests.post(
            f'{self.base}/api/invoice',
            json=payload, headers=self._headers(), auth=self._auth, timeout=TIMEOUT)
        return self._parse(resp)

    def upload_pdf(self, invoice_id, filename, pdf_bytes):
        resp = requests.post(
            f'{self.base}/api/invoice/upload/{invoice_id}',
            files={'FileUpload': (filename, pdf_bytes, 'application/pdf')},
            headers=self._headers(json_content=False), auth=self._auth, timeout=TIMEOUT)
        return self._parse(resp)

    def get_status(self, invoice_id):
        resp = requests.get(
            f'{self.base}/api/invoice/status/{invoice_id}',
            headers=self._headers(json_content=False), auth=self._auth, timeout=TIMEOUT)
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


def _ascii_safe(text):
    """Transliterate Greek to ASCII. ponytail: kept as a fallback — series is now
    sent as Greek (AADE allows it); rewrap the series fields with this if ILYDA
    ever rejects Greek."""
    _GR = 'ΑΒΓΔΕΖΗΘΙΚΛΜΝΞΟΠΡΣΤΥΦΧΨΩαβγδεζηθικλμνξοπρστυφχψω'
    _LA = 'ABGDEZHQIKLMNXOPRSTYFCPWabgdezhqiklmnxoprstyfcpw'
    _GR_TO_LATIN = str.maketrans(_GR, _LA)
    text = (text or '').translate(_GR_TO_LATIN)
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode()
    return text


def _vat_category(tax, inv_type):
    """Return (aade_vat_category_int, en16931_category_code) for a tax line."""
    if not tax or inv_type in TYPES_NO_VAT:
        return 8, 'O'
    rate = int(tax.amount)
    aade_cat = VAT_CATEGORY_MAP.get(rate, 7)
    # category 7 = 0% with exemption reason → use 'E' (exempt) in EN16931
    code = 'E' if aade_cat == 7 else ('S' if rate else 'E')
    return aade_cat, code


class AccountMove(models.Model):
    _inherit = 'account.move'

    # ── Operations dispatched by the base module ─────────────────────────────

    def _l10n_gr_prov_send_ilyda(self):
        self.ensure_one()
        self._l10n_gr_prov_ilyda_validate()
        client = IlydaClient(self.company_id)
        payload = self._l10n_gr_prov_ilyda_build_payload()
        _logger.info('ILYDA submit payload for %s: %s', self.name, payload)
        data = client.submit_invoice(payload)
        _logger.info('ILYDA raw response for %s: %s', self.name, data)
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

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _l10n_gr_prov_ilyda_inv_type(self):
        """Return the effective AADE invoice type for this document.

        For credit notes the journal default is always wrong (it carries the
        forward invoice type, e.g. 1.1).  Core l10n_gr_edi sets 5.1/5.2
        correctly but our journal-default override in account_move_inv_type.py
        clobbers it, and the stored value can't be trusted.  Derive it here
        from move_type directly so the payload is always correct.
        """
        self.ensure_one()
        if self.move_type == 'out_refund':
            return '5.1' if self.reversed_entry_id else '5.2'
        return self.journal_id.l10n_gr_edi_inv_type_default or self.l10n_gr_edi_inv_type

    # ── Validation ────────────────────────────────────────────────────────────

    def _l10n_gr_prov_ilyda_validate(self):
        self.ensure_one()
        errors = []
        company_partner = self.company_id.partner_id
        inv_type = self._l10n_gr_prov_ilyda_inv_type()
        if not self.company_id.vat:
            errors.append(_('Company VAT number is missing.'))
        if not inv_type:
            errors.append(_('myDATA Invoice Type is missing (set it on the E-Invoicing Provider tab).'))
        elif inv_type not in PROVIDER_SUBMITTABLE_TYPES:
            errors.append(_(
                'Invoice type %s cannot be submitted through the e-invoicing provider '
                '(only 1.1–11.5 are allowed). Use an accounting/ERP journal instead.',
                inv_type))
        if ((inv_type in TYPES_DISPATCH or self.journal_id.l10n_gr_prov_delivery_note)
                and self.l10n_gr_prov_move_purpose in MOVE_PURPOSE_NOT_SENDABLE):
            errors.append(_(
                'Ο Σκοπός Διακίνησης %s δεν γίνεται δεκτός από το myDATA στην τρέχουσα '
                'έκδοση (§8.14) — επιλέξτε άλλον σκοπό.',
                self.l10n_gr_prov_move_purpose))
        for branch in (self.l10n_gr_prov_start_shipping_branch,
                       self.l10n_gr_prov_complete_shipping_branch):
            if branch and not branch.isdigit():
                errors.append(_(
                    'Η εγκατάσταση διακίνησης "%s" πρέπει να είναι αριθμός '
                    '(κωδικός εγκατάστασης ΑΑΔΕ).', branch))
        # Payment lines must cover the payable exactly (tips are on top)
        if self.l10n_gr_prov_payment_ids and inv_type not in TYPES_DISPATCH:
            paid = sum(self.l10n_gr_prov_payment_ids.mapped('amount'))
            payable = self._l10n_gr_prov_payable()
            if abs(paid - payable) > 0.01:
                errors.append(_(
                    'Οι Τρόποι Πληρωμής αθροίζουν %(paid).2f αλλά το πληρωτέο '
                    'είναι %(due).2f — διορθώστε τα ποσά στην καρτέλα '
                    'myDATA Φόροι & Πληρωμές.', paid=paid, due=payable))
        lines = self._l10n_gr_prov_ilyda_lines()
        if not lines:
            errors.append(_('The document has no product lines.'))
        # Dispatch types (9.x/10.x) classify with category3 only, no E3 code.
        no_cls = inv_type in TYPES_NO_CLASSIFICATION or inv_type in TYPES_DISPATCH
        no_vat = inv_type in TYPES_NO_VAT
        for line in lines:
            line_label = line.name or line.product_id.display_name
            if not no_cls and (not line.l10n_gr_prov_cls_category or not line.l10n_gr_prov_cls_type):
                errors.append(_(
                    'Line "%s": myDATA income classification (category + E3 type) is missing.',
                    line_label))
            tax = line.tax_ids[:1]
            if not no_vat:
                if not tax:
                    errors.append(_('Line "%s": no VAT tax is set.', line_label))
                elif int(tax.amount) not in VAT_CATEGORY_MAP:
                    errors.append(_(
                        'Line "%s": tax rate %s%% is not a valid Greek VAT rate '
                        '(24, 13, 6, 17, 9, 4 or 0).', line_label, tax.amount))
                elif int(tax.amount) == 0 and not line.l10n_gr_prov_vat_exemption:
                    errors.append(_(
                        'Line "%s": 0%% VAT requires a VAT Exemption Reason '
                        '(set on the line in the invoice).', line_label))
        # Counterpart required for B2B types; forbidden for retail/no-VAT types
        if (self.is_sale_document()
                and inv_type not in TYPES_NO_BUYER
                and not self.commercial_partner_id.vat):
            errors.append(_(
                'Invoice type %s requires a customer with a VAT number (counterpart is mandatory). '
                'Use an 11.x journal for retail sales without a VAT customer.', inv_type))
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
        return self.invoice_line_ids.filtered(lambda l: l.display_type == 'product')

    # ── Payload builder ───────────────────────────────────────────────────────

    @staticmethod
    def _ilyda_vat(vat, prefixed=True):
        """Return VAT normalised for EN16931.

        Greek VAT: strip GR/EL prefix, re-add EL when prefixed=True.
        Foreign VAT: return as-is (already carries the correct country prefix).
        prefixed=False is only meaningful for Greek VAT (used in B2G references).
        """
        vat = (vat or '').replace(' ', '').upper()
        if vat.startswith('EL') or vat.startswith('GR'):
            bare = vat[2:]
            return f'EL{bare}' if prefixed else bare
        return vat

    def _l10n_gr_prov_ilyda_build_payload(self):
        self.ensure_one()
        company = self.company_id
        partner = self.commercial_partner_id
        lines = self._l10n_gr_prov_ilyda_lines()
        inv_type = self._l10n_gr_prov_ilyda_inv_type()
        no_vat = inv_type in TYPES_NO_VAT
        no_cls = inv_type in TYPES_NO_CLASSIFICATION or inv_type in TYPES_DISPATCH

        # ── Lines, VAT breakdown buckets, classifications ────────────────────
        invoice_lines, row_types = [], []
        vat_buckets = {}      # (rate, aade_vat_category, exemption) -> [taxable, tax]
        cls_totals = {}       # (category, cls_type) -> amount
        for number, line in enumerate(lines, start=1):
            net = _r2(line.price_subtotal)
            vat_amount = _r2(line.price_total - line.price_subtotal)
            tax = line.tax_ids[:1]
            rate = tax.amount if tax else 0.0

            aade_vat_cat, category_code = _vat_category(tax, inv_type)

            exemption = (
                line.l10n_gr_prov_vat_exemption if aade_vat_cat == 7 else None
            ) or None

            key = (rate, aade_vat_cat, exemption)
            bucket = vat_buckets.setdefault(key, [0.0, 0.0])
            bucket[0] += net
            bucket[1] += vat_amount

            if not no_cls and line.l10n_gr_prov_cls_category and line.l10n_gr_prov_cls_type:
                cls_key = (line.l10n_gr_prov_cls_category, line.l10n_gr_prov_cls_type)
                cls_totals[cls_key] = _r2(cls_totals.get(cls_key, 0.0) + net)

            line_cls = [{
                'classificationCategory': line.l10n_gr_prov_cls_category,
                'classificationType': line.l10n_gr_prov_cls_type,
                'amount': net,
            }] if not no_cls and line.l10n_gr_prov_cls_category and line.l10n_gr_prov_cls_type else []

            discount_pct = line.discount or 0.0
            discount_amount = _r2(line.price_unit * line.quantity * discount_pct / 100.0)

            line_vals = {
                'lineNumber': number,
                'note': '',
                'invoicedQuantity': line.quantity,
                'invoicedQuantityUnits': 'EA',
                'netAmount': net,
                'discountAmount': discount_amount,
                'discountTotalAmount': discount_amount,
                'itemInfo': {
                    'itemInfoName': (line.product_id.name or line.name or '')[:200],
                    'itemInfoDescription': (line.name or line.product_id.name or '')[:200],
                },
                'priceDetails': {
                    'itemNetPrice': _r2(net / line.quantity) if line.quantity else _r2(net),
                    'itemPriceBaseQuantity': 1,
                },
                'lineVatInfo': {
                    'vatAmount': vat_amount,
                    'vatRate': rate,
                    'vatCategoryCode': category_code,
                    'aadeVatData': {
                        'aadeVatCategory': aade_vat_cat,
                        'aadeVatExemptionCategory': int(exemption) if exemption else None,
                    },
                },
            }
            cpv = line.product_id.l10n_gr_prov_cpv
            if cpv:
                line_vals['itemClassificationIdentifiers'] = [{
                    'classificationIdentifier': cpv,
                    'classificationIdentifierScheme': 'STI',
                }]
            invoice_lines.append(line_vals)

            row_type = {
                'lineNumber': number,
                'netValue': net,
                'vatCategory': str(aade_vat_cat),   # ILYDA expects string
                'vatAmount': vat_amount,
            }
            if exemption:
                row_type['vatExemptionCategory'] = int(exemption)
            # dispatch rows need item description/quantity/unit — also on
            # combined invoice+ΔΑ documents (isDeliveryNote journals)
            if inv_type == '9.3' or self.journal_id.l10n_gr_prov_delivery_note:
                row_type['itemDescr'] = (line.product_id.name or line.name or '')[:200]
                row_type['quantity'] = line.quantity
                row_type['measurementUnit'] = 1  # ponytail: no UoM mapping yet
            if line_cls:
                row_type['incomeClassification'] = line_cls
            row_types.append(row_type)

        # VAT breakdowns
        vat_breakdowns = []
        for (rate, aade_cat, exemption), (taxable, tax) in vat_buckets.items():
            code = 'O' if no_vat else ('E' if aade_cat == 7 else ('S' if rate else 'E'))
            vat_breakdowns.append({
                'categoryCode': code,
                'categoryRate': rate,
                'categoryTaxableAmount': _r2(taxable),
                'categoryTaxAmount': _r2(tax),
                'exemptionReasonCode': str(exemption) if exemption else None,
                'exemptionReasonText': None,
                'aadeVatData': {
                    'aadeVatCategory': aade_cat,
                    'aadeVatExemptionCategory': int(exemption) if exemption else None,
                },
            })

        income_classifications = [{
            'classificationCategory': cat,
            'classificationType': cls_type,
            'amount': amount,
        } for (cat, cls_type), amount in cls_totals.items()]

        # ── Totals ────────────────────────────────────────────────────────────
        # Withholding is an EN16931 doc-level allowance (BT-107) at Z/0%, so both
        # total systems land on the same gross (ILYDA rule BG-22-MISMATCH):
        #   BT-109 = lines net + charges − withheld; BT-112 = BT-109 + VAT;
        #   BT-115 = BT-112 (BR-CO-16, paid=rounding=0);
        #   ET-25  = net + VAT + fees/stamp/other − withheld == BT-112.
        # (cf. examples_bundle/test_b2b_allowance_aadeData.json)
        total_net = _r2(sum(b[0] for b in vat_buckets.values()))
        total_vat = _r2(sum(b[1] for b in vat_buckets.values()))
        withholding = _r2(self.l10n_gr_prov_withholding_amount or 0.0)
        stamp_duty = _r2(self.l10n_gr_prov_stamp_duty_amount or 0.0)
        fees = _r2(self.l10n_gr_prov_fees_amount or 0.0)
        other_taxes = _r2(self.l10n_gr_prov_other_taxes_amount or 0.0)
        extra_charges = _r2(stamp_duty + fees + other_taxes)
        total_without_vat = _r2(total_net + extra_charges - withholding)  # BT-109
        total_with_vat = _r2(total_without_vat + total_vat)               # BT-112
        amount_due = total_with_vat                                       # BT-115
        aade_gross = _r2(total_net + total_vat + extra_charges - withholding)  # ET-25

        # Withholding allowance: EN16931 mirror of taxTotals taxType=1, plus a
        # Z/0% VAT breakdown with negative taxable (as in ILYDA's example).
        doc_level_allowances = []
        if withholding:
            wh_label = dict(WITHHOLDING_CATEGORY_SELECTION).get(
                self.l10n_gr_prov_withholding_category, 'Παρακρατούμενος Φόρος')
            doc_level_allowances.append({
                'amount': withholding,
                'reason': wh_label,
                'vatCategoryCode': 'Z',
                'vatRate': 0,
            })
            vat_breakdowns.append({
                'categoryCode': 'Z',
                'categoryRate': 0,
                'categoryTaxableAmount': -withholding,
                'categoryTaxAmount': 0,
                'exemptionReasonCode': None,
                'exemptionReasonText': None,
            })

        exchange_rate = 0.0
        if self.currency_id and self.currency_id.name != 'EUR':
            company_currency = company.currency_id
            exchange_rate = _r2(self.currency_id._get_conversion_rate(
                self.currency_id, company_currency,
                company, self.invoice_date or self.date,
            ))

        # ── taxTotals (TaxTotalsType) — one entry per non-zero extra tax ────────
        # taxType: 1=Παρακρατούμενοι, 2=Τέλη, 3=Λοιποί Φόροι, 4=Χαρτόσημο
        tax_totals = []
        _extra_taxes = [
            (withholding,   1, self.l10n_gr_prov_withholding_category),
            (fees,          2, self.l10n_gr_prov_fees_category),
            (other_taxes,   3, self.l10n_gr_prov_other_taxes_category),
            (stamp_duty,    4, self.l10n_gr_prov_stamp_duty_category),
        ]
        for amount, tax_type, category in _extra_taxes:
            if amount:
                entry = {
                    'taxType': tax_type,
                    'taxAmount': amount,
                    'underlyingValue': total_net,
                }
                if category:
                    entry['taxCategory'] = int(category)
                tax_totals.append(entry)

        # ── docLevelCharges — non-VAT taxes as document-level charges ────────
        doc_level_charges = []
        _charge_taxes = [
            (stamp_duty,   4, self.l10n_gr_prov_stamp_duty_category,   'Χαρτόσημο'),
            (fees,         2, self.l10n_gr_prov_fees_category,          'Τέλη'),
            (other_taxes,  3, self.l10n_gr_prov_other_taxes_category,   'Λοιποί Φόροι'),
        ]
        for amount, tax_type, category, reason in _charge_taxes:
            if amount:
                charge = {
                    'chargeAmount': amount,
                    'chargeReason': reason,
                    'vatCategoryCode': 'O',
                    'vatRate': 0,
                    'aadeTaxData': {'aadeTaxType': tax_type},
                }
                if category:
                    charge['aadeTaxData']['aadeTaxCategory'] = int(category)
                doc_level_charges.append(charge)

        doc_charges_sum = _r2(sum(c['chargeAmount'] for c in doc_level_charges))

        doc_total = {
            'invoiceLinesNetAmountSum': total_net,
            'invoiceTotalWithoutVat': total_without_vat,
            'invoiceTotalVatAmount': total_vat,
            'invoiceTotalAmountWithVat': total_with_vat,
            'invoiceTotalVatAmountInAccountingCurrency': None,
            'amountDueForPayment': amount_due,
            'paidAmount': 0.0,
            'roundingAmount': 0.0,
            'documentLevelAllowancesSum': withholding,
            'documentLevelChargesSum': doc_charges_sum,
            'exchangeRate': exchange_rate,
            'aadeDocTotals': {
                'aadeTotalNetValue': total_net,
                'aadeTotalVatAmount': total_vat,
                'aadeTotalGrossValue': aade_gross,
                'aadeTotalWitheldAmount': withholding,
                'aadeTotalFeesAmount': fees,
                'aadeTotalStampDutyAmount': stamp_duty,
                'aadeTotalOtherTaxesAmount': other_taxes,
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
                'sellerAddressLine2': (
                    getattr(company_partner, 'arithmos_odou', None)
                    or company_partner.street2 or ''),
                'sellerCity': company_partner.city or '',
                'sellerPostCode': company_partner.zip or '',
                'sellerCountrySubdivision': company_partner.state_id.name or '',
            },
        }

        # ── Buyer (B2B/B2G only; retail stays anonymous) ─────────────────────
        buyer = None
        if partner.vat and inv_type not in TYPES_NO_BUYER:
            buyer = {
                'buyerVatIdentifier': self._ilyda_vat(partner.vat),
                'buyerName': partner.name,
                'buyerTradingName': partner.name,
                'buyerBranch': partner.l10n_gr_edi_branch_number or 0,
                'buyerPostalAddress': {
                    'buyerCountryCode': partner.country_id.code or 'GR',
                    'buyerAddressLine1': partner.street or '',
                    'buyerAddressLine2': (
                        getattr(partner, 'arithmos_odou', None) or partner.street2 or ''),
                    'buyerCity': partner.city or '',
                    'buyerPostCode': partner.zip or '',
                    'buyerCountrySubdivision': partner.state_id.name or '',
                },
            }
            if partner.email:
                buyer['buyerContact'] = {'buyerContactEmail': partner.email}

        # ── Series / serial ────────────────────────────────────────────────────
        # AADE series is plain xs:string(50) — Greek is permitted (ERP doc §5, series).
        # Send the journal code verbatim (ΤΙΜ, ΔΑ, ΑΛΠ) as Greek ERPs do.
        name_parts = (self.name or '').split('/')
        series = ('_'.join(name_parts[:-1]) or self.journal_id.code)[:50]
        serial = name_parts[-1] or str(self.sequence_number or 0)

        # ── AADE block ────────────────────────────────────────────────────────
        aade_data = {
            'aadeInvoiceTypeCode': inv_type,
            'invoiceRowTypes': row_types,
        }
        if income_classifications:
            aade_data['incomeClassifications'] = income_classifications
        if tax_totals:
            aade_data['taxTotals'] = tax_totals

        # Dispatch data: pure ΔΑ (9.3) or combined invoice+ΔΑ (ΤΔΑ/ΠΤΔΑ journals)
        is_delivery_note = self.journal_id.l10n_gr_prov_delivery_note
        if inv_type == '9.3' or is_delivery_note:
            if is_delivery_note:
                aade_data['isDeliveryNote'] = True
            aade_data['aadeMovePurpose'] = int(
                self.l10n_gr_prov_move_purpose
                or ('5' if self.move_type == 'out_refund' else '1'))
            if self.l10n_gr_prov_move_purpose == '19' and self.l10n_gr_prov_other_move_purpose:
                aade_data['otherMovePurposeTitle'] = self.l10n_gr_prov_other_move_purpose
            # Planned dispatch data (§5.3: estimates; actuals via RegisterTransfer)
            if self.l10n_gr_prov_dispatch_datetime:
                local = fields.Datetime.context_timestamp(
                    self.with_context(tz='Europe/Athens'),
                    self.l10n_gr_prov_dispatch_datetime)
                aade_data['aadeDispatchDate'] = f'{local.date()}T00:00:00'
                aade_data['aadeDispatchTime'] = local.strftime('%Y-%m-%dT%H:%M:%S')
            else:
                aade_data['aadeDispatchDate'] = f'{self.invoice_date}T00:00:00'
            # v2.0.1: otherTransportDetails is deprecated (MPD-0100) — the
            # planned vehicle goes in the header field instead
            if self.l10n_gr_prov_vehicle_id:
                aade_data['aadeVehicleNumber'] = self.l10n_gr_prov_vehicle_id.name
            ship = self.partner_shipping_id or partner
            aade_data['otherDeliveryNoteHeader'] = {
                'loadingAddress': {
                    'street': company_partner.street or '',
                    'number': getattr(company_partner, 'arithmos_odou', None) or company_partner.street2 or '',
                    'postalCode': company_partner.zip or '',
                    'city': company_partner.city or '',
                },
                'deliveryAddress': {
                    'street': ship.street or '',
                    'number': getattr(ship, 'arithmos_odou', None) or ship.street2 or '',
                    'postalCode': ship.zip or '',
                    'city': ship.city or '',
                },
            }
            if self.l10n_gr_prov_start_shipping_branch:
                aade_data['otherDeliveryNoteHeader']['startShippingBranch'] = \
                    int(self.l10n_gr_prov_start_shipping_branch)
            if self.l10n_gr_prov_complete_shipping_branch:
                aade_data['otherDeliveryNoteHeader']['completeShippingBranch'] = \
                    int(self.l10n_gr_prov_complete_shipping_branch)

        if inv_type in TYPES_NEED_CORRELATED and self.reversed_entry_id \
                and self.reversed_entry_id.l10n_gr_prov_mark:
            aade_data['correlatedInvoices'] = [
                int(self.reversed_entry_id.l10n_gr_prov_mark)
            ]

        payload = {
            'b2g': bool(self.l10n_gr_prov_b2g),
            'selfPricing': False,
            'vatPaidByBuyer': False,
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
            'docLevelAllowances': doc_level_allowances or None,
            'docLevelCharges': doc_level_charges or None,
            'aadeData': aade_data,
        }

        # Payment methods — forbidden for dispatch notes (9.x/10.x)
        if inv_type not in TYPES_DISPATCH:
            _TERMS = {
                '1': 'ΤΡΑΠΕΖΙΚΗ ΜΕΤΑΦΟΡΑ', '2': 'ΤΡΑΠΕΖΙΚΗ ΜΕΤΑΦΟΡΑ',
                '3': 'ΜΕΤΡΗΤΑ', '4': 'ΕΠΙΤΑΓΗ', '5': 'ΕΠΙ ΠΙΣΤΩΣΕΙ',
                '6': 'WEB BANKING', '7': 'POS / e-POS', '8': 'IRIS',
            }
            pay_lines = self.l10n_gr_prov_payment_ids
            if pay_lines:
                labels = dict(pay_lines._fields['payment_type'].selection)
                payload['paymentMethods'] = [{
                    'type': int(p.payment_type),   # AADE code 1-8 (ILYDA ET-63)
                    'paymentMethodInfo': p.info
                        or labels[p.payment_type].split(' - ', 1)[1],
                    'amount': _r2(p.amount),
                    **({'tipAmount': _r2(p.tip_amount)} if p.tip_amount else {}),
                    **({'transactionId': p.transaction_id} if p.transaction_id else {}),
                } for p in pay_lines]
                main = max(pay_lines, key=lambda p: p.amount)
                payload['paymentTerms'] = _TERMS.get(main.payment_type, 'ΕΠΙ ΠΙΣΤΩΣΕΙ')
            else:
                # legacy single-method fallback (old drafts, cron sends)
                method = self.l10n_gr_edi_payment_method or '5'
                ilyda_type, method_info = PAYMENT_METHOD_MAP.get(method, (5, 'Επί Πιστώσει'))
                # amount = myDATA gross (net + VAT + charges − withheld) = actual payable
                payload['paymentMethods'] = [{
                    'type': ilyda_type,
                    'paymentMethodInfo': method_info,
                    'amount': aade_gross,
                }]
                payload['paymentTerms'] = _TERMS.get(method, 'ΕΠΙ ΠΙΣΤΩΣΕΙ')

        # Credit note: reference the reversed invoice
        if self.move_type == 'out_refund' and self.reversed_entry_id \
                and self.reversed_entry_id.l10n_gr_prov_mark:
            origin = self.reversed_entry_id
            origin_parts = (origin.name or '').split('/')
            origin_series = ('_'.join(origin_parts[:-1]) or origin.journal_id.code)[:50]
            origin_serial = origin_parts[-1] or str(origin.sequence_number or 0)
            seller_bare_vat = self._ilyda_vat(company.vat, prefixed=False)
            reference = '|'.join([
                seller_bare_vat,
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
            payload['sellerIdentifiers'] = [{'sellerIdentifier': self._ilyda_vat(company.vat)}]
            if buyer:
                bare_vat = self._ilyda_vat(partner.vat, prefixed=False)
                if partner.l10n_gr_prov_aaht:
                    payload['buyerIdentifiers'] = [{'buyerIdentifier': partner.l10n_gr_prov_aaht}]
                buyer['buyerElectronicAddress'] = {
                    'buyerElectronicAddress': bare_vat,
                    'buyerElectronicAddressSchemeIdentifier': '9933',
                }
            ship = self.partner_shipping_id or partner
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
        # AADE business errors often carry the real reason in aadeMessage only
        message = error.get('defaultMessage') or error.get('aadeMessage') or ''
        aade = error.get('aadeMessage')
        if aade and aade != message:
            message = f'{message} ({aade})' if message else aade
        text = f"{error.get('code')}: {message}".strip()
        fields = error.get('errorFields') or []
        if fields:
            details = ', '.join(
                f"{f.get('field')}={f.get('value')}" for f in fields)
            text += f' [{details}]'
        return text

    def _l10n_gr_prov_ilyda_handle_response(self, data):
        self.ensure_one()
        _logger.debug('ILYDA response: %s', data)
        if isinstance(data, list):
            details = '; '.join(
                self._l10n_gr_prov_ilyda_format_error(e) if isinstance(e, dict)
                else str(e)
                for e in data
            ) or str(data)[:500]
            raise UserError(_('ILYDA rejected the document: %s', details))
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
            'l10n_gr_prov_previously_submitted': bool(marking.get('aadePreviouslySubmittedError228')),
        })
