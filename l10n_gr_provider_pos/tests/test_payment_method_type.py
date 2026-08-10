# -*- coding: utf-8 -*-
"""An undeclared bank method must be stamped, never refused.

Odoo creates such methods itself (core's «Card» on the first till, every
third-party terminal), so refusing the write would make a provider company
unable to create a POS config at all.
"""
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestPaymentMethodType(TransactionCase):

    def setUp(self):
        super().setUp()
        self.company = self.env.company
        self.company.l10n_gr_prov_provider = 'ilyda'
        self.bank = self.env['account.journal'].search(
            [('type', '=', 'bank'), ('company_id', '=', self.company.id)], limit=1)
        if not self.bank:
            self.skipTest('company has no bank journal')

    def _create(self, **vals):
        return self.env['pos.payment.method'].create(dict({
            'name': 'test method',
            'company_id': self.company.id,
            'journal_id': self.bank.id,
        }, **vals))

    def test_undeclared_bank_method_is_stamped_not_refused(self):
        method = self._create()
        self.assertEqual(method.l10n_gr_prov_payment_type, '7')
        self.assertFalse(method._l10n_gr_prov_type_is_guessed())

    def test_declared_type_is_kept(self):
        method = self._create(l10n_gr_prov_payment_type='4')
        self.assertEqual(method.l10n_gr_prov_payment_type, '4')

    def test_cash_method_is_left_blank(self):
        """Cash carries its own answer — no need to write anything down."""
        cash = self.env['account.journal'].search(
            [('type', '=', 'cash'), ('company_id', '=', self.company.id)], limit=1)
        if not cash:
            self.skipTest('company has no cash journal')
        method = self._create(journal_id=cash.id)
        self.assertFalse(method.l10n_gr_prov_payment_type)
        self.assertEqual(method._l10n_gr_prov_mydata_type(), '3')

    def test_non_provider_company_is_untouched(self):
        self.company.l10n_gr_prov_provider = False
        self.assertFalse(self._create().l10n_gr_prov_payment_type)

    def test_core_can_still_create_a_pos_config(self):
        """The regression: this raised ValidationError on core's «Card»."""
        config = self.env['pos.config'].create({'name': 'Provider till test'})
        self.assertTrue(config.payment_method_ids)
