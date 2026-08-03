# -*- coding: utf-8 -*-
"""MegEftPos Driver — REST wrapper client (ILYDA driver v2.1.5).

The driver is a local Windows service sitting between the ERP and the card
terminal, giving one API for every NSP (Cardlink, Viva, Mellon, ePay, Nexi,
Worldline, EDPS…). It is what turns Α.1155 from «the cashier types the
transaction id» into «the software charges the card».

Flow for a card payment:
    1. ask the provider (ILYDA) for a signature — this already existed;
    2. POST /api/v1/transaction/sale here, passing that signature through;
    3. the terminal charges, and the response carries nspReferenceNumber,
       which is the value AADE expects as the payment's transactionId.

Every call is {licenseKey, vatNumber, posDevice, request} and answers
{data, error{errorLevel, errorCode, errorMessage}}.
"""
import logging

import requests

from odoo import _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

TIMEOUT = 210  # the terminal itself waits up to 180s for the cardholder

# Παράρτημα Α — POS_PROTOCOL. NOT_SET is deliberately absent: it is the
# «unsupported» member, so a terminal must name a real protocol.
POS_PROTOCOLS = [
    ('EDPS_JSON', 'EDPS — JSON Protocol'),
    ('EDPS_WEB_ECR', 'EDPS — Web ECR'),
    ('EDPS_COMMON_TCP_SOCKET', 'EDPS — Common TCP Socket'),
    ('CARDLINK_DLL', 'Cardlink — TCP Socket (DLL)'),
    ('WORLDLINE_WEB_ECR', 'Cardlink / Worldline — Common Web'),
    ('MELLON_WEB_ECR', 'Mellon — Common Web'),
    ('EPAY_WEB_ECR', 'ePay — Common Web'),
    ('NEXI_WEB_ECR', 'Nexi — Common Web'),
    ('NEXI_COMMON_TCP_SOCKET', 'Nexi — TCP Socket'),
    ('ATTICA_WEB_ECR', 'Attica — Common Web'),
    ('VIVA_CLOUD', 'Viva Cloud'),
    ('INSS_RESTAPI', 'INSS'),
]

# Protocols that reach the terminal over the local network: host/port required.
PROTOCOLS_NEED_HOST = ('CARDLINK_DLL', 'EDPS_JSON', 'EDPS_COMMON_TCP_SOCKET',
                       'NEXI_COMMON_TCP_SOCKET')
# WebECR protocols authenticate with an API key redeemed from an OTP.
PROTOCOLS_NEED_API_KEY = ('MELLON_WEB_ECR', 'EPAY_WEB_ECR', 'NEXI_WEB_ECR',
                          'ATTICA_WEB_ECR', 'WORLDLINE_WEB_ECR', 'EDPS_WEB_ECR')
PROTOCOLS_NEED_CLIENT = ('VIVA_CLOUD',)

# Παράρτημα Α — RESPONSE_CODE
RESPONSE_CODES = [
    ('APPROVED', 'Εγκρίθηκε'),
    ('DECLINED', 'Απορρίφθηκε'),
    ('CANCELLED', 'Ακυρώθηκε'),
    ('FAILED', 'Απέτυχε'),
    ('UNKNOWN', 'Άγνωστο αποτέλεσμα'),
    ('BUSY', 'Το τερματικό απασχολείται'),
    ('MAX_TRANSACTIONS', 'Μέγιστο πλήθος συναλλαγών'),
    ('ACTION_REQUIRED', 'Απαιτείται ενέργεια στο τερματικό'),
    ('COMMUNICATION_ERROR', 'Σφάλμα επικοινωνίας'),
]


class MegEftPosDriver:
    """Thin HTTP client for MegEftPosRestServices."""

    def __init__(self, company):
        base = (company.l10n_gr_prov_eft_driver_url or '').rstrip('/')
        if not base:
            raise UserError(_(
                'Δεν έχει οριστεί η διεύθυνση του MegEftPos Driver '
                '(Ρυθμίσεις → Ελληνικός Πάροχος → Driver EFT/POS).'))
        if not company.l10n_gr_prov_eft_license_key:
            raise UserError(_(
                'Δεν έχει οριστεί το License Key του MegEftPos Driver.'))
        self.base = base
        self.license_key = company.sudo().l10n_gr_prov_eft_license_key
        # The ΑΦΜ the licence was issued for — on test keys ILYDA binds a
        # different one than the company's own, so it is configurable.
        self.vat = company._l10n_gr_prov_eft_driver_vat()

    def _post(self, path, payload):
        url = f'{self.base}{path}'
        _logger.info('MegEftPos %s payload: %s', path, payload)
        try:
            resp = requests.post(url, json=payload, timeout=TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            raise UserError(_(
                'Ο MegEftPos Driver δεν απαντά (%(url)s): %(err)s',
                url=url, err=e))
        except ValueError:
            raise UserError(_('Μη αναγνώσιμη απάντηση από τον MegEftPos Driver.'))
        _logger.info('MegEftPos %s response: %s', path, data)
        return data

    @staticmethod
    def check(data):
        """Return the payload, raising on a driver-level error.

        EL_WARNING is not fatal: the transaction may still carry a result, so
        the caller decides on responseCode.
        """
        error = (data or {}).get('error') or {}
        if error.get('errorLevel') == 'EL_ERROR':
            raise UserError(_(
                'MegEftPos: %(code)s %(msg)s',
                code=error.get('errorCode') or '',
                msg=error.get('errorMessage') or ''))
        return (data or {}).get('data') or {}

    def _envelope(self, pos_device, request=None):
        body = {
            'licenseKey': self.license_key,
            'vatNumber': self.vat,
            'posDevice': pos_device,
        }
        if request is not None:
            body['request'] = request
        return body

    # ── Transactions ─────────────────────────────────────────────────────────

    def sale(self, pos_device, request):
        return self.check(self._post(
            '/api/v1/transaction/sale', self._envelope(pos_device, request)))

    def refund(self, pos_device, request):
        return self.check(self._post(
            '/api/v1/transaction/refund', self._envelope(pos_device, request)))

    def void(self, pos_device, request):
        return self.check(self._post(
            '/api/v1/transaction/void', self._envelope(pos_device, request)))

    def preload(self, pos_device, request):
        return self.check(self._post(
            '/api/v1/transaction/preload', self._envelope(pos_device, request)))

    # ── Recovery ─────────────────────────────────────────────────────────────

    # These three answer with a list of TransactionResponse (empty when the
    # terminal knows nothing about the transaction).

    def pending_by_ecr(self, pos_device, ecr_reference):
        return self.check(self._post(
            f'/api/v1/transaction/pending/by/ecrReferenceNumber/{ecr_reference}',
            self._envelope(pos_device))) or []

    def pending_by_nsp(self, pos_device, nsp_reference):
        return self.check(self._post(
            f'/api/v1/transaction/pending/by/nspReferenceNumber/{nsp_reference}',
            self._envelope(pos_device))) or []

    def pending_all(self, pos_device):
        return self.check(self._post(
            '/api/v1/transaction/pending', self._envelope(pos_device))) or []

    # ── WebECR key ───────────────────────────────────────────────────────────

    def redeem_otp(self, pos_device, otp):
        """Exchange the OTP shown on the terminal for the API key WebECR
        protocols authenticate with."""
        body = self._envelope(pos_device)
        body['otp'] = otp
        return self.check(self._post('/api/v1/otp/redeem', body))
