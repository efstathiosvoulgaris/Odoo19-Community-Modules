"""ΕΡΓΑΝΗ ΙΙ REST client (guide §2.1, JWT section). Tokens are fetched and
refreshed only through ErganiClient.token(), under a row lock, and the new pair
is committed before it is used — every refresh issues a new refresh token."""
import base64
import json
import logging
import time
from datetime import datetime, timedelta

import requests

from odoo import SUPERUSER_ID, api, fields

_logger = logging.getLogger(__name__)
TIMEOUT = (5, 60)


class ErganiError(Exception):
    pass


class ErganiNotSent(ErganiError):
    """Failed before the request body could have left: safe to retry."""


class ErganiUnknown(ErganiError):
    """May or may not have reached ΕΡΓΑΝΗ: a person must check."""


class ErganiRejected(ErganiError):
    """HTTP 400: ΕΡΓΑΝΗ refused the card."""


class ErganiThrottled(ErganiError):
    """HTTP 429."""


class ErganiAuthError(ErganiError):
    """Login failed: wrong credentials or ΕΡΓΑΝΗ refuses the account."""


def _parse_dt(value):
    """'2022-05-10T09:43:37.5388855+03:00' → naive UTC (7-digit fractions)."""
    if not value or not isinstance(value, str):
        return False
    head, sep, tail = value.partition('.')
    if not sep:  # no fraction: the offset, if any, is still on head
        head, tail = (head[:-6], head) if len(head) > 6 and head[-6] in '+-' else (head, '')
    offset = tail[-6:] if len(tail) >= 6 and tail[-6] in '+-' else '+00:00'
    try:
        aware = datetime.fromisoformat(head + offset)
    except ValueError:
        return False
    return (aware - aware.utcoffset()).replace(tzinfo=None)


def _post(url, body, headers, timeout=TIMEOUT):
    """POST classifying failures by whether the body may have left."""
    try:
        return requests.post(url, data=json.dumps(body), headers=headers, timeout=timeout)
    except requests.exceptions.ConnectTimeout as e:
        raise ErganiNotSent(f'Λήξη χρόνου σύνδεσης: {e}') from e
    except requests.exceptions.SSLError as e:
        # A handshake/certificate failure happens before the body leaves; a TLS
        # error while reading the response comes after (DESIGN §5.7).
        if any(s in str(e) for s in ('CERTIFICATE_VERIFY_FAILED', 'handshake',
                                     'WRONG_VERSION_NUMBER', 'certificate')):
            raise ErganiNotSent(f'Σφάλμα TLS: {e}') from e
        raise ErganiUnknown(f'Σφάλμα TLS μετά την αποστολή: {e}') from e
    except requests.exceptions.ConnectionError as e:
        # DNS failure / refused happen before anything is sent; a reset or
        # remote disconnect may come after the body left.
        text = str(e)
        if any(s in text for s in ('NameResolution', 'getaddrinfo', 'Connection refused',
                                   'Failed to establish a new connection')):
            raise ErganiNotSent(f'Αδύνατη σύνδεση: {e}') from e
        raise ErganiUnknown(f'Η σύνδεση διακόπηκε: {e}') from e
    except requests.exceptions.RequestException as e:
        raise ErganiUnknown(f'Αβέβαιη αποστολή: {e}') from e


def _get(url, params, headers, timeout=TIMEOUT):
    """GET for read-only services: nothing is declared, so every transport
    failure is simply «not sent»."""
    try:
        return requests.get(url, params=params, headers=headers, timeout=timeout)
    except requests.exceptions.RequestException as e:
        raise ErganiNotSent(f'Αδύνατη σύνδεση: {e}') from e


def _extract_pdf(resp):
    """The receipt comes as base64 (guide γρ. 363); whether bare or inside a
    JSON object is UNVERIFIED until trial, so accept both."""
    if resp.content[:4] == b'%PDF':
        return resp.content
    try:
        data = resp.json()
    except ValueError:
        data = resp.text
    candidates, stack = [], [data]
    while stack:
        item = stack.pop()
        if isinstance(item, str):
            candidates.append(item)
        elif isinstance(item, dict):
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)
    for text in candidates:
        try:
            raw = base64.b64decode(text.strip().strip('"'))
        except ValueError:
            continue
        if raw[:4] == b'%PDF':
            return raw
    raise ErganiError('Η απάντηση του ΕΡΓΑΝΗ δεν περιέχει PDF.')


# What may be kept of each call (PLAN_1.3 §2.4): never credentials or tokens,
# never the card body twice (the card keeps it), other bodies only on failure.
NO_BODY_KINDS = ('login', 'refresh', 'card', 'wto')


