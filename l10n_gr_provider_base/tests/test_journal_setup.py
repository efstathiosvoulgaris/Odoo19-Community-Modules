# -*- coding: utf-8 -*-
"""Journal setup — the install path that kept breaking by hand.

Three bugs found only by clicking through fresh databases live here: Odoo
translates the sales journal code «INV» to «ΤΙΜ» in Greek and silently stole
the code the 1.1 journal needs; journals created before the chart got rewritten
by the chart loader; and without an explicit sequence the picker fell back to
alphabetical Greek codes.
"""
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.l10n_gr_provider_base.models.account_journal import (
    GR_JOURNALS, GR_JOURNAL_SEQUENCE_START,
)


@tagged('post_install', '-at_install')
class TestGrJournalSetup(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env['res.company'].create({'name': 'GR Provider Test'})
        cls.Journal = cls.env['account.journal'].with_company(cls.company)

    def _make_chart_sale_journal(self, code='ΤΙΜ'):
        """Odoo's own sales journal, xmlid included — that is how the setup
        tells the chart's journal apart from a hand-made one."""
        journal = self.Journal.create({
            'name': 'Πωλήσεις',
            'code': code,
            'type': 'sale',
            'company_id': self.company.id,
        })
        self.env['ir.model.data'].create({
            'name': f'{self.company.id}_sale',
            'module': 'account',
            'model': 'account.journal',
            'res_id': journal.id,
        })
        return journal

    def _create_journals(self):
        return self.Journal._l10n_gr_prov_create_journals(self.company)

    # ── the ΤΙΜ collision ────────────────────────────────────────────────────

    def test_chart_journal_is_moved_off_the_mydata_code(self):
        chart_journal = self._make_chart_sale_journal('ΤΙΜ')
        counts = self._create_journals()
        self.assertEqual(counts['recoded'], 1)
        # the journal survives untouched apart from its code
        self.assertEqual(chart_journal.code, 'ΠΩΛ')
        self.assertEqual(chart_journal.name, 'Πωλήσεις')
        self.assertFalse(chart_journal.l10n_gr_edi_inv_type_default)
        # ...and ΤΙΜ now belongs to the myDATA journal
        tim = self.Journal.search([
            ('code', '=', 'ΤΙΜ'), ('company_id', '=', self.company.id)])
        self.assertEqual(len(tim), 1)
        self.assertEqual(tim.l10n_gr_edi_inv_type_default, '1.1')
        self.assertNotEqual(tim, chart_journal)

    def test_chart_journal_keeps_a_non_colliding_code(self):
        chart_journal = self._make_chart_sale_journal('INV')
        counts = self._create_journals()
        self.assertEqual(counts['recoded'], 0)
        self.assertEqual(chart_journal.code, 'INV')

    def test_foreign_journal_holding_our_code_is_left_alone(self):
        """No xmlid, so it is somebody's own journal: never touched, and the
        myDATA journal it blocks is reported instead of vanishing silently."""
        foreign = self.Journal.create({
            'name': 'Δικό μου ημερολόγιο',
            'code': 'ΤΙΜ',
            'type': 'sale',
            'company_id': self.company.id,
        })
        counts = self._create_journals()
        self.assertEqual(counts['recoded'], 0)
        self.assertEqual(foreign.code, 'ΤΙΜ')
        self.assertFalse(foreign.l10n_gr_edi_inv_type_default)
        self.assertEqual(counts['skipped'], 1)
        self.assertEqual(counts['created'], len(GR_JOURNALS) - 1)

    # ── creation ────────────────────────────────────────────────────────────

    def test_creates_every_journal_with_its_code_and_type(self):
        counts = self._create_journals()
        self.assertEqual(counts['created'], len(GR_JOURNALS))
        for xmlid, name, code, jtype, inv_type in GR_JOURNALS:
            journal = self.env.ref(
                f'l10n_gr_provider_base.{xmlid}_{self.company.id}')
            self.assertEqual(journal.code, code, name)
            self.assertEqual(journal.type, jtype, name)
            self.assertEqual(journal.l10n_gr_edi_inv_type_default, inv_type, name)
            self.assertFalse(journal.refund_sequence, name)

    def test_journals_are_ordered_for_the_picker(self):
        self._create_journals()
        for position, (xmlid, name, _code, _jtype, _inv) in enumerate(GR_JOURNALS):
            journal = self.env.ref(
                f'l10n_gr_provider_base.{xmlid}_{self.company.id}')
            self.assertEqual(journal.sequence,
                             GR_JOURNAL_SEQUENCE_START + position, name)

    def test_retail_journals_default_to_the_80mm_form(self):
        self._create_journals()
        alp = self.env.ref(f'l10n_gr_provider_base.gr_j_11_1_{self.company.id}')
        tim = self.env.ref(f'l10n_gr_provider_base.gr_j_1_1_{self.company.id}')
        self.assertEqual(alp.l10n_gr_prov_print_form, 'gr_80mm')
        self.assertEqual(tim.l10n_gr_prov_print_form, 'gr_a4')

    def test_delivery_note_journals_are_flagged(self):
        self._create_journals()
        combined = self.env.ref(
            f'l10n_gr_provider_base.gr_j_1_1_dn_{self.company.id}')
        plain = self.env.ref(f'l10n_gr_provider_base.gr_j_1_1_{self.company.id}')
        self.assertTrue(combined.l10n_gr_prov_delivery_note)
        self.assertFalse(plain.l10n_gr_prov_delivery_note)

    def test_creation_is_idempotent(self):
        self._create_journals()
        counts = self._create_journals()
        self.assertEqual(counts['created'], 0)
        self.assertEqual(counts['repaired'], 0)
        self.assertEqual(self.Journal.search_count([
            ('company_id', '=', self.company.id),
            ('l10n_gr_edi_inv_type_default', '!=', False),
        ]), len(GR_JOURNALS))

    # ── repair ──────────────────────────────────────────────────────────────

    def test_drifted_code_and_type_are_restored(self):
        """The chart loader rewrites journals it merges onto — ours heal."""
        self._create_journals()
        tim = self.env.ref(f'l10n_gr_provider_base.gr_j_1_1_{self.company.id}')
        tim.write({'code': 'ΧΧΧ', 'l10n_gr_edi_inv_type_default': False})
        counts = self._create_journals()
        self.assertEqual(counts['repaired'], 1)
        self.assertEqual(tim.code, 'ΤΙΜ')
        self.assertEqual(tim.l10n_gr_edi_inv_type_default, '1.1')

    def test_a_manual_rename_survives(self):
        """Only the code and the myDATA type are load-bearing; a journal the
        accountant renamed keeps its name."""
        self._create_journals()
        tim = self.env.ref(f'l10n_gr_provider_base.gr_j_1_1_{self.company.id}')
        tim.name = 'Τιμολόγια Πελατών (δικό μας)'
        self._create_journals()
        self.assertEqual(tim.name, 'Τιμολόγια Πελατών (δικό μας)')
