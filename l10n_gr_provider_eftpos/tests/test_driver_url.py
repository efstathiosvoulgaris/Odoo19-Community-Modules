# -*- coding: utf-8 -*-
"""Which MegEftPos driver a terminal talks to.

Getting this wrong is silent and expensive: the charge goes to the wrong
till's terminal, or to a driver that isn't there, and the cashier only finds
out with a customer waiting.
"""
from odoo.tests.common import TransactionCase


class TestDriverUrl(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.l10n_gr_prov_eft_driver_url = 'http://company:8187'
        cls.Terminal = cls.env['l10n.gr.prov.eft.terminal']

    def _terminal(self, **vals):
        return self.Terminal.new(dict({
            'name': 'Ταμείο',
            'code': 'T1',
            'company_id': self.company.id,
            'pos_protocol': 'EDPS_JSON',
        }, **vals))

    def test_falls_back_to_company(self):
        """No per-terminal URL: the company one, exactly as before 1.10."""
        terminal = self._terminal()
        self.assertEqual(terminal._l10n_gr_prov_driver_url(), 'http://company:8187')

    def test_terminal_url_wins(self):
        terminal = self._terminal(driver_url='http://192.168.1.50:8187')
        self.assertEqual(terminal._l10n_gr_prov_driver_url(), 'http://192.168.1.50:8187')

    def test_two_tills_do_not_share(self):
        """The whole point of the change: one driver per till."""
        a = self._terminal(driver_url='http://192.168.1.50:8187')
        b = self._terminal(driver_url='http://192.168.1.51:8187')
        self.assertNotEqual(a._l10n_gr_prov_driver_url(), b._l10n_gr_prov_driver_url())

    def test_enabled_needs_a_url_from_somewhere(self):
        self.company.l10n_gr_prov_eft_driver_url = False
        self.assertFalse(self._terminal()._l10n_gr_prov_driver_enabled())
        self.assertTrue(
            self._terminal(driver_url='http://till:8187')._l10n_gr_prov_driver_enabled())

    def test_enabled_still_needs_a_protocol(self):
        """A URL alone is not a driver connection: without pos_protocol the
        terminal is charged by hand."""
        self.assertFalse(
            self._terminal(pos_protocol=False,
                           driver_url='http://till:8187')._l10n_gr_prov_driver_enabled())