class ErganiClient:

    def __init__(self, company):
        self.company = company.sudo()
        self.env = self.company.env
        self.base = self.company._ergani_base_url()

    # ── transport + submission log ───────────────────────────────────────────

    def _http(self, method, path, kind, body=None, headers=None, params=None, card=None):
        started = time.monotonic()
        resp = error = None
        try:
            if method == 'GET':
                resp = _get(self.base + path, params, headers or {})
            else:
                resp = _post(self.base + path, body, headers or {})
            return resp
        except ErganiError as e:
            error = e
            raise
        finally:
            self._log(kind, method, path, resp, error, started, body, card)

    def _log(self, kind, method, path, resp, error, started, body, card):
        """One row per call, in its own transaction: it must survive the
        caller's rollback, or a crash right after the POST."""
        if error is not None:
            outcome = 'not_sent' if isinstance(error, ErganiNotSent) else 'unknown'
            status = 0
        else:
            status = resp.status_code
            outcome = {200: 'ok', 400: 'rejected', 401: 'auth', 429: 'throttled'}.get(
                status, 'error')
        vals = {
            'company_id': self.company.id,
            'environment': self.company.ergani_mode,
            'kind': kind,
            'method': method,
            'endpoint': path,
            'http_status': status,
            'outcome': outcome,
            'duration_ms': int((time.monotonic() - started) * 1000),
            'card_id': card.id if card and card._name == 'ergani.card' else False,
            'wto_id': card.id if card and card._name == 'ergani.wto' else False,
            'card_hash': (card.row_hash if card._name == 'ergani.card' else card.payload_hash)
                         if card else False,
            'message': str(error)[:500] if error is not None else (
                False if outcome == 'ok' else resp.text[:500]),
        }
        if kind not in NO_BODY_KINDS and outcome != 'ok':
            vals['request_body'] = json.dumps(body, ensure_ascii=False) if body else False
            vals['response_body'] = resp.text[:4000] if resp is not None else False
        try:
            with self.env.registry.cursor() as cr:
                api.Environment(cr, SUPERUSER_ID, {})['ergani.submission'].create(vals)
        except Exception:
            _logger.exception('ΕΡΓΑΝΗ: could not log the %s call', kind)

    # ── tokens ───────────────────────────────────────────────────────────────

    def _session_row(self):
        Session = self.env['ergani.session'].sudo()
        key = [('company_id', '=', self.company.id),
               ('environment', '=', self.company.ergani_mode)]
        row = Session.search(key, limit=1)
        if not row:
            row = Session.create({'company_id': self.company.id,
                                  'environment': self.company.ergani_mode})
            self.env.cr.commit()
        self.env.cr.execute('SELECT id FROM ergani_session WHERE id = %s FOR UPDATE', [row.id])
        row.invalidate_recordset()
        return row

    def _store(self, row, data):
        # accessTokenExpired is a lifetime in seconds (guide γρ. 163),
        # refreshTokenExpired a timestamp.
        seconds = data.get('accessTokenExpired')
        row.write({
            'access_token': data.get('accessToken'),
            'refresh_token': data.get('refreshToken'),
            'access_expires': (fields.Datetime.now() + timedelta(seconds=int(seconds))
                               if seconds else False),
            'refresh_expires': _parse_dt(data.get('refreshTokenExpired')),
        })
        self.env.cr.commit()  # the new refresh token must survive a crash

    def _login(self, row):
        body = {'Username': self.company.ergani_username or '',
                'Password': self.company.ergani_password or '', 'Usertype': '02'}
        resp = self._http('POST', 'Authentication', 'login', body,
                          {'Content-Type': 'application/json'})
        if resp.status_code != 200:
            raise ErganiAuthError(f'Login ΕΡΓΑΝΗ: HTTP {resp.status_code} {resp.text[:300]}')
        self._store(row, resp.json())

    def _refresh(self, row):
        body = {'AccessToken': row.access_token, 'RefreshToken': row.refresh_token}
        resp = self._http('POST', 'Authentication/Refresh', 'refresh', body,
                          {'Content-Type': 'application/json'})
        if resp.status_code != 200:
            return False
        self._store(row, resp.json())
        return True

    def token(self, force_refresh=False):
        """Login/refresh never carries a card, so its failures must never make
        a card 'unknown': transport trouble is 'not sent', anything else pauses."""
        if not (self.company.ergani_username and self.company.ergani_password):
            raise ErganiAuthError('Δεν έχουν οριστεί χρήστης/κωδικός ΕΡΓΑΝΗ.')
        if not self.base.startswith('https://'):
            raise ErganiAuthError('Δεν έχει οριστεί σωστή διεύθυνση ΕΡΓΑΝΗ.')
        try:
            return self._token(force_refresh)
        except ErganiUnknown as e:
            raise ErganiNotSent(f'Login ΕΡΓΑΝΗ: {e}') from e
        except (ValueError, TypeError, AttributeError) as e:
            raise ErganiAuthError(f'Login ΕΡΓΑΝΗ: απρόσμενη απάντηση ({e})') from e

    def _token(self, force_refresh):
        row = self._session_row()
        soon = fields.Datetime.now() + timedelta(minutes=5)
        if row.access_token and not force_refresh and (
                not row.access_expires or row.access_expires > soon):
            return row.access_token
        if row.refresh_token and (not row.refresh_expires or row.refresh_expires > soon):
            if self._refresh(row):
                return row.access_token
        self._login(row)
        return row.access_token

    def _auth_headers(self, force_refresh=False):
        return {'Content-Type': 'application/json',
                'Authorization': 'Bearer ' + self.token(force_refresh)}

    def _authorized(self, method, path, kind, body=None, params=None, card=None):
        resp = self._http(method, path, kind, body, self._auth_headers(), params, card)
        if resp.status_code == 401:  # rejected unread: the only safe repeat
            resp = self._http(method, path, kind, body, self._auth_headers(force_refresh=True),
                              params, card)
        return resp

    # ── services ─────────────────────────────────────────────────────────────

    def post_card(self, payload, card=None):
        """WRKCardSE. Returns the single {id, protocol, submitDate} entry."""
        return self.post_document('WRKCardSE', payload, record=card, kind='card')

    def post_document(self, code, payload, record=None, kind='wto'):
        """Any declaration (WRKCardSE, WTODaily, …): POST Documents/{code}, answer
        [{id, protocol, submitDate}] (guide γρ. 283–311)."""
        resp = self._authorized('POST', 'Documents/' + code, kind, payload, card=record)
        if resp.status_code == 429:
            raise ErganiThrottled('ΕΡΓΑΝΗ: πολλά αιτήματα (429).')
        if resp.status_code == 400:
            raise ErganiRejected(resp.text[:1000])
        if resp.status_code == 401:
            raise ErganiAuthError(f'ΕΡΓΑΝΗ: HTTP 401 {resp.text[:300]}')
        if resp.status_code != 200:
            raise ErganiUnknown(f'ΕΡΓΑΝΗ: HTTP {resp.status_code} {resp.text[:300]}')
        try:
            data = resp.json()
        except ValueError as e:
            raise ErganiUnknown(f'ΕΡΓΑΝΗ: απάντηση χωρίς JSON: {resp.text[:300]}') from e
        if not isinstance(data, list) or len(data) != 1:
            raise ErganiUnknown(f'ΕΡΓΑΝΗ: απρόσμενη απάντηση: {resp.text[:300]}')
        return data[0], resp.text

    def get_receipt(self, protocol, submitted_yyyymmdd, card=None):
        """PDF of a submitted card (guide γρ. 357–371)."""
        resp = self._authorized('GET', 'Documents/WRKCardSE', 'receipt', card=card, params={
            'protocol': protocol, 'submittedDate': submitted_yyyymmdd})
        if resp.status_code != 200:
            raise ErganiError(f'HTTP {resp.status_code} {resp.text[:300]}')
        return _extract_pdf(resp)

    def execute_service(self, code, parameters=None):
        """WebServices/ExecuteService (guide γρ. 437–472): the service's own
        object, e.g. {'MiniaiaKatastash': ...} for EX_BASE_04."""
        body = {'ServiceCode': code, 'Parameters': [
            {'ParameterName': k, 'ParameterValue': str(v)} for k, v in (parameters or {}).items()]}
        resp = self._authorized('POST', 'WebServices/ExecuteService', 'service', body)
        if resp.status_code != 200:
            raise ErganiError(f'{code}: HTTP {resp.status_code} {resp.text[:300]}')
        try:
            data = resp.json()
        except ValueError as e:
            raise ErganiError(f'{code}: απάντηση χωρίς JSON') from e
        return data.get(code, data) if isinstance(data, dict) else data

    def _get_json(self, path):
        resp = self._authorized('GET', path, 'service')
        if resp.status_code != 200:
            raise ErganiError(f'{path}: HTTP {resp.status_code} {resp.text[:300]}')
        try:
            return resp.json()
        except ValueError as e:
            raise ErganiError(f'{path}: απάντηση χωρίς JSON') from e

    def list_services(self):
        """WebServices/ServicesList: every service this account may run (guide γρ. 379–429)."""
        return self._get_json('WebServices/ServicesList')

    def list_submissions(self):
        """Lookup/Submissions: every declaration type this account may submit (γρ. 235–243)."""
        return self._get_json('Lookup/Submissions')

    def test_connection(self):
        body = {'ServiceCode': 'EX_BASE_01', 'Parameters': []}
        resp = self._authorized('POST', 'WebServices/ExecuteService', 'service', body)
        if resp.status_code != 200:
            raise ErganiError(f'HTTP {resp.status_code} {resp.text[:300]}')
        data = resp.json()
        return (data.get('EX_BASE_01') or {}).get('Ergodotis') or data
