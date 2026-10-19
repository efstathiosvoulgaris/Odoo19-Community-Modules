# -*- coding: utf-8 -*-
"""MegEftPos Driver — REST wrapper client (ILYDA driver v2.1.10).

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
from contextlib import contextmanager

import requests

from odoo import _
from odoo.exceptions import AccessError, UserError, ValidationError

_logger = logging.getLogger(__name__)

TIMEOUT = 210  # the terminal itself waits up to 180s for the cardholder

# Never written to the log. 'clientSecter' is the driver's own spelling.
SECRET_KEYS = frozenset({'licenseKey', 'apiKey', 'clientSecret', 'clientSecter', 'otp'})


class DriverRejected(UserError):
    """The request never became a transaction: the driver could not be
    reached, or refused the request (licence, body, auth). Nothing was
    charged, so the caller may safely go back and try again."""


class DriverNoAnswer(UserError):
    """The request left, but no usable answer came back (read timeout, reset
    connection, server error). The terminal MAY have charged the card: the
    outcome is unknown until the driver's pending list says otherwise."""


@contextmanager
def as_user_error():
    """Show a driver failure as the plain message it is.

    The web client only renders odoo's own exception classes as a message; a
    subclass (DriverRejected, DriverNoAnswer) arrives as «Odoo Server Error»
    with a traceback. Wrap every call made straight from a button in this.
    Paths that must tell the two apart (the charge itself) catch them first.
    """
    try:
        yield
    except (DriverRejected, DriverNoAnswer) as e:
        raise UserError(str(e)) from None


def check_driver_url(url):
    if url and not url.lower().startswith(('http://', 'https://')):
        raise ValidationError(_(
            'Η διεύθυνση του MegEftPos Driver πρέπει να ξεκινά με http:// ή https://.'))


def check_driver_url_rights(env):
    """Every driver call carries the licence key, API keys and Viva secrets:
    whoever sets the address decides where they go. Settings admins only."""
    if not env.su and not env.user.has_group('base.group_system'):
        raise AccessError(_(
            'Μόνο οι διαχειριστές ρυθμίσεων αλλάζουν τη διεύθυνση του '
            'MegEftPos Driver.'))


def redact(value):
    """Copy of a request/response with every secret masked, for logging."""
    if isinstance(value, dict):
        return {k: '***' if k in SECRET_KEYS and v else redact(v)
                for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value


def _is_greek(ch):
    return 'Ͱ' <= ch <= 'Ͽ'


def fix_greek(value):
    """Undo the driver's mis-decoded Greek, recursively.

    Some terminal libraries hand the driver Windows-1253 bytes that it reads
    as Windows-1252, so «Παρακαλώ ελέγξτε» arrives as «Ðáñáêáëþ åëÝãîôå» —
    already garbled in the driver's own log. A string with accented Latin
    letters and no Greek is re-read as 1253 — only when accented letters are
    most of its letters, so a real «Café Müller» is left alone.
    """
    if isinstance(value, dict):
        return {k: fix_greek(v) for k, v in value.items()}
    if isinstance(value, list):
        return [fix_greek(v) for v in value]
    if not isinstance(value, str) or any(map(_is_greek, value)):
        return value
    accented = sum('À' <= ch <= 'ÿ' for ch in value)
    if accented < 3 or accented * 2 < sum(ch.isalpha() for ch in value):
        return value
    for source in ('cp1252', 'latin-1'):
        try:
            fixed = value.encode(source).decode('cp1253')
        except UnicodeError:
            continue
        if any(map(_is_greek, fixed)):
            return fixed
    return value

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
    ('NEXI_SOFT_POS_WEB_ECR', 'Nexi — SoftPOS Web ECR'),
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
                          'NEXI_SOFT_POS_WEB_ECR', 'ATTICA_WEB_ECR',
                          'WORLDLINE_WEB_ECR', 'EDPS_WEB_ECR')
