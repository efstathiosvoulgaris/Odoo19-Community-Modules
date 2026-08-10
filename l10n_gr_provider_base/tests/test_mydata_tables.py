# -*- coding: utf-8 -*-
"""The pure myDATA tables and derivations. No ORM, no provider, no database."""
from decimal import Decimal, ROUND_HALF_UP

from odoo.tests import TransactionCase, tagged

from odoo.addons.l10n_gr_provider_base.models import gr_mydata
from odoo.addons.l10n_gr_provider_base.models.gr_mydata import (
    PAYMENT_METHOD_MAP,
    PAYMENT_METHODS_SELECTION,
    VAT_CATEGORY_MAP,
    WITHHOLDING_CATEGORY_RATE,
    default_classification,
    journal_types_for_class,
    partner_class,
    valid_cls_categories,
    valid_cls_types,
)


@tagged('post_install', '-at_install')
class TestMydataTables(TransactionCase):

    def test_demo_selfcheck(self):
        """The module's own assertions (map ↔ selection integrity) actually run."""
        gr_mydata._demo()

    # ── partner class → allowed invoice types ────────────────────────────────
    def test_partner_class(self):
        eu = {'DE', 'FR'}
        self.assertEqual(partner_class(True, 'GR', eu, True), 'b2b')
        self.assertEqual(partner_class(False, 'GR', eu, False), 'retail')
        self.assertEqual(partner_class(False, '', eu, True), 'b2b',
                         'a private individual with an ΑΦΜ is B2B')
        self.assertEqual(partner_class(True, 'de', eu, True), 'eu',
                         'country code must be case-insensitive')
        self.assertEqual(partner_class(True, 'US', eu, True), 'third')

    def test_journal_types_per_class(self):
        self.assertIn('1.1', journal_types_for_class('b2b'))
        self.assertNotIn('1.1', journal_types_for_class('retail'))
        self.assertIn('11.1', journal_types_for_class('retail'))
        self.assertNotIn('11.1', journal_types_for_class('eu'))
        # credit notes are partner-class agnostic
        for cls in ('b2b', 'retail', 'eu', 'third'):
            self.assertIn('5.1', journal_types_for_class(cls))

    # ── classification defaults ──────────────────────────────────────────────
    def test_retail_types_prefer_retail_e3(self):
        """11.3/11.4 also allow the wholesale E3_561_001 — retail must win."""
        for inv_type in ('11.1', '11.2', '11.3', '11.4'):
            cat, e3 = default_classification(inv_type, 'goods')
            self.assertEqual(e3, 'E3_561_003', f'{inv_type} picked {e3}')
            self.assertIn(cat, valid_cls_categories(inv_type))

    def test_wholesale_default(self):
        self.assertEqual(default_classification('1.1', 'goods'),
                         ('category1_1', 'E3_561_001'))
        self.assertEqual(default_classification('1.1', 'fixed_assets'),
                         ('category1_4', 'E3_880_001'))

    def test_self_billed_classifies_as_expense(self):
        """3.2 (Τίτλος Κτήσης) is our purchase — never an income category."""
        cat, e3 = default_classification('3.2', 'services')
        self.assertTrue(cat.startswith('category2_'), cat)

    def test_undefined_type_has_no_default(self):
        self.assertEqual(default_classification('5.1', 'goods'), (None, None))
        self.assertEqual(default_classification('nope', 'goods'), (None, None))

    def test_every_default_is_valid_for_its_type(self):
        """Whatever the derivation picks must be accepted by the same map."""
        for inv_type in gr_mydata.CLASSIFICATION_MAP:
            for product_type in ('goods', 'services', 'fixed_assets'):
                cat, e3 = default_classification(inv_type, product_type)
                if cat is None:
                    continue
                self.assertIn(cat, valid_cls_categories(inv_type),
                              f'{inv_type}/{product_type}')
                valid = valid_cls_types(inv_type, cat)
                if valid:
                    self.assertIn(e3, valid, f'{inv_type}/{product_type}/{cat}')

    # 17.4 lists category1_10 as 'all_above' with no tuple sibling in the same
    # category1_* group, so the union is empty and the type offers no E3 code.
    # Known gap in CLASSIFICATION_MAP, not in the expansion — if it is filled
    # in, drop it from here.
    _EMPTY_ALL_ABOVE = {('17.4', 'category1_10')}

    def test_all_above_expands(self):
        """'all_above' must resolve to codes, never leak the literal string."""
        for inv_type, cats in gr_mydata.CLASSIFICATION_MAP.items():
            for cat, val in cats.items():
                types = valid_cls_types(inv_type, cat)
                self.assertNotIn('all_above', types)
                if val == 'all_above' and (inv_type, cat) not in self._EMPTY_ALL_ABOVE:
                    self.assertTrue(types, f'{inv_type}/{cat} expanded to nothing')

    # ── flat lookup tables ───────────────────────────────────────────────────
    def test_vat_category_map_is_per_rate(self):
        """One code per rate — island rates must NOT collapse onto mainland."""
        self.assertEqual(len(set(VAT_CATEGORY_MAP.values())), len(VAT_CATEGORY_MAP))
        self.assertEqual(VAT_CATEGORY_MAP[24], 1)
        self.assertEqual(VAT_CATEGORY_MAP[17], 4)
        self.assertEqual(VAT_CATEGORY_MAP[0], 7)

    def test_payment_method_map_covers_selection(self):
        for code, _label in PAYMENT_METHODS_SELECTION:
            ilyda_type, info = PAYMENT_METHOD_MAP[code]
            self.assertIn(ilyda_type, (1, 2, 3, 4, 5))
            self.assertTrue(info)

    def test_withholding_rates_are_fractions(self):
        for cat, rate in WITHHOLDING_CATEGORY_RATE.items():
            self.assertGreaterEqual(rate, 0.0, cat)
            self.assertLess(rate, 1.0, f'{cat}: {rate} looks like a percentage')


