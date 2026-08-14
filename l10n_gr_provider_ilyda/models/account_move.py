# -*- coding: utf-8 -*-
"""ILYDA Y.PA.H.E.S. driver.

Implements the operations dispatched by l10n_gr_provider_base:
  _l10n_gr_prov_send_ilyda            POST /api/invoice
  _l10n_gr_prov_upload_pdf_ilyda      POST /api/invoice/upload/{invoiceId}
  _l10n_gr_prov_poll_b2g_status_ilyda GET  /api/invoice/status/{invoiceId}
  _l10n_gr_prov_recover_ilyda         GET  /api/invoice/by-uid/{uid}
                                      GET  /api/invoice/pending/by-uid/{uid}

API reference: ILYDA "Οδηγίες υλοποίησης eInvoicing" v1.0.6.
"""
import hashlib
import json
import logging
import unicodedata

import requests

from odoo import fields, models, _
from odoo.exceptions import UserError
from odoo.addons.l10n_gr_provider_base.models.gr_mydata import (
    ProviderUnreachableError,
    VAT_CATEGORY_MAP,
    TYPES_NO_BUYER,
    TYPES_NO_VAT,
    TYPES_NO_CLASSIFICATION,
    TYPES_CREDIT,
    TYPES_NEED_CORRELATED,
    PAYMENT_METHOD_MAP,
    PROVIDER_SUBMITTABLE_TYPES,
    TYPES_DISPATCH,
    TYPES_DISPATCH_CORRELATED,
    TYPES_RECEIPT,
    TYPES_SELF_BILLED,
    MOVE_PURPOSE_NOT_SENDABLE,
    WITHHOLDING_CATEGORY_SELECTION,
    valid_cls_types,
    valid_cls_categories,
    preferred_e3,
)

_logger = logging.getLogger(__name__)

ILYDA_PROD_BASE = 'https://vs.gr'
ILYDA_TEST_BASE = 'https://test.vs.gr'
# 90s, not 30s: ILYDA's transmission-failure-2 simulation deliberately stalls the
# response, and a client-side timeout would send us down the TF-1 offline path
# instead. Real AADE round-trips are slow enough to want the headroom anyway.
TIMEOUT = 90

# BT-15 value that switches test.vs.gr into the transmission-failure-2 simulation
# («Οδηγίες διαχείρισης offline παραστατικών μετά από transmission failure 2» §6).
TF2_SENTINEL = '1cadb85a-88e7-4853-b5d0-75143b38b76e'

