# -*- coding: utf-8 -*-
"""Offline QR signing keys — TF-1 (Α.1112/2025).

When the provider is unreachable at issue time, the ERP may still hand the
customer a printed document bearing an offline QR: a JWS (HS256) token signed
locally with an HMAC key the provider issued beforehand. This model stores
those keys and their lifecycle (issue → verify installation → revoke). The
secret is returned by the provider exactly once, at issue time.

The HTTP calls are provider-specific and dispatched to the driver module
(_offline_key_<operation>_<provider>); the JWS signing itself is generic
RFC 7515 and lives here.
"""
import base64
import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class L10nGrProvOfflineKey(models.Model):
    _name = 'l10n.gr.prov.offline.key'
    _description = 'Κλειδί Offline QR (TF-1)'
    _order = 'id desc'
    _rec_name = 'key_identifier'

    company_id = fields.Many2one(
        'res.company', string='Εταιρεία', required=True,
        default=lambda self: self.env.company)
    purpose = fields.Char(
        string='Σκοπός', default='Odoo ERP',
        help='Ελεύθερη περιγραφή της εγκατάστασης που θα υπογράφει με το κλειδί.')
    key_identifier = fields.Char(string='Αναγνωριστικό Κλειδιού', readonly=True, copy=False)
    key_version = fields.Integer(string='Έκδοση', readonly=True, copy=False)
    secret = fields.Char(
        readonly=True, copy=False, groups='base.group_system',
        help='Base64url HMAC κλειδί — επιστρέφεται από τον πάροχο ΜΟΝΟ κατά την '
             'έκδοση. Αν χαθεί, ανακαλέστε το κλειδί και εκδώστε νέο.')
    algorithm = fields.Char(readonly=True, copy=False, default='OFFLINE_QR_JWS')
    status = fields.Selection([
        ('issued', 'Εκδόθηκε'),
        ('verified', 'Επαληθευμένο'),
        ('revoked', 'Ανακλήθηκε'),
    ], string='Κατάσταση', readonly=True, copy=False)
    valid_from = fields.Datetime(string='Ισχύει Από', readonly=True, copy=False)
    valid_to = fields.Datetime(string='Ισχύει Έως', readonly=True, copy=False)
    installation_verified_at = fields.Datetime(
        string='Επαλήθευση Εγκατάστασης', readonly=True, copy=False)
    link_base_url = fields.Char(string='Link Base URL', readonly=True, copy=False)

    # ── Lifecycle actions (HTTP via the driver) ──────────────────────────────

    def _offline_key_dispatch(self, operation):
        self.ensure_one()
        provider = (self.company_id or self.env.company).l10n_gr_prov_provider
        handler = getattr(self, f'_offline_key_{operation}_{provider}', None)
        if handler is None:
            raise UserError(_(
                'The configured provider "%s" does not implement offline-QR '
                'key management ("%s").', provider, operation))
        return handler()

    def action_issue(self):
        for key in self:
            if key.key_identifier:
                raise UserError(_('Το κλειδί έχει ήδη εκδοθεί (%s).', key.key_identifier))
            key._offline_key_dispatch('issue')

    def action_verify(self):
        for key in self:
            if not key.key_identifier:
                raise UserError(_('Εκδώστε πρώτα το κλειδί.'))
            key._offline_key_dispatch('verify')

    def action_revoke(self):
        for key in self:
            if not key.key_identifier:
                raise UserError(_('Το κλειδί δεν έχει εκδοθεί.'))
            key._offline_key_dispatch('revoke')

    # ── Selection for signing ────────────────────────────────────────────────

    @api.model
    def _get_active_key(self, company):
        """Newest verified key whose validity window covers now, or empty."""
        now = fields.Datetime.now()
        return next(iter(self.search([
            ('company_id', '=', company.id),
            ('status', '=', 'verified'),
        ]).filtered(
            lambda k: (not k.valid_from or k.valid_from < now)
            and (not k.valid_to or now <= k.valid_to)
        )), self.browse())

    # ── JWS (RFC 7515, HS256, base64url unpadded) ────────────────────────────

    def _sign_jws(self, payload):
        """Return the signed offline-QR token for `payload` (a dict)."""
        self.ensure_one()
        secret = self.sudo().secret
        if not secret:
            raise UserError(_('Το μυστικό του κλειδιού δεν είναι αποθηκευμένο — '
                              'ανακαλέστε το και εκδώστε νέο.'))
        if self.status != 'verified':
            # TQR-0017: tokens signed with an unverified key fail on scan.
            raise UserError(_('Το κλειδί δεν έχει επαληθευμένη εγκατάσταση.'))

        def b64u(raw):
            return base64.urlsafe_b64encode(raw).rstrip(b'=').decode()

        def dump(obj):
            return json.dumps(obj, separators=(',', ':'), ensure_ascii=False).encode()

        header = {'alg': 'HS256', 'typ': self.algorithm or 'OFFLINE_QR_JWS',
                  'kid': self.key_identifier}
        signing_input = f'{b64u(dump(header))}.{b64u(dump(payload))}'
        key_bytes = base64.urlsafe_b64decode(secret + '=' * (-len(secret) % 4))
        signature = hmac.new(key_bytes, signing_input.encode(), hashlib.sha256).digest()
        return f'{signing_input}.{b64u(signature)}'

    def _qr_url(self, token):
        self.ensure_one()
        base = (self.link_base_url or '').rstrip('/')
        return f'{base}/{self.algorithm or "OFFLINE_QR_JWS"}/{token}'

    # ── Helpers for driver responses ─────────────────────────────────────────

    @staticmethod
    def _parse_provider_ts(value):
        """Provider timestamps arrive as epoch-seconds-with-decimals (issue
        response) OR ISO-8601 UTC strings (list/verify) — normalize to the
        naive-UTC datetimes Odoo stores."""
        if not value:
            return False
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, tz=timezone.utc).replace(tzinfo=None)
        try:
            parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        except ValueError:
            return False
        if parsed.tzinfo:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed
