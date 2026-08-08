# -*- coding: utf-8 -*-
"""A credit document reverses its own kind.

`to_invoice` cannot say whether a refund is a ΤΙΜ: core switches it on for any
refund whose original was invoiced, and on a provider till every order is
invoiced. So the flag arrives True on every refund, including refunds of plain
retail receipts.
"""
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestPosRefundTimologio(TransactionCase):

    def setUp(self):
        super().setUp()
        origin = self.env['pos.order'].search(
            [('lines', '!=', False),
             ('config_id.l10n_gr_prov_alp_journal_id', '!=', False)], limit=1)
        if not origin:
            self.skipTest('no provider POS order in this database')
        self.origin = origin

    def _refund_of(self, timologio):
        """A refund as it actually reaches the server: to_invoice True whatever
        the original was. In-memory, so nothing is written."""
        self.origin.l10n_gr_prov_timologio = timologio
        return self.env['pos.order'].new({
            'to_invoice': True,
            'lines': [(0, 0, {'refunded_orderline_id': self.origin.lines[0].id})],
        })

    def test_refund_of_a_receipt_is_not_a_timologio(self):
        self.assertFalse(
            self._refund_of(False)._l10n_gr_prov_wants_timologio(),
            'a refunded ΑΛΠ must credit as ΠΛΠ 11.4, with no ΑΦΜ demanded')

    def test_refund_of_a_timologio_is_a_timologio(self):
        self.assertTrue(
            self._refund_of(True)._l10n_gr_prov_wants_timologio(),
            'a refunded ΤΙΜ must credit as ΠΙΣΤ 5.1')

    def test_negative_order_keeps_the_cashiers_choice(self):
        """Typed with negative quantities: no original, so the button decides."""
        order = self.env['pos.order'].new({'to_invoice': True})
        self.assertTrue(order._l10n_gr_prov_wants_timologio())
