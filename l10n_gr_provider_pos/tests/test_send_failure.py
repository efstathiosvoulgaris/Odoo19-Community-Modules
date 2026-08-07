# -*- coding: utf-8 -*-
"""What a failed transmission costs, per till (pos.config.l10n_gr_prov_send_failure).

No provider is contacted: the send is replaced by one that always raises, which
is exactly the situation the option exists for.
"""
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

_SEND = ('odoo.addons.l10n_gr_provider_base.models.account_move'
         '.AccountMove._l10n_gr_prov_try_send')


@tagged('post_install', '-at_install')
class TestPosSendFailure(TransactionCase):

    def setUp(self):
        super().setUp()
        order = self.env['pos.order'].search(
            [('account_move', '!=', False),
             ('config_id.l10n_gr_prov_alp_journal_id', '!=', False)], limit=1)
        if not order:
            self.skipTest('no provider POS order in this database')
        self.order = order
        # An already-marked document is never re-sent, so work on an unmarked
        # copy of it (rolled back with the test transaction).
        self.order.account_move = order.account_move.copy()
        self.assertFalse(self.order.account_move.l10n_gr_prov_mark)

    def _run(self, mode):
        self.order.config_id.l10n_gr_prov_send_failure = mode
        with patch(_SEND, autospec=True,
                   side_effect=Exception('provider unreachable')):
            return self.order._l10n_gr_prov_pos_send()

    def test_ignore_swallows(self):
        self.assertIsNone(self._run('ignore'),
                          'service must not stop for a provider failure')

    def test_warn_swallows(self):
        self.assertIsNone(self._run('warn'),
                          'warn is rendered by the front end, not by raising')

    def test_block_raises(self):
        with self.assertRaises(UserError):
            self._run('block')