# UBL document type codes
UBL_INVOICE = '380'
UBL_CREDIT_NOTE = '381'
# AADE types ILYDA requires to carry 381 (BT-3-MISMATCH). move_type is not
# enough: a μη-συσχετιζόμενο 5.2 is entered on the ΠΙΜΣ journal as a plain
# customer invoice, so it reaches us as out_invoice.
AADE_CREDIT_TYPES = ('5.1', '5.2', '11.4')


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
        try:
            resp = requests.post(
                f'{self.base}/api/invoice',
                json=payload, headers=self._headers(), auth=self._auth, timeout=TIMEOUT)
        except (requests.ConnectionError, requests.Timeout) as e:
            # TF-1 trigger: the provider is unreachable — the base send flow
            # falls back to the locally signed offline QR when a key exists.
            raise ProviderUnreachableError(str(e)) from e
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
        if resp.status_code == 404:
            # The branded HTML 404 means the route did not match at all — the
            # ERP-Bridge status endpoint is not exposed on this environment.
            # A document ILYDA simply does not know answers with a JSON A000x.
            raise UserError(_(
                'ILYDA has no B2G status endpoint on %s (HTTP 404 for '
                'invoice id %s). Ask them whether /api/invoice/status is '
                'enabled for this account.', self.base, invoice_id))
        return self._parse(resp)

    # Search / reconciliation lookups. The API docs list X-Auth-Key as the
    # primary auth for these; Basic auth works for POST /api/invoice, so we use
    # it here too — if these ever return 401/403, add an X-Auth-Key company
    # field. Not-found comes back as an A000x error body, not an exception.
    def _get(self, path):
        resp = requests.get(
            f'{self.base}{path}',
            headers=self._headers(json_content=False), auth=self._auth, timeout=TIMEOUT)
        return self._parse(resp)

    def find_by_uid(self, uid):
        return self._get(f'/api/invoice/by-uid/{uid}')

    def find_by_mark(self, mark):
        return self._get(f'/api/invoice/by-mark/{mark}')

    def find_by_auth_code(self, hash_):
        return self._get(f'/api/invoice/by-authentication-code/{hash_}')

    def pending_by_uid(self, uid):
        """TF-2 transmission queue: state of a document queued while AADE was
        offline (MyDataQueuePendingEntry)."""
        return self._get(f'/api/invoice/pending/by-uid/{uid}')

    # Offline-QR key lifecycle (TF-1). {vat} = bare 9 digits or EL+9.
    def issue_offline_key(self, vat, purpose):
        resp = requests.post(
            f'{self.base}/api/offline-qr/{vat}/keys',
            json={'purpose': purpose or 'Odoo ERP'},
            headers=self._headers(), auth=self._auth, timeout=TIMEOUT)
        return self._parse(resp)

    def verify_offline_key(self, vat, key_identifier):
        resp = requests.post(
            f'{self.base}/api/offline-qr/{vat}/keys/{key_identifier}/verify',
            headers=self._headers(json_content=False), auth=self._auth, timeout=TIMEOUT)
        return self._parse(resp)

    def revoke_offline_key(self, vat, key_identifier):
        # keyIdentifier is REQUIRED here on purpose: omitting it revokes ALL
        # active keys of the VAT.
        resp = requests.delete(
            f'{self.base}/api/offline-qr/{vat}/keys',
            params={'keyIdentifier': key_identifier},
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
        return self._l10n_gr_prov_ilyda_handle_response(data)

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

    # A0002/3/4/6: not-found codes of by-mark/by-id/by-uid/by-authentication-code;
    # the pending queue returns its own A000x for unknown uids.
    _ILYDA_NOT_FOUND = {'A0002', 'A0003', 'A0004', 'A0005', 'A0006'}

    @classmethod
    def _l10n_gr_prov_ilyda_error_code(cls, data):
        """Error code of a search response, or None if it is a real document."""
        if not isinstance(data, dict):
            return 'A0000'
        if data.get('code'):
            return data['code']
        errors = data.get('errors') or []
        if errors and isinstance(errors[0], dict):
            return errors[0].get('code') or 'A0000'
        return None

    def _l10n_gr_prov_ilyda_lookup(self, method, key):
        """Run one search call. Returns the document dict, or None when the
        provider explicitly answers "not found". Any OTHER error raises — the
        duplicate guard must never read an auth/server failure as "unknown
        document, safe to resend"."""
        data = method(key)
        code = self._l10n_gr_prov_ilyda_error_code(data)
        if code is None:
            return data
        if code in self._ILYDA_NOT_FOUND:
            return None
        raise UserError(_(
            'Provider lookup failed (%(code)s): %(body)s',
            code=code, body=str(data)[:300]))

    def _l10n_gr_prov_recover_ilyda(self):
        """Look this document up at ILYDA by UID; adopt what the provider has.

        Returns a truthy state ('sent'/'queued') when the document exists at the
        provider — the caller must NOT resend. Returns False when it is unknown
        there (safe to resend) or when only errors were found.
        """
        self.ensure_one()
        client = IlydaClient(self.company_id)
        candidates = self._l10n_gr_prov_ilyda_uid_candidates()
        stored = (self.l10n_gr_prov_invoice_identifier or '').lower()
        matched = next((u for _label, u in candidates if u == stored), None)

        # Self-check on already-marked documents: prove the UID algorithm
        # against the identifier ILYDA returned, before it's ever needed for
        # a real recovery.
        if self.l10n_gr_prov_mark:
            if not stored:
                body = _('Έλεγχος UID: δεν υπάρχει αποθηκευμένο αναγνωριστικό για σύγκριση.')
            elif matched:
                label = next(l for l, u in candidates if u == matched)
                body = _('Έλεγχος UID: ο τοπικός υπολογισμός (%s) ταυτίζεται με το '
                         'αναγνωριστικό του παρόχου — η ανάκτηση είναι αξιόπιστη.', label)
            else:
                body = _('Έλεγχος UID: ΚΑΜΙΑ αντιστοιχία. Αποθηκευμένο: %(stored)s — '
                         'υπολογισμένα: %(calc)s. Χρειάζεται προσαρμογή του αλγορίθμου.',
                         stored=stored,
                         calc='; '.join(f'{l}={u}' for l, u in candidates))
            self.l10n_gr_prov_uid = matched or stored or candidates[0][1]
            self.message_post(body=body)
            return 'sent'

        # Prefer the provider-authored identifier (present after a TF-2 queue
        # response) — it needs no algorithm at all. Without one, try every
        # candidate format so a wrong concatenation guess can't yield a false
        # "not found" (which would green-light a duplicate resend).
        # NB: never name a local variable `uid` in a function that calls _() —
        # translate._get_lang() inspects caller frame locals and would read the
        # hash as a res.users id (crashed the cron until renamed to doc_uid).
        uid_keys = [stored] if stored else [u for _label, u in candidates]
        doc_uid = uid_keys[0]
        self.l10n_gr_prov_uid = doc_uid

        # 1. Completed documents
        data = None
        for key in uid_keys:
            data = self._l10n_gr_prov_ilyda_lookup(client.find_by_uid, key)
            if data is not None:
                doc_uid = key
                self.l10n_gr_prov_uid = doc_uid
                break
        if data is not None and data.get('mark'):
            self.write({
                'l10n_gr_prov_mark': str(data['mark']),
                'l10n_gr_prov_verification_hash':
                    data.get('invoiceVerificationHash') or self.l10n_gr_prov_verification_hash,
                'l10n_gr_prov_qr_url':
                    data.get('myDataQrCode') or self.l10n_gr_prov_qr_url,
                'l10n_gr_prov_state': 'sent',
                'l10n_gr_prov_error': False,
            })
            self.message_post(body=_(
                'Το MARK ανακτήθηκε από τον πάροχο χωρίς επανυποβολή: %s',
                self.l10n_gr_prov_mark))
            self._l10n_gr_prov_ilyda_note_missing_invoice_id()
            return 'sent'

        # 2. TF-2 transmission queue. Unlike the single-invoice lookups, an
        # unknown UID here isn't confirmed to come back as a proper A000x code
        # — it may just be an empty object. A real MyDataQueuePendingEntry
        # always carries 'uid' (docs, EG-15), so treat anything without one as
        # not-found too, rather than falling into the terminal-failure branch
        # below for a document that was simply never submitted.
        entry = None
        for key in uid_keys:
            candidate = self._l10n_gr_prov_ilyda_lookup(client.pending_by_uid, key)
            if candidate is not None and candidate.get('uid'):
                entry = candidate
                self.l10n_gr_prov_uid = key
                break
        if entry is None:
            if self.l10n_gr_prov_state == 'queued':
                # It was queued and now the provider doesn't know it — surface it.
                self.write({
                    'l10n_gr_prov_state': 'error',
                    'l10n_gr_prov_error': _(
                        'Το παραστατικό δεν βρέθηκε πλέον στην ουρά του παρόχου.'),
                })
            else:
                self.message_post(body=_(
                    'Αναζήτηση στον πάροχο: το παραστατικό δεν βρέθηκε (UID %s) — '
                    'ασφαλής η επανυποβολή.', doc_uid))
            return False

        state = entry.get('invoiceState')
        # mark is filled iff the queue completed the transmission (docs: EG-15);
        # it may arrive as string or number.
        if entry.get('mark'):
            self.write({
                'l10n_gr_prov_mark': str(entry['mark']),
                'l10n_gr_prov_verification_hash':
                    entry.get('verificationHash') or self.l10n_gr_prov_verification_hash,
                'l10n_gr_prov_invoice_id':
                    entry.get('invoiceId') or self.l10n_gr_prov_invoice_id,
                'l10n_gr_prov_state': 'sent',
                'l10n_gr_prov_error': False,
            })
            self.message_post(body=_(
                'Η ουρά του παρόχου ολοκλήρωσε τη διαβίβαση. MARK: %s',
                self.l10n_gr_prov_mark))
            self._l10n_gr_prov_ilyda_note_missing_invoice_id()
            return 'sent'
        if state in ('RESUBMIT_PENDING', 'SUBMITTED'):
            # SUBMITTED without a mark yet: transitional — keep polling.
            if self.l10n_gr_prov_state != 'queued':
                self.write({'l10n_gr_prov_state': 'queued', 'l10n_gr_prov_error': False})
            self.message_post(body=_(
                'Σε ουρά διαβίβασης στον πάροχο (αναμονή myDATA).'))
            return 'queued'
        # SUBMISSION_ERRORS / MAX_RETRIES_REACHED: transmitted but rejected by
        # AADE (no MARK exists) or the provider gave up — record the reason and
        # allow a fresh submission attempt.
        try:
            details = '; '.join(
                self._l10n_gr_prov_ilyda_format_error(e)
                for e in json.loads(entry.get('errorsJson') or '[]'))
        except (ValueError, AttributeError):
            details = entry.get('errorsJson') or ''
        self.write({
            'l10n_gr_prov_state': 'error',
            'l10n_gr_prov_error': _(
                'Ουρά παρόχου: %(state)s. %(details)s', state=state, details=details),
        })
        self.message_post(body=self.l10n_gr_prov_error)
        return False

    def _l10n_gr_prov_ilyda_note_missing_invoice_id(self):
        """Recovered documents may lack the provider's invoiceId (the search
        and queue responses don't always include it) — without it the legal
        PDF cannot be uploaded via /api/invoice/upload/{invoiceId}."""
        self.ensure_one()
        if not self.l10n_gr_prov_invoice_id:
            self.message_post(body=_(
                'Το παραστατικό ανακτήθηκε χωρίς provider invoice id — το PDF '
                'δεν μπορεί να μεταφορτωθεί αυτόματα στον πάροχο. Αν απαιτείται, '
                'ανεβάστε το χειροκίνητα από το portal της ILYDA.'))

    def _ilyda_now_athens(self):
        """Now, as an ISO timestamp with the Athens offset (DST-correct)."""
        now_athens = fields.Datetime.context_timestamp(
            self.with_context(tz='Europe/Athens'), fields.Datetime.now())
        stamp = now_athens.strftime('%Y-%m-%dT%H:%M:%S%z')
        return f'{stamp[:-2]}:{stamp[-2:]}'  # +0300 -> +03:00

    def _ilyda_issue_date(self):
        """BT-2. Date-only, as in every ILYDA example — except when BT-15 carries
        the transmission-failure-2 sentinel, where the simulation demands a
        timestamp within 10' of now, tz and DST included."""
        if (self.l10n_gr_prov_receiving_advice_ref or '').strip() == TF2_SENTINEL:
            return self._ilyda_now_athens()
        return f'{self.invoice_date}T00:00:00'

    def _l10n_gr_prov_issue_offline_ilyda(self):
        """TF-1: sign an offline QR locally (provider unreachable at issue).

        The payload amounts must match the later normal submission of the same
        UID (TQR-0030/31/32)."""
        self.ensure_one()
        key = self.env['l10n.gr.prov.offline.key']._get_active_key(self.company_id)
        if not key:
            return False
        series, serial = self._l10n_gr_prov_ilyda_series_serial()
        issue_dt = self._ilyda_now_athens()
        payload = {
            'sellerVat': self._ilyda_vat(self.company_id.vat, prefixed=False),
            'sellerBranch': int(self.company_id.partner_id.l10n_gr_edi_branch_number or 0),
            'invoiceIssueDate': issue_dt,
            'seriesNumber': series,
            'serialNumber': serial,
            'aadeInvoiceTypeCode': self._l10n_gr_prov_ilyda_inv_type() or '',
            # ponytail: plain move totals; documents with fees/stamp/other extra
            # taxes may trip TQR-0030 — derive from the submit builder's
            # aadeDocTotals if that ever bites.
            'netAmount': _r2(self.amount_untaxed),
            'vatAmount': _r2(self.amount_tax),
            'grossAmount': _r2(self.amount_total),
        }
        partner = self.commercial_partner_id
        if partner.vat:
            payload['buyerVatNumber'] = self._ilyda_vat(partner.vat)
        token = key._sign_jws(payload)
        self.write({
            'l10n_gr_prov_offline_token': token,
            'l10n_gr_prov_qr_url': key._qr_url(token),
            'l10n_gr_prov_state': 'offline',
            'l10n_gr_prov_error': False,
            'l10n_gr_prov_send_datetime': fields.Datetime.now(),
        })
        self.message_post(body=_(
            'Ο πάροχος είναι μη προσβάσιμος — το παραστατικό εκδόθηκε με offline '
            'QR (TF-1, κλειδί %(kid)s). Πρέπει να διαβιβαστεί έως το τέλος της '
            'επόμενης ημέρας (Α.1112/2025)· οι επαναπροσπάθειες γίνονται '
            'αυτόματα κάθε 10 λεπτά.', kid=key.key_identifier))
        return True

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _l10n_gr_prov_ilyda_series_serial(self):
        """Split the Odoo sequence into (series, serial) exactly as submitted.
        The UID computation reuses this — it must stay byte-identical to what
        the payload sends."""
        self.ensure_one()
        name_parts = (self.name or '').split('/')
        series = ('_'.join(name_parts[:-1]) or self.journal_id.code)[:50]
        serial = name_parts[-1] or str(self.sequence_number or 0)
        return series, serial

    def _l10n_gr_prov_ilyda_uid_candidates(self):
        """The document UID as ILYDA computes it (A.1035 Appendix B2 / ET-7):

            SHA-1( ISO-8859-7( vat-YYYY-MM-DD-branch-type-series-serial ) )

        dash-separated, ISO date, bare VAT, effective submitted invoice type.
        Format confirmed empirically against all 54 provider-returned
        identifiers on the test database (2026-07-17); the recovery self-check
        keeps guarding it on every marked document.
        """
        self.ensure_one()
        series, serial = self._l10n_gr_prov_ilyda_series_serial()
        text = '-'.join([
            self._ilyda_vat(self.company_id.vat, prefixed=False),
            str(self.invoice_date or ''),
            str(self.company_id.partner_id.l10n_gr_edi_branch_number or 0),
            self._l10n_gr_prov_ilyda_inv_type() or '',
            series, serial,
        ])
        # (named digest, not uid: see the frame-inspection note in recover)
        digest = hashlib.sha1(text.encode('iso-8859-7', 'replace')).hexdigest()
        return [('A.1035-B2', digest)]

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
            # Retail refunds (ΠΛΑ journal) are 11.4 and POS card refunds (ΠΟΣΕ)
            # are 8.5 — neither is a 5.x credit note.
            journal_default = self.journal_id.l10n_gr_edi_inv_type_default
            if journal_default in ('11.4', '8.5'):
                return journal_default
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
        if (self.l10n_gr_prov_is_dispatch
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
        if inv_type == '8.6' and not self.l10n_gr_prov_table_aa:
            errors.append(_(
                'Το Δελτίο Παραγγελίας Εστίασης (8.6) απαιτεί ΑΑ Τραπεζιού.'))
        if inv_type in TYPES_DISPATCH_CORRELATED:
            corr = self.l10n_gr_edi_correlation_id
            if not corr or not corr.l10n_gr_prov_mark:
                errors.append(_(
                    'Ο τύπος %s είναι συσχετιζόμενο δελτίο — επιλέξτε το '
                    'συσχετιζόμενο παραστατικό (με MARK) στο πεδίο '
                    '«Correlated Invoice».', inv_type))
            # 10.1 (ILYDA err 320): the correlated document must be a delivery
            # note (9.x / ΤΔΑ) or a 10.2 — not an invoice.
            elif inv_type == '10.1':
                corr_type = corr.l10n_gr_edi_inv_type
                if not (corr_type in TYPES_DISPATCH
                        or corr.journal_id.l10n_gr_prov_delivery_note):
                    errors.append(_(
                        'Το συσχετιζόμενο παραστατικό του Δελτίου Ποσοτικής '
                        'Παραλαβής (10.1) πρέπει να είναι Δελτίο Αποστολής '
                        '(9.1/9.2/9.3) ή 10.2 — όχι τιμολόγιο.'))
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
        # 8.2 Ειδικό Στοιχείο Τέλους Διαμονής: the fee IS the document — one
        # zero-value line, the amount only in Λοιποί Φόροι, correlated with
        # the stay document (cf. examples_bundle/VALID_8_2_example.json).
        if inv_type == '8.2':
            if not (self.l10n_gr_prov_other_taxes_amount
                    and self.l10n_gr_prov_other_taxes_category):
                errors.append(_(
                    'Το Ειδικό Στοιχείο (8.2) απαιτεί κατηγορία και ποσό στους '
                    'Λοιπούς Φόρους (τέλος διαμονής/ανθεκτικότητας) — '
                    'καρτέλα myDATA Φόροι.'))
            if (self.l10n_gr_prov_fees_amount or self.l10n_gr_prov_stamp_duty_amount
                    or self.l10n_gr_prov_withholding_amount):
                errors.append(_(
                    'Το Ειδικό Στοιχείο (8.2) επιτρέπει μόνο Λοιπούς Φόρους — '
                    'όχι Τέλη, Χαρτόσημο ή Κρατήσεις.'))
            if len(lines) != 1 or any(l.price_subtotal for l in lines):
                errors.append(_(
                    'Το Ειδικό Στοιχείο (8.2) θέλει ακριβώς μία γραμμή με '
                    'μηδενική αξία (περιγραφή τέλους) — το ποσό μπαίνει μόνο '
                    'στους Λοιπούς Φόρους.'))
            corr = self.l10n_gr_edi_correlation_id
            if not corr or not corr.l10n_gr_prov_mark:
                errors.append(_(
                    'Το Ειδικό Στοιχείο (8.2) συσχετίζεται με το παραστατικό '
                    'διαμονής (ΑΛΠ/ΤΠΥ με MARK) — επιλέξτε το στο πεδίο '
                    '«Correlated Invoice».'))
        # 1.5 Εκκαθάριση Πωλήσεων Τρίτων: every line carries an Επισήμανση and
        # the document needs both kinds — the cleared third-party sales (1) and
        # the agent's commission (2). AADE MDP-0083 / MDP-0084.
        if inv_type == '1.5':
            marks = {l.l10n_gr_prov_detail_type for l in lines}
            if None in marks or False in marks:
                errors.append(_(
                    'Εκκαθάριση Πωλήσεων Τρίτων (1.5): κάθε γραμμή χρειάζεται '
                    'Επισήμανση (1 Εκκαθάριση Πωλήσεων Τρίτων ή 2 Αμοιβή από '
                    'Πωλήσεις Τρίτων) — συμπληρώστε τη στήλη «Επισήμανση».'))
            elif not {'1', '2'} <= marks:
                errors.append(_(
                    'Εκκαθάριση Πωλήσεων Τρίτων (1.5): απαιτείται τουλάχιστον '
                    'μία γραμμή με Επισήμανση 1 (αξία πωλήσεων τρίτων) και μία '
                    'με Επισήμανση 2 (αμοιβή εκκαθαριστή).'))

        # Dispatch types (9.x/10.x) classify with category3 only; associate
        # types (1.6/2.4 — CLASSIFICATION_MAP sentinel, no valid categories)
        # inherit their classification from the correlated invoice.
        no_cls = (inv_type in TYPES_NO_CLASSIFICATION or inv_type in TYPES_DISPATCH
                  or not valid_cls_categories(inv_type))
        no_vat = inv_type in TYPES_NO_VAT
        # Rows that carry a quantity: the XSD types it minExclusive 0, so a zero
        # or negative one has AADE reject the whole document with an error that
        # never names the line. Caught here instead.
        sends_quantity = self._l10n_gr_prov_sends_quantity(inv_type)
        for line in lines:
            line_label = line.name or line.product_id.display_name
            if sends_quantity and (line.quantity or 0) <= 0:
                errors.append(_(
                    'Γραμμή «%s»: η ποσότητα πρέπει να είναι μεγαλύτερη του '
                    'μηδενός σε παραστατικό που διαβιβάζει ποσότητες '
                    '(διακίνηση, δελτίο αποστολής, δελτίο παραγγελίας). '
                    'Διορθώστε την ή διαγράψτε τη γραμμή.', line_label))
            # E3 is required only when the category takes one — the *_95 and
            # category3 groups are E3-less by spec (e.g. category1_95 on 8.2).
            cls_cat = line.l10n_gr_prov_cls_category
            if not no_cls and (not cls_cat or (
                    not line.l10n_gr_prov_cls_type
                    and valid_cls_types(inv_type, cls_cat))):
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
        # Counterpart required for B2B types (and self-billed 3.1/3.2, whose
        # counterpart is the individual's ΑΦΜ); forbidden for retail/no-VAT types
        # 9.2 is exempt: it is transmitted with the generic ΑΦΜ 000000000.
        if ((self.is_sale_document() or inv_type in TYPES_SELF_BILLED)
                and inv_type not in TYPES_NO_BUYER
                and inv_type != '9.2'
                and not self.commercial_partner_id.vat):
            errors.append(_(
                'Invoice type %s requires a counterpart with a VAT/ΑΦΜ number '
                '(mandatory). Set the ΑΦΜ on the vendor/customer.', inv_type))
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
        # Dispatch documents carry loading/delivery addresses, and every part of
        # them is mandatory (MDP-0026) — as is the seller's street number
        # (BT-36, MDP-0024). The number is the one that actually goes missing:
        # Odoo has no field for it, so «Γεωργαντά 22» lands whole in `street`.
        if ((inv_type in TYPES_DISPATCH or self.journal_id.l10n_gr_prov_delivery_note)
                and inv_type not in TYPES_RECEIPT):
            ship = self.partner_shipping_id or self.commercial_partner_id
            for who, party in (
                    (_('της εταιρείας (διεύθυνση φόρτωσης)'), company_partner),
                    (_('του παραλήπτη (διεύθυνση παράδοσης)'), ship)):
                street, number = party._l10n_gr_prov_street_number()
                missing = [label for label, value in (
                    (_('οδός'), street), (_('αριθμός'), number),
                    (_('πόλη'), party.city), (_('Τ.Κ.'), party.zip)) if not value]
                if missing:
                    errors.append(_(
                        'Δελτίο διακίνησης: λείπει %(fields)s από τη διεύθυνση '
                        '%(who)s «%(name)s». Συμπληρώστε τα στην καρτέλα της '
                        'επαφής — ο αριθμός στο πεδίο «Αριθμός».',
                        fields=', '.join(missing), who=who, name=party.display_name))
        if errors:
            raise UserError('\n'.join(errors))

    def _l10n_gr_prov_sends_quantity(self, inv_type):
        """True when the row payload will carry `quantity` — kept in step with
        the condition in the payload builder, and extended by the restaurant
        module for documents matched against catering notes."""
        self.ensure_one()
        return bool(inv_type in TYPES_DISPATCH or inv_type == '8.6'
                    or self.journal_id.l10n_gr_prov_delivery_note)

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
        is_dispatch_type = inv_type in TYPES_DISPATCH
        is_delivery_note = self.journal_id.l10n_gr_prov_delivery_note
        no_vat = inv_type in TYPES_NO_VAT
        no_cls = (inv_type in TYPES_NO_CLASSIFICATION or is_dispatch_type
                  or not valid_cls_categories(inv_type))

        # ── Lines, VAT breakdown buckets, classifications ────────────────────
        invoice_lines, row_types = [], []
        vat_buckets = {}      # (rate, aade_vat_category, exemption) -> [taxable, tax]
        cls_totals = {}       # (category, cls_type) -> amount
        for number, line in enumerate(lines, start=1):
            net = _r2(line.price_subtotal)
            vat_amount = _r2(line.price_total - line.price_subtotal)
            tax = line.tax_ids[:1]
            rate = tax.amount if tax else 0.0
            if is_dispatch_type:
                # dispatch notes carry no values (MDP-0011..0015): zero the
                # money side, keep quantities/descriptions
                net = vat_amount = rate = 0.0
            elif no_vat:
                # no-VAT types (e.g. 3.1/3.2 Τίτλος Κτήσης): line VAT must be 0
                # even if the line carries a tax (MDP-0014); net stays real.
                vat_amount = rate = 0.0

            aade_vat_cat, category_code = _vat_category(tax, inv_type)

            exemption = (
                line.l10n_gr_prov_vat_exemption if aade_vat_cat == 7 else None
            ) or None

            key = (rate, aade_vat_cat, exemption)
            bucket = vat_buckets.setdefault(key, [0.0, 0.0])
            bucket[0] += net
            bucket[1] += vat_amount

            # E3 code is sent only when valid for this type+category; the
            # category*_95 groups (e.g. 8.6 restaurant orders) take none.
            cls_cat = line.l10n_gr_prov_cls_category
            cls_type = line.l10n_gr_prov_cls_type
            valid = valid_cls_types(inv_type, cls_cat) if cls_cat else frozenset()
            if cls_type and cls_type not in valid:
                cls_type = False
            # Category needs an E3 but the line has none (created off the onchange
            # path, e.g. a copy): fall back to the preferred code (MDP-0001).
            if not cls_type and valid:
                cls_type = preferred_e3(inv_type, valid)
            # category2_* are expense categories (e.g. 3.1 Τίτλος Κτήσης) and
            # must go in expensesClassification; category1_*/category3 are income.
            is_expense_cls = bool(cls_cat) and cls_cat.startswith('category2')
            line_cls = []
            if not no_cls and cls_cat:
                cls_totals[(cls_cat, cls_type)] = _r2(
                    cls_totals.get((cls_cat, cls_type), 0.0) + net)
                entry = {'classificationCategory': cls_cat, 'amount': net}
                if cls_type:
                    entry['classificationType'] = cls_type
                line_cls = [entry]

            discount_pct = line.discount or 0.0
            discount_amount = 0.0 if is_dispatch_type else _r2(
                line.price_unit * line.quantity * discount_pct / 100.0)

            line_vals = {
                'lineNumber': number,
                'note': '',
                'invoicedQuantity': line.quantity,
                'invoicedQuantityUnits': line._l10n_gr_prov_quantity_units(),
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
            # §8.15 Επισήμανση — mandatory on 1.5 (MDP-0083)
            if line.l10n_gr_prov_detail_type:
                row_type['invoiceDetailType'] = int(line.l10n_gr_prov_detail_type)
            # dispatch rows AND restaurant order notes (8.6) need item
            # description/quantity/unit — also on combined invoice+ΔΑ documents
            if is_dispatch_type or is_delivery_note or inv_type == '8.6':
                row_type['itemDescr'] = (line.product_id.name or line.name or '')[:200]
                row_type['quantity'] = line.quantity
                unit_code, unit_title = line._l10n_gr_prov_measurement_unit()
                row_type['measurementUnit'] = unit_code
                if unit_code == 7:
                    # §8.13 note 9: code 7 must carry the real unit name and
                    # the count it corresponds to — the pair reads «500_g»,
                    # the same shape as the guide's «3_Παλέτες».
                    # ponytail: the guide means the *packaging* count, with
                    # quantity staying the item count. We send the same number
                    # for both because Odoo has no packaging unit here. Nothing
                    # validates it; give the uom its §8.13 code (Μονάδες
                    # Μέτρησης → Είδος Ποσότητας) and code 7 never fires.
                    row_type['otherMeasurementUnitTitle'] = unit_title
                    row_type['otherMeasurementUnitQuantity'] = max(
                        int(line.quantity or 0), 1)
            # myDATA requires document- and row-level classification to match
            # (MDP-0004/0006). 3.1/3.2 forbid row-level *income* (MDP-0040), but
            # their expense classification must be present at the row too.
            if line_cls:
                row_type['expensesClassification' if is_expense_cls
                         else 'incomeClassification'] = line_cls
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

        income_classifications, expenses_classifications = [], []
        for (cat, cls_type), amount in cls_totals.items():
            entry = {'classificationCategory': cat, 'amount': amount}
            if cls_type:
                entry['classificationType'] = cls_type
            (expenses_classifications if cat.startswith('category2')
             else income_classifications).append(entry)

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
        # B2G: Παρακρατήσεις Φόρου Εισοδήματος and Κρατήσεις Υπέρ Τρίτων Φορέων
        # του Ελλην. Δημοσίου must NOT fill the numeric BG-20/BG-21 fields — they
        # go as plain text in BG-24 and leave every total untouched (Εθνικός
        # Μορφότυπος PEPPOL BIS v8.0, BG-20 note + §BT-122/123; cf.
        # examples_bundle/test_b2g_advanced_allowances_and_charges_aadeData.json,
        # where docLevelAllowances is null next to an additionalSupportDocs entry).
        b2g = bool(self.l10n_gr_prov_b2g)
        wh_allowance = 0.0 if b2g else withholding
        # Κρατήσεις Υπέρ Τρίτων = myDATA Κρατήσεις (taxType 5): they reduce the
        # AADE gross and nothing on the EN16931 side. ILYDA checks exactly that
        # gap — BT-112 minus every BG-24 παρακράτηση must equal
        # aadeTotalGrossValue (BG-22-MISMATCH).
        deductions = _r2(self.l10n_gr_prov_yper3_amount or 0.0) if b2g else 0.0
        total_without_vat = _r2(total_net + extra_charges - wh_allowance)  # BT-109
        total_with_vat = _r2(total_without_vat + total_vat)                # BT-112
        amount_due = total_with_vat                                        # BT-115
        aade_gross = _r2(                                                  # ET-25
            total_net + total_vat + extra_charges - withholding - deductions)

        # Withholding allowance: EN16931 mirror of taxTotals taxType=1, plus a
        # Z/0% VAT breakdown with negative taxable (as in ILYDA's example).
        doc_level_allowances = []
        additional_support_docs = []
        if withholding and b2g:
            additional_support_docs.append({
                'reference': withholding,
                'description': '##PARAKRAT|FOR|EISOD|%s##' % (
                    self.l10n_gr_prov_withholding_category or ''),
            })
        elif withholding:
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
        # Υπέρ Τρίτων: one single entry carrying the algebraic sum, never an
        # EN16931 total.
        if deductions:
            additional_support_docs.append({
                'reference': deductions,
                'description': '##PARAKRAT|YPER3##',
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
        # taxType 5 = Κρατήσεις; no category, no underlying value (ILYDA's
        # test_b2g_advanced_allowances_and_charges example).
        if deductions:
            tax_totals.append({'taxType': 5, 'taxAmount': deductions})

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
            'documentLevelAllowancesSum': wh_allowance,
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
                'aadeTotalDeductionsAmount': deductions,
            },
        }

        # ── 8.2 Ειδικό Στοιχείο Τέλους Διαμονής: the document IS the tax ─────
        # myDATA wants net 0 with the fee only in otherTaxes (recType 3 row),
        # but ILYDA's EN16931 validation rejects a tax above its underlying
        # value (MDP-0058) — so, per ILYDA's VALID_8_2 example, the fee rides
        # as the line base on the EN16931 side while the aadeData row carries
        # the true myDATA picture. Generic extra-tax taxTotals/charges and
        # classifications are dropped (recType 3 rows carry none).
        if inv_type == '8.2':
            fee = other_taxes
            line0 = invoice_lines[0]
            line0['netAmount'] = fee
            line0['priceDetails']['itemNetPrice'] = fee
            row0 = row_types[0]
            row0.update({
                'recType': 3,
                'netValue': 0.0,
                # MDP-0075: recType 3 rows take ONLY the category — the amount
                # goes in taxesTotals (cf. the example's XML).
                'otherTaxesPercentCategory': int(self.l10n_gr_prov_other_taxes_category),
            })
            row0.pop('incomeClassification', None)
            row0.pop('expensesClassification', None)
            for breakdown in vat_breakdowns:
                breakdown['categoryTaxableAmount'] = fee
            # underlyingValue = the EN16931 line base (= fee), so the
            # tax ≤ underlying check (MDP-0058) is satisfied.
            tax_totals[:] = [{
                'taxType': 3,
                'taxAmount': fee,
                'underlyingValue': fee,
                'taxCategory': int(self.l10n_gr_prov_other_taxes_category),
            }]
            doc_level_charges.clear()
            income_classifications.clear()
            expenses_classifications.clear()
            doc_total.update({
                'invoiceLinesNetAmountSum': fee,
                'invoiceTotalWithoutVat': fee,
                'invoiceTotalAmountWithVat': fee,
                'amountDueForPayment': fee,
                'documentLevelChargesSum': 0.0,
            })
            doc_total['aadeDocTotals'].update({
                'aadeTotalNetValue': 0.0,
                'aadeTotalGrossValue': fee,
            })

        # ── Seller ────────────────────────────────────────────────────────────
        company_partner = company.partner_id
        seller_street, seller_number = company_partner._l10n_gr_prov_street_number()
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
                'sellerAddressLine1': seller_street,
                'sellerAddressLine2': seller_number,   # BT-36, MDP-0024
                'sellerCity': company_partner.city or '',
                'sellerPostCode': company_partner.zip or '',
                'sellerCountrySubdivision': company_partner.state_id.name or '',
            },
        }

        # ── Buyer (B2B/B2G only; retail stays anonymous) ─────────────────────
        buyer = None
        # 9.2 Συγκεντρωτικό Δελτίο Αποστολής covers several deliveries at once,
        # so it has no single counterparty: AADE demands the generic ΑΦΜ
        # 000000000 (error 289 / MDP-0104) and the block is sent even when the
        # partner has no VAT of its own.
        is_aggregate_dn = inv_type == '9.2'
        if (partner.vat or is_aggregate_dn) and inv_type not in TYPES_NO_BUYER:
            buyer = {
                'buyerVatIdentifier':
                    '000000000' if is_aggregate_dn else self._ilyda_vat(partner.vat),
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
        series, serial = self._l10n_gr_prov_ilyda_series_serial()

        # ── AADE block ────────────────────────────────────────────────────────
        aade_data = {
            'aadeInvoiceTypeCode': inv_type,
            'invoiceRowTypes': row_types,
        }
        if inv_type == '8.6' and self.l10n_gr_prov_table_aa:
            aade_data['tableAA'] = self.l10n_gr_prov_table_aa
        if income_classifications:
            aade_data['incomeClassifications'] = income_classifications
        if expenses_classifications:
            aade_data['expensesClassifications'] = expenses_classifications
        if tax_totals:
            aade_data['taxTotals'] = tax_totals

        # Dispatch data: pure ΔΑ (9.x/10.x) or combined invoice+ΔΑ (ΤΔΑ/ΠΤΔΑ journals)
        if inv_type in TYPES_RECEIPT:
            # Δελτίο Ποσοτικής Παραλαβής (10.1/10.2): receipt side — movePurpose,
            # dispatchDate and otherDeliveryNoteHeader are forbidden; only the
            # receivingNotePurpose is sent (MDP-0107/0108/0111/0116).
            # Unprefixed on AadeData, like its sibling reverseDeliveryNotePurpose
            # (the aade-prefixed name is rejected as unknown by ILYDA).
            aade_data['receivingNotePurpose'] = int(
                self.l10n_gr_prov_receiving_purpose or '1')
        elif is_dispatch_type or is_delivery_note:
            if is_delivery_note:
                aade_data['isDeliveryNote'] = True
            aade_data['aadeMovePurpose'] = int(
                self.l10n_gr_prov_move_purpose
                or ('5' if self.move_type == 'out_refund' else '1'))
            if self.l10n_gr_prov_move_purpose == '19' and self.l10n_gr_prov_other_move_purpose:
                aade_data['otherMovePurposeTitle'] = self.l10n_gr_prov_other_move_purpose
            # Αντίστροφη Διακίνηση — accepted only for 9.3 (§5.3/§8.21)
            if inv_type == '9.3' and self.l10n_gr_prov_reverse_delivery:
                aade_data['reverseDeliveryNote'] = True
                aade_data['reverseDeliveryNotePurpose'] = int(
                    self.l10n_gr_prov_reverse_purpose or '1')
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
            ship_street, ship_number = ship._l10n_gr_prov_street_number()
            # MDP-0026: street/number/city/postalCode are all mandatory here
            load_addr = {
                'street': seller_street,
                'number': seller_number,
                'postalCode': company_partner.zip or '',
                'city': company_partner.city or '',
            }
            deliver_addr = {
                'street': ship_street,
                'number': ship_number,
                'postalCode': ship.zip or '',
                'city': ship.city or '',
            }
            # Return (σκοπός 5): goods travel back — swap the addresses
            if aade_data['aadeMovePurpose'] == 5:
                load_addr, deliver_addr = deliver_addr, load_addr
            aade_data['otherDeliveryNoteHeader'] = {
                'loadingAddress': load_addr,
                'deliveryAddress': deliver_addr,
            }
            if self.l10n_gr_prov_start_shipping_branch:
                aade_data['otherDeliveryNoteHeader']['startShippingBranch'] = \
                    int(self.l10n_gr_prov_start_shipping_branch)
            if self.l10n_gr_prov_complete_shipping_branch:
                aade_data['otherDeliveryNoteHeader']['completeShippingBranch'] = \
                    int(self.l10n_gr_prov_complete_shipping_branch)

        # Correlated MARK: credit notes via the reversal link, everything else
        # (9.1/10.1, ΔΑ→ΤΙΜ follow-ups) via the myDATA correlation field.
        # Forbidden for plain dispatch notes (MDP-0090): 9.2/9.3/10.2 — only the
        # correlated dispatch types (9.1/10.1) accept it.
        correlated_forbidden = (
            is_dispatch_type and inv_type not in TYPES_DISPATCH_CORRELATED)
        correlated = ((self.reversed_entry_id
                       if inv_type in TYPES_NEED_CORRELATED else None)
                      or self.l10n_gr_edi_correlation_id)
        if correlated and correlated.l10n_gr_prov_mark and not correlated_forbidden:
            aade_data['correlatedInvoices'] = [
                int(correlated.l10n_gr_prov_mark)
            ]

        payload = {
            'b2g': bool(self.l10n_gr_prov_b2g),
            'selfPricing': False,
            'vatPaidByBuyer': False,
            'invoiceTypeCode': (
                UBL_CREDIT_NOTE if inv_type in AADE_CREDIT_TYPES else UBL_INVOICE),
            'seriesNumber': series,
            'serialNumber': serial,
            'invoiceIssueDate': self._ilyda_issue_date(),
            'invoiceCurrencyCode': self.currency_id.name or 'EUR',
            # BT-15 is a plain EN16931 term, not a B2G one: ILYDA's transmission
            # failure 2 simulation is triggered by putting TF2_SENTINEL here.
            'receivingAdviceReference': self.l10n_gr_prov_receiving_advice_ref or None,
            'seller': seller,
            'buyer': buyer,
            'invoiceLines': invoice_lines,
            'vatBreakdowns': vat_breakdowns,
            'docTotal': doc_total,
            'docLevelAllowances': doc_level_allowances or None,
            'docLevelCharges': doc_level_charges or None,
            'additionalSupportDocs': additional_support_docs or None,
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
            origin_series, origin_serial = origin._l10n_gr_prov_ilyda_series_serial()
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
            budget_type = self.l10n_gr_prov_budget_type or '1'
            if inv_type == '5.2':
                # Uncorrelated credit notes carry routing only, not the funding
                # reference: '1' / '3' bare, '2|<Ενάριθμος>' for ΠΔΕ. Sending
                # '1|<ΑΔΑ>' here is rejected as BT-11-INVALID-FOR-CREDIT-NOTE.
                # (The national guide puts this string in BG-24/BT-122 instead;
                # ILYDA validates it on BT-11 — asked them to confirm.)
                project_ref = (
                    f'2|{self.l10n_gr_prov_budget_ref}'
                    if budget_type == '2' and self.l10n_gr_prov_budget_ref
                    else budget_type)
            elif self.l10n_gr_prov_budget_ref:
                project_ref = f'{budget_type}|{self.l10n_gr_prov_budget_ref}'
            else:
                project_ref = None
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

    # TF-2: ILYDA accepted the document but AADE was unreachable — it is queued
    # at the provider. MQ001 = already queued (re-submission), MQ002 = queued now.
    _ILYDA_QUEUE_CODES = {'MQ001', 'MQ002'}

    def _l10n_gr_prov_ilyda_write_marking(self, marking):
        self.write({
            'l10n_gr_prov_mark': str(marking.get('mark')),
            'l10n_gr_prov_invoice_id': marking.get('invoiceId'),
            'l10n_gr_prov_verification_hash': marking.get('verificationHash'),
            'l10n_gr_prov_invoice_identifier': marking.get('invoiceIdentifier'),
            'l10n_gr_prov_qr_url': marking.get('qrCode'),
            'l10n_gr_prov_provider_url': marking.get('providerUrl'),
            'l10n_gr_prov_previously_submitted': bool(marking.get('aadePreviouslySubmittedError228')),
        })
        if marking.get('invoiceIdentifier'):
            self.l10n_gr_prov_uid = marking['invoiceIdentifier'].lower()

    def _l10n_gr_prov_ilyda_handle_response(self, data):
        """Process a submit response. Returns 'sent' or 'queued' (TF-2)."""
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
        codes = {e.get('code') for e in errors}

        if non_fatal:
            self.message_post(body=_(
                'ILYDA non-fatal warnings: %s',
                '; '.join(self._l10n_gr_prov_ilyda_format_error(e) for e in non_fatal)))

        if not marking.get('mark') and codes & self._ILYDA_QUEUE_CODES:
            # Queued, not rejected — MQ002 arrives together with fatal-flagged
            # I9999/I0004, so this must be checked before the fatal guard. The
            # response carries the identifier + QR that the printed document
            # must bear; the MARK arrives later via the recovery poll.
            identifier = marking.get('invoiceIdentifier')
            if identifier or self.l10n_gr_prov_invoice_identifier:
                self.write({
                    'l10n_gr_prov_invoice_id':
                        marking.get('invoiceId') or self.l10n_gr_prov_invoice_id,
                    'l10n_gr_prov_invoice_identifier':
                        identifier or self.l10n_gr_prov_invoice_identifier,
                    'l10n_gr_prov_qr_url':
                        marking.get('qrCode') or self.l10n_gr_prov_qr_url,
                })
                if identifier:
                    self.l10n_gr_prov_uid = identifier.lower()
                return 'queued'
            # Queue code without any identifier: nothing to print or poll with.
            raise UserError(_(
                'ILYDA queued the document but returned no identifier: %s',
                '; '.join(self._l10n_gr_prov_ilyda_format_error(e) for e in errors)))

        if fatal or not marking.get('mark'):
            details = '; '.join(
                self._l10n_gr_prov_ilyda_format_error(e) for e in (fatal or errors)
            ) or _('No marking returned by the provider.')
            raise UserError(_('ILYDA rejected the document: %s', details))

        if 'I0008' in codes:
            # Same invoice number was already marked — the response carries the
            # original marking. Expected after a lost response; not a new issue.
            self.message_post(body=_(
                'Ο πάροχος αναγνώρισε προηγούμενη έκδοση του παραστατικού (I0008) '
                'και επέστρεψε το αρχικό MARK.'))
        self._l10n_gr_prov_ilyda_write_marking(marking)
        return 'sent'
