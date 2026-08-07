# -*- coding: utf-8 -*-
"""The two cancellation routes of the catering guide §4, offline.

The provider is never called: `_l10n_gr_prov_send` is replaced by a stub that
marks the note as if it had been transmitted, so what is asserted is the
payload we would have sent and the state machine around it.
"""
from unittest.mock import patch

from odoo.tests import TransactionCase, tagged

_PATH = ('odoo.addons.l10n_gr_provider_pos_restaurant.models.catering_order'
         '.L10nGrProvCateringOrder._l10n_gr_prov_send')


@tagged('post_install', '-at_install')
class TestCateringCancel(TransactionCase):

    def setUp(self):
        super().setUp()
        self.sent = []

        def fake_send(note):
            self.sent.append((note, note._l10n_gr_prov_build_payload()))
            note.write({'state': 'sent',
                        'mark': '4000019%05d' % note.id,
                        'error_message': False})

        self.patcher = patch(_PATH, autospec=True, side_effect=fake_send)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def _note(self, **kw):
        vals = {
            'company_id': self.env.company.id,
            'table_aa': 'A1',
            'pos_order_uuid': 'uuid-1',
            'serial': '00001',
            'line_ids': [(0, 0, {
                'name': 'Πατάτες', 'prep_key': 'k1', 'quantity': 2.0,
                'net_value': 10.0, 'vat_amount': 1.3, 'vat_rate': 13.0,
            })],
        }
        vals.update(kw)
        note = self.env['l10n.gr.prov.catering.order'].create(vals)
        note._l10n_gr_prov_send()
        return note

    def test_negative_note_credits_the_original_price(self):
        """One of two units cancelled: half the ORIGINAL amounts, recType 7."""
        origin = self._note()
        line = self.env['l10n.gr.prov.catering.order']._l10n_gr_prov_negative_line(
            'uuid-1', {'prep_key': 'k1', 'quantity': -1, 'name': 'Πατάτες'})
        self.assertEqual(line['quantity'], 1)
        self.assertEqual(line['net'], 5.0)
        self.assertEqual(line['vat_amount'], 0.65)

        negative = self._note(kind='negative', serial='00002', line_ids=[(0, 0, {
            'name': line['name'], 'prep_key': 'k1', 'quantity': line['quantity'],
            'net_value': line['net'], 'vat_amount': line['vat_amount'],
            'vat_rate': line['vat_rate'],
        })])
        payload = self.sent[-1][1]
        row = payload['aadeData']['invoiceRowTypes'][0]
        self.assertEqual(row['recType'], 7, 'the opposite sign IS recType 7')
        self.assertEqual(row['netValue'], 5.0, 'amounts stay positive')
        self.assertEqual(negative.amount_total, 5.65)
        self.assertNotIn('recType', origin_row := self.sent[0][1][
            'aadeData']['invoiceRowTypes'][0], origin_row)

    def test_negative_line_of_an_untransmitted_item_is_dropped(self):
        line = self.env['l10n.gr.prov.catering.order']._l10n_gr_prov_negative_line(
            'uuid-1', {'prep_key': 'never-sent', 'quantity': -1})
        self.assertIsNone(line, 'nothing was transmitted, nothing to cancel')

    def test_total_cancel_closes_the_notes(self):
        first, second = self._note(), self._note(serial='00002')
        cancel = (first | second)._l10n_gr_prov_total_cancel()

        aade = self.sent[-1][1]['aadeData']
        self.assertTrue(aade['totalCancelDeliveryOrders'])
        self.assertEqual(sorted(aade['multipleConnectedMarks']),
                         sorted([int(first.mark), int(second.mark)]))
        self.assertEqual(aade['invoiceRowTypes'][0]['vatCategory'], 8)
        self.assertEqual(self.sent[-1][1]['docTotal']['invoiceTotalAmountWithVat'], 0.0)
        self.assertEqual(cancel.kind, 'cancel')
        self.assertEqual(first.state, 'cancelled')
        self.assertEqual(second.state, 'cancelled')

    def test_a_failed_total_cancel_leaves_the_notes_open(self):
        note = self._note()
        self.patcher.stop()
        with patch(_PATH, autospec=True,
                   side_effect=lambda n: n.write({'state': 'error'})):
            note._l10n_gr_prov_total_cancel()
        self.patcher.start()
        self.assertEqual(note.state, 'sent',
                         'an unsent cancellation must not close anything')
