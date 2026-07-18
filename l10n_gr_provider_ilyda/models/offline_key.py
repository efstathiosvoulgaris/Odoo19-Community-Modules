# -*- coding: utf-8 -*-
"""ILYDA driver for the offline-QR key lifecycle (TF-1).

Endpoints: POST/GET/DELETE /api/offline-qr/{vat}/keys and
POST .../keys/{kid}/verify. The secret comes back only from the issue call.
"""
import logging

from odoo import fields, models, _
from odoo.exceptions import UserError

from .account_move import IlydaClient

_logger = logging.getLogger(__name__)


class L10nGrProvOfflineKey(models.Model):
    _inherit = 'l10n.gr.prov.offline.key'

    def _ilyda_key_vat(self):
        vat = ((self.company_id or self.env.company).vat or '').replace(' ', '').upper()
        return vat[2:] if vat[:2] in ('EL', 'GR') else vat

    @staticmethod
    def _ilyda_key_check(data):
        """Key endpoints answer with the key object on success; anything with
        an error code/list is a failure."""
        if not isinstance(data, dict) or data.get('code') or data.get('errors'):
            raise UserError(_('ILYDA offline-key call failed: %s', str(data)[:400]))
        return data

    def _offline_key_issue_ilyda(self):
        self.ensure_one()
        client = IlydaClient(self.company_id or self.env.company)
        data = self._ilyda_key_check(
            client.issue_offline_key(self._ilyda_key_vat(), self.purpose))
        self.write({
            'key_identifier': data.get('keyIdentifier'),
            'key_version': data.get('keyVersion') or 0,
            'secret': data.get('secret'),
            'algorithm': data.get('algorithm') or 'OFFLINE_QR_JWS',
            'status': 'issued',
            'valid_from': self._parse_provider_ts(data.get('validFrom')),
            'valid_to': self._parse_provider_ts(data.get('validTo')),
            'link_base_url': data.get('linkBaseUrl'),
        })
        _logger.info('Offline QR key issued: %s (v%s)',
                     self.key_identifier, self.key_version)

    def _offline_key_verify_ilyda(self):
        self.ensure_one()
        client = IlydaClient(self.company_id or self.env.company)
        data = self._ilyda_key_check(
            client.verify_offline_key(self._ilyda_key_vat(), self.key_identifier))
        self.write({
            'status': 'verified',
            'installation_verified_at':
                self._parse_provider_ts(data.get('installationVerifiedAt'))
                or fields.Datetime.now(),
            # list/verify summaries may re-send the validity window — keep it fresh
            'valid_from': self._parse_provider_ts(data.get('validFrom')) or self.valid_from,
            'valid_to': self._parse_provider_ts(data.get('validTo')) or self.valid_to,
            'link_base_url': data.get('linkBaseUrl') or self.link_base_url,
        })

    def _offline_key_revoke_ilyda(self):
        self.ensure_one()
        client = IlydaClient(self.company_id or self.env.company)
        data = client.revoke_offline_key(self._ilyda_key_vat(), self.key_identifier)
        # response is a summary or {"revoked": n}; treat error bodies as failure
        if isinstance(data, dict) and data.get('code'):
            raise UserError(_('ILYDA offline-key call failed: %s', str(data)[:400]))
        self.write({'status': 'revoked'})