PROTOCOLS_NEED_CLIENT = ('VIVA_CLOUD',)
# Learned on ePay UAT (A80, 2026-10-19): the terminal refuses δόσεις started
# from the till («ΑΑΔΕ 1098»), and the NSP spends a signature on its first
# charge attempt whatever the outcome — a second charge with it is refused
# as DUPLICATE SIGNATURE. Mellon accepts both.
PROTOCOLS_NO_INSTALLMENTS = ('EPAY_WEB_ECR',)
PROTOCOLS_SINGLE_USE_SIGNATURE = ('EPAY_WEB_ECR',)

# Παράρτημα Α — PAYMENT_METHOD. NONE_PAYMENT_METHOD is what an NSP answers
# when it cannot tell the ERP what the customer picked, so it is a valid
# response value but never something we ask for.
PAYMENT_METHODS = [
    ('BANK_CARD', 'Τραπεζική Κάρτα'),
    ('IRIS', 'IRIS'),
]

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

    def __init__(self, company, terminal=None):
        # Per terminal when set, company-wide otherwise. The driver is a
        # process on the till PC, so one address only fits an install where
        # Odoo runs on that same PC and there is exactly one till.
        url = (terminal._l10n_gr_prov_driver_url() if terminal
               else company.l10n_gr_prov_eft_driver_url)
        base = (url or '').rstrip('/')
        if not base:
            raise UserError(_(
                'Δεν έχει οριστεί η διεύθυνση του MegEftPos Driver — ορίστε '
                'την στο τερματικό («MegEftPos Driver URL») ή γενικά στην '
                'εταιρεία (Ρυθμίσεις → Ελληνικός Πάροχος → Driver EFT/POS).'))
        # sudo: the key is an admin-only field, and cashiers charge cards too
        if not company.sudo().l10n_gr_prov_eft_license_key:
            raise UserError(_(
                'Δεν έχει οριστεί το License Key του MegEftPos Driver.'))
        self.base = base
        self.license_key = company.sudo().l10n_gr_prov_eft_license_key
        # The ΑΦΜ the licence was issued for — on test keys ILYDA binds a
        # different one than the company's own, so it is configurable.
        self.vat = company._l10n_gr_prov_eft_driver_vat()
        # MegEftPosRestServices.config → rest.authorization.method: with
        # BASIC_AUTH the service rejects unauthenticated calls with 401.
        driver = company.sudo()
        user = (driver.l10n_gr_prov_eft_driver_user or '').strip()
        self.auth = (user, driver.l10n_gr_prov_eft_driver_password or '') if user else None
        if self.auth:
            # HTTP Basic Auth is latin-1 by spec; Greek here fails deep inside
            # requests with an unreadable UnicodeEncodeError, so say it plainly.
            try:
                ''.join(self.auth).encode('latin-1')
            except UnicodeEncodeError:
                raise UserError(_(
                    'Τα στοιχεία σύνδεσης του MegEftPos Driver δέχονται μόνο '
                    'λατινικούς χαρακτήρες. Αν ο driver τρέχει με '
                    'rest.authorization.method=NONE, αφήστε τα κενά.'))

    def _post(self, path, payload):
        url = f'{self.base}{path}'
        _logger.info('MegEftPos %s payload: %s', path, redact(payload))
        # Transport and parsing are caught separately: json() raises ValueError,
        # and so does a bad Basic Auth credential (UnicodeEncodeError) — sharing
        # one handler leaves `resp` unbound on the second.
        # Whether money may have moved decides everything downstream, so the
        # failure is classified: a connection that never opened, or a request
        # the driver answered with a client error, charged nothing; anything
        # after the request left may have.
        try:
            resp = requests.post(url, json=payload, auth=self.auth, timeout=TIMEOUT)
        except requests.ConnectTimeout as e:
            raise DriverRejected(_(
                'Ο MegEftPos Driver δεν απαντά (%(url)s): %(err)s', url=url, err=e))
        except requests.ConnectionError as e:
            if 'NewConnectionError' in repr(e) or 'Failed to establish' in str(e):
                raise DriverRejected(_(
                    'Ο MegEftPos Driver δεν απαντά (%(url)s): %(err)s', url=url, err=e))
            raise DriverNoAnswer(_(
                'Η σύνδεση με τον MegEftPos Driver διακόπηκε (%(url)s): %(err)s',
                url=url, err=e))
        except requests.RequestException as e:
            raise DriverNoAnswer(_(
                'Ο MegEftPos Driver δεν απάντησε έγκαιρα (%(url)s): %(err)s',
                url=url, err=e))
        if resp.status_code >= 500:
            raise DriverNoAnswer(_(
                'Σφάλμα διακομιστή από τον MegEftPos Driver (%(url)s): HTTP %(code)s',
                url=url, code=resp.status_code))
        if resp.status_code >= 400 and not resp.headers.get(
                'Content-Type', '').startswith('application/json'):
            raise DriverRejected(_(
                'Ο MegEftPos Driver απέρριψε το αίτημα (%(url)s): HTTP %(code)s',
                url=url, code=resp.status_code))
        try:
            data = resp.json()
        except ValueError:
            # Not JSON: usually the Windows HTTP stack answering instead of the
            # driver. Name the known cause, but never echo the body — the URL is
            # user-set, and echoing what it returns turns this into a probe.
            if 'Invalid Hostname' in (resp.text or ''):
                raise DriverRejected(_(
                    'Ο MegEftPos Driver δεν δέχεται αυτή τη διεύθυνση (%(url)s): '
                    'το rest.server.host του δεν ταιριάζει με το URL — ορίστε '
                    'το σε «+».', url=url))
            raise DriverRejected(_(
                'Η διεύθυνση %(url)s δεν απάντησε ως MegEftPos Driver '
                '(HTTP %(code)s, όχι JSON).', url=url, code=resp.status_code))
        data = fix_greek(data)
        _logger.info('MegEftPos %s response: %s', path, redact(data))
        return data

    @staticmethod
    def check(data):
        """Return the payload, raising on a driver-level error.

        EL_WARNING is not fatal: the transaction may still carry a result, so
        the caller decides on responseCode.
        """
        error = (data or {}).get('error') or {}
        if error.get('errorLevel') == 'EL_ERROR':
            # No transaction was produced (transaction() only lands here when
            # the data block is empty), so nothing was charged.
            raise DriverRejected(_(
                'MegEftPos: %(code)s %(msg)s',
                code=error.get('errorCode') or '',
                msg=error.get('errorMessage') or ''))
        return (data or {}).get('data') or {}

    @classmethod
    def transaction(cls, data):
        """Return a transaction result, raising only when none was produced.

        The driver answers a failed charge with BOTH a TransactionResponse and
        errorLevel=EL_ERROR. Raising on the error level would roll the write
        back and discard ecrReferenceNumber — the only handle for recovering a
        charge that may have gone through. So keep the result and fold the
        driver's error into it; the caller decides on responseCode.

        An empty data block means nothing was attempted (bad licence, rejected
        body): there is nothing to preserve, so raise.
        """
        payload = (data or {}).get('data') or {}
        if not payload:
            return cls.check(data)
        error = (data or {}).get('error') or {}
        if error.get('errorLevel') == 'EL_ERROR':
            payload = dict(payload, driverError=' '.join(filter(None, (
                error.get('errorCode'), error.get('errorMessage')))))
        return payload

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
        return self.transaction(self._post(
            '/api/v1/transaction/sale', self._envelope(pos_device, request)))

    def refund(self, pos_device, request):
        return self.transaction(self._post(
            '/api/v1/transaction/refund', self._envelope(pos_device, request)))

    def void(self, pos_device, request):
        return self.transaction(self._post(
            '/api/v1/transaction/void', self._envelope(pos_device, request)))

    def preload(self, pos_device, request):
        return self.transaction(self._post(
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
