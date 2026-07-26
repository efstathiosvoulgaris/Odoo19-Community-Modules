# -*- coding: utf-8 -*-
"""The myDATA constant tables are load-bearing.

A wrong combination here is not caught by Odoo: it travels to AADE and comes
back as an MDP rejection long after the edit, usually on a customer's document.
These tests keep the tables internally consistent.
"""
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.l10n_gr_provider_base.models import gr_mydata as gm


@tagged('post_install', '-at_install')
class TestGrMydataTables(TransactionCase):

    def test_classification_map_uses_known_codes(self):
        """Every category and E3 code in the map exists in the selections."""
        known_e3 = {code for code, _label in gm.CLS_TYPES}
        known_cat = {code for code, _label in gm.CLS_CATEGORIES}
        known_types = {code for code, _label in gm.INVOICE_TYPES}
        for inv_type, categories in gm.CLASSIFICATION_MAP.items():
            self.assertIn(inv_type, known_types,
                          f'{inv_type}: not in INVOICE_TYPES')
            for category, value in categories.items():
                self.assertIn(category, known_cat,
                              f'{inv_type}/{category}: not in CLS_CATEGORIES')
                if isinstance(value, tuple):
                    for e3 in value:
                        self.assertIn(e3, known_e3,
                                      f'{inv_type}/{category}: {e3} not in CLS_TYPES')

    def test_submittable_types_are_real_types(self):
        known_types = {code for code, _label in gm.INVOICE_TYPES}
        self.assertLessEqual(gm.PROVIDER_SUBMITTABLE_TYPES, known_types)
        # providers may only submit 1.1–11.5 (provider doc §5)
        for inv_type in gm.PROVIDER_SUBMITTABLE_TYPES:
            self.assertLess(float(inv_type.split('.')[0]), 12,
                            f'{inv_type} is an accounting-only type')

    def test_type_sets_reference_real_types(self):
        known_types = {code for code, _label in gm.INVOICE_TYPES}
        for name in ('TYPES_NO_BUYER', 'TYPES_NO_VAT', 'TYPES_DISPATCH',
                     'TYPES_RECEIPT', 'TYPES_SELF_BILLED', 'TYPES_POS_ONLY',
                     'TYPES_CREDIT', 'TYPES_NEED_CORRELATED'):
            self.assertLessEqual(getattr(gm, name), known_types,
                                 f'{name} references an unknown invoice type')

    def test_self_supply_and_restaurant_orders_carry_vat(self):
        """6.1/6.2 are deemed supplies and 8.6 is a real restaurant order —
        AADE rejects vatCategory 8 on them (MDP-0050)."""
        for inv_type in ('6.1', '6.2', '8.6'):
            self.assertNotIn(inv_type, gm.TYPES_NO_VAT)

    def test_titlos_ktisis_requires_counterpart(self):
        """3.1/3.2 need the individual's ΑΦΜ — ILYDA error 204."""
        for inv_type in ('3.1', '3.2'):
            self.assertNotIn(inv_type, gm.TYPES_NO_BUYER)

    def test_partner_class(self):
        eu = {'PL', 'DE', 'FR'}
        self.assertEqual(gm.partner_class(True, 'GR', eu, True), 'b2b')
        self.assertEqual(gm.partner_class(False, 'GR', eu, False), 'retail')
        # an individual with an ΑΦΜ still invoices as a business
        self.assertEqual(gm.partner_class(False, 'GR', eu, True), 'b2b')
        self.assertEqual(gm.partner_class(True, 'PL', eu, True), 'eu')
        self.assertEqual(gm.partner_class(True, 'US', eu, True), 'third')
        # no country set is treated as domestic
        self.assertEqual(gm.partner_class(True, False, eu, False), 'b2b')

    def test_journal_types_per_partner_class(self):
        self.assertIn('1.1', gm.journal_types_for_class('b2b'))
        self.assertNotIn('1.1', gm.journal_types_for_class('retail'))
        self.assertIn('11.1', gm.journal_types_for_class('retail'))
        self.assertIn('1.2', gm.journal_types_for_class('eu'))
        self.assertIn('1.3', gm.journal_types_for_class('third'))
        # credit notes and dispatch notes are class-agnostic
        self.assertIn('5.1', gm.journal_types_for_class('retail'))
        self.assertIn('9.3', gm.journal_types_for_class('b2b'))

    def test_default_classification(self):
        self.assertEqual(gm.default_classification('1.1', 'goods'),
                         ('category1_1', 'E3_561_001'))
        # retail types must prefer the retail E3 code, not the wholesale one
        self.assertEqual(gm.default_classification('11.1', 'goods'),
                         ('category1_1', 'E3_561_003'))
        self.assertEqual(gm.default_classification('11.3', 'goods'),
                         ('category1_1', 'E3_561_003'))
        # 5.1 follows the correlated original, so it derives nothing
        self.assertEqual(gm.default_classification('5.1', 'goods'), (None, None))

    def test_every_derived_default_is_map_valid(self):
        for inv_type, _label in gm.INVOICE_TYPES:
            for product_type in ('goods', 'own_products', 'services', 'fixed_assets'):
                category, e3 = gm.default_classification(inv_type, product_type)
                if not category:
                    continue
                self.assertIn(category, gm.valid_cls_categories(inv_type))
                if e3:
                    self.assertIn(e3, gm.valid_cls_types(inv_type, category))

    def test_self_billed_defaults_to_an_expense_category(self):
        """Τίτλος Κτήσης is our expense even though the map also lists income."""
        for inv_type in gm.TYPES_SELF_BILLED:
            category, _e3 = gm.default_classification(inv_type, 'services')
            self.assertTrue(category.startswith('category2_'),
                            f'{inv_type} derived the income category {category}')

    def test_vat_category_map_covers_every_greek_rate(self):
        for rate in gm.DOMESTIC_TAX_RATES:
            self.assertIn(rate, gm.VAT_CATEGORY_MAP)
        self.assertEqual(gm.VAT_CATEGORY_MAP[0], 7)   # 0% / exempt

    def test_payment_method_map_matches_the_selection(self):
        self.assertEqual(
            {code for code, _label in gm.PAYMENT_METHODS_SELECTION},
            set(gm.PAYMENT_METHOD_MAP),
        )

    def test_extra_tax_rate_keys_are_valid_categories(self):
        pairs = (
            (gm.WITHHOLDING_CATEGORY_RATE, gm.WITHHOLDING_CATEGORY_SELECTION),
            (gm.STAMP_DUTY_CATEGORY_RATE, gm.STAMP_DUTY_CATEGORY_SELECTION),
            (gm.FEES_CATEGORY_RATE, gm.FEES_CATEGORY_SELECTION),
            (gm.FEES_CATEGORY_FIXED, gm.FEES_CATEGORY_SELECTION),
            (gm.OTHER_TAXES_CATEGORY_RATE, gm.OTHER_TAXES_CATEGORY_SELECTION),
            (gm.OTHER_TAXES_CATEGORY_FIXED, gm.OTHER_TAXES_CATEGORY_SELECTION),
        )
        for rates, selection in pairs:
            known = {code for code, _label in selection}
            self.assertLessEqual(set(rates), known)

    def test_measurement_unit_mapping_targets_real_codes(self):
        from odoo.addons.l10n_gr_provider_base.models import uom_uom
        known = {code for code, _label in uom_uom.MEASUREMENT_UNITS}
        self.assertLessEqual(set(uom_uom.UOM_UNIT_MAP.values()), known)
        # 7 is the catch-all and is never mapped directly: it needs the unit
        # name and count alongside it (§8.13 note 9)
        self.assertNotIn('7', set(uom_uom.UOM_UNIT_MAP.values()))