@tagged('post_install', '-at_install')
class TestApplyRate(TransactionCase):
    """_l10n_gr_prov_apply_rate: net × rate, half-up, manual left alone."""

    def setUp(self):
        super().setUp()
        self.move = self.env['account.move'].create({'move_type': 'out_invoice'})

    def _with_net(self, net):
        """Give the move a taxless line worth `net`."""
        self.move.write({'invoice_line_ids': [(5, 0, 0), (0, 0, {
            'name': 'test', 'quantity': 1.0, 'price_unit': net, 'tax_ids': [(5, 0, 0)],
        })]})
        self.assertEqual(self.move.amount_untaxed, net)

    def _apply(self, category, preset=None):
        self.move.l10n_gr_prov_withholding_category = category
        if preset is not None:
            self.move.l10n_gr_prov_withholding_amount = preset
        self.move._l10n_gr_prov_apply_rate(
            'l10n_gr_prov_withholding_category',
            'l10n_gr_prov_withholding_amount',
            WITHHOLDING_CATEGORY_RATE)
        return self.move.l10n_gr_prov_withholding_amount

    def test_no_category_zeroes(self):
        self.assertEqual(self._apply(False, preset=99.0), 0.0)

    def test_manual_category_is_left_untouched(self):
        """Rate 0.00 in the map means "user types the amount" — do not clear it."""
        self.assertEqual(self._apply('17', preset=42.0), 42.0)

    def test_rate_applied(self):
        self._with_net(1000.0)
        self.assertEqual(self._apply('7'), 80.0)      # 8% παροχή υπηρεσιών
        self.assertEqual(self._apply('4'), 30.0)      # 3% τεχνικά έργα

    def test_rounding_is_half_up(self):
        """100.10 × 15% = 15.015 → 15.02. Bankers/float truncation gives 15.01."""
        self._with_net(100.10)
        self.assertEqual(self._apply('1'), 15.02)
