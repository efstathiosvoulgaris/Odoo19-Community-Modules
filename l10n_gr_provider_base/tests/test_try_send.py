# -*- coding: utf-8 -*-
"""_l10n_gr_prov_try_send: the state machine around one transmission.

No provider is contacted — the driver dispatch is replaced, so every branch
(sent / queued / duplicate-guard / offline fallback / error) is exercised
without credentials, network, or a configured company.
"""
from unittest.mock import patch

from odoo.tests import TransactionCase, tagged

from odoo.addons.l10n_gr_provider_base.models.gr_mydata import ProviderUnreachableError

_DISPATCH = ('odoo.addons.l10n_gr_provider_base.models.account_move'
             '.AccountMove._l10n_gr_prov_dispatch')


@tagged('post_install', '-at_install')
class TestTrySend(TransactionCase):

    def setUp(self):
        super().setUp()
        self.move = self.env['account.move'].create({'move_type': 'out_invoice'})
        self.calls = []

    def _send(self, results, **kwargs):
        """Run one send with the driver replaced by `results`: {operation: value}.
        A value that is an exception instance is raised instead of returned."""
        def fake(record, operation):
            self.calls.append(operation)
            outcome = results.get(operation)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome
        with patch(_DISPATCH, autospec=True, side_effect=fake):
            return self.move._l10n_gr_prov_try_send(**kwargs)

    # ── happy paths ──────────────────────────────────────────────────────────
    def test_sent(self):
        self.move.l10n_gr_prov_error = 'stale failure'
        self._send({'send': 'sent'})
        self.assertEqual(self.move.l10n_gr_prov_state, 'sent')
        self.assertFalse(self.move.l10n_gr_prov_error, 'old error must be cleared')
        self.assertTrue(self.move.l10n_gr_prov_send_datetime)

    def test_driver_returning_none_counts_as_sent(self):
        self._send({'send': None})
        self.assertEqual(self.move.l10n_gr_prov_state, 'sent')

    def test_queued(self):
        """TF-2: provider accepted it, AADE is down. Not an error, not marked."""
        self._send({'send': 'queued'})
        self.assertEqual(self.move.l10n_gr_prov_state, 'queued')
        self.assertFalse(self.move.l10n_gr_prov_error)
        self.assertTrue(self.move.l10n_gr_prov_send_datetime)

    # ── duplicate guard ──────────────────────────────────────────────────────
    def test_fresh_document_is_not_looked_up(self):
        self._send({'send': 'sent'})
        self.assertEqual(self.calls, ['send'], 'no recover call on a first send')

    def test_failed_document_is_recovered_before_resend(self):
        """A previous attempt may have landed — adopt it, never send twice."""
        self.move.l10n_gr_prov_state = 'error'
        self._send({'recover': 'sent', 'send': 'sent'})
        self.assertEqual(self.calls, ['recover'], 'must NOT resend after adopting')

    def test_unknown_at_provider_is_resent(self):
        self.move.l10n_gr_prov_state = 'error'
        self._send({'recover': False, 'send': 'sent'})
        self.assertEqual(self.calls, ['recover', 'send'])
        self.assertEqual(self.move.l10n_gr_prov_state, 'sent')

    def test_failed_lookup_does_not_resend(self):
        """If we cannot verify, we do not risk a duplicate at AADE."""
        self.move.l10n_gr_prov_state = 'error'
        self._send({'recover': Exception('lookup 500'), 'send': 'sent'})
        self.assertEqual(self.calls, ['recover'])
        self.assertEqual(self.move.l10n_gr_prov_state, 'error')
        self.assertIn('lookup 500', self.move.l10n_gr_prov_error)

    def test_marked_document_skips_the_guard(self):
        self.move.write({'l10n_gr_prov_state': 'error', 'l10n_gr_prov_mark': '4001'})
        self._send({'send': 'sent'})
        self.assertEqual(self.calls, ['send'])

    # ── failure ──────────────────────────────────────────────────────────────
    def test_failure_is_stored_not_raised(self):
        self.assertIsNone(self._send({'send': Exception('boom')}))
        self.assertEqual(self.move.l10n_gr_prov_state, 'error')
        self.assertIn('boom', self.move.l10n_gr_prov_error)

    def test_failure_raises_when_asked(self):
        with self.assertRaises(Exception):
            self._send({'send': Exception('boom')}, raise_on_error=True)

    def test_offline_document_stays_offline_through_a_failed_retry(self):
        """The printed QR and the retry cron both key on the 'offline' state."""
        self.move.write({'l10n_gr_prov_state': 'offline',
                         'l10n_gr_prov_offline_token': 'tok'})
        self._send({'recover': False, 'send': Exception('still down')})
        self.assertEqual(self.move.l10n_gr_prov_state, 'offline')
        self.assertIn('still down', self.move.l10n_gr_prov_error)

    def test_unreachable_provider_falls_back_to_offline(self):
        """TF-1: an already-issued offline QR covers the document — not an error."""
        self.move.write({'l10n_gr_prov_state': 'offline',
                         'l10n_gr_prov_offline_token': 'tok'})
        self._send({'recover': False,
                    'send': ProviderUnreachableError('no route')})
        self.assertEqual(self.move.l10n_gr_prov_state, 'offline')
        self.assertFalse(self.move.l10n_gr_prov_error,
                         'the fallback succeeded — nothing to report')

    def test_unreachable_without_a_key_fails_normally(self):
        """No offline key configured → the fallback must not mask the failure."""
        self._send({'send': ProviderUnreachableError('no route')})
        self.assertEqual(self.move.l10n_gr_prov_state, 'error')
        self.assertIn('no route', self.move.l10n_gr_prov_error)

    def test_missing_driver_is_a_readable_error(self):
        """No driver module for the configured provider — real dispatch, no
        network: getattr finds nothing and raises before any client is built."""
        self.move.company_id.l10n_gr_prov_provider = False
        self.move._l10n_gr_prov_try_send()
        self.assertEqual(self.move.l10n_gr_prov_state, 'error')
        self.assertTrue(self.move.l10n_gr_prov_error)
