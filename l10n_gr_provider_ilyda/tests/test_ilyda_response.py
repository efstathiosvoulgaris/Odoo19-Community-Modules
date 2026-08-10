# -*- coding: utf-8 -*-
"""ILYDA driver: response handling, error classification, UID/series.

Everything here is offline — the API client is never constructed. What is
tested is how the driver reads what ILYDA sends back, which is where a wrong
call means either a duplicate document at AADE or a lost MARK.
"""
from types import SimpleNamespace

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

from odoo.addons.l10n_gr_provider_ilyda.models.account_move import (
    _ascii_safe, _r2, _vat_category,
)


@tagged('post_install', '-at_install')
class TestIlydaHelpers(TransactionCase):
    """Pure helpers — no record needed."""

    def test_r2(self):
        self.assertEqual(_r2(None), 0.0)
        self.assertEqual(_r2(1.005), 1.0)     # float repr, documented behaviour
        self.assertEqual(_r2(12.3456), 12.35)

    def test_ascii_safe_transliterates_greek(self):
        self.assertEqual(_ascii_safe('ΤΙΜ'), 'TIM')
        # accented Greek is dropped, not transliterated: the translate table
        # runs before NFKD, so 'ή' never matches and the ascii encode discards
        # it. Fine for the series it guards; do not feed it free text.
        self.assertEqual(_ascii_safe('Αθήνα'), 'Aqna')
        self.assertEqual(_ascii_safe(None), '')
        self.assertTrue(_ascii_safe('ΑΛΠ/2026/0001').isascii())

    def test_vat_category(self):
        self.assertEqual(_vat_category(SimpleNamespace(amount=24.0), '1.1'), (1, 'S'))
        self.assertEqual(_vat_category(SimpleNamespace(amount=17.0), '1.1'), (4, 'S'))
        self.assertEqual(_vat_category(SimpleNamespace(amount=0.0), '1.1'), (7, 'E'))
        self.assertEqual(_vat_category(None, '1.1'), (8, 'O'))

    def test_vat_category_no_vat_types(self):
        """8.4/9.1 etc. carry no VAT even when the line has a tax."""
        self.assertEqual(_vat_category(SimpleNamespace(amount=24.0), '9.1'), (8, 'O'))

    def test_unknown_rate_falls_back_to_exempt(self):
        self.assertEqual(_vat_category(SimpleNamespace(amount=99.0), '1.1'), (7, 'E'))

    def test_ilyda_vat_normalisation(self):
        vat = self.env['account.move']._ilyda_vat
        self.assertEqual(vat('EL123456789'), 'EL123456789')
        self.assertEqual(vat('GR 123456789'), 'EL123456789')
        self.assertEqual(vat('123456789'), '123456789')
        self.assertEqual(vat('EL123456789', prefixed=False), '123456789')
        self.assertEqual(vat('DE811234567'), 'DE811234567', 'foreign VAT is kept')
        self.assertEqual(vat(None), '')


@tagged('post_install', '-at_install')
class TestIlydaErrorCode(TransactionCase):
    """The duplicate guard reads these — a misread costs a double submission."""

    def setUp(self):
        super().setUp()
        self.move = self.env['account.move'].create({'move_type': 'out_invoice'})

    def _code(self, data):
        return self.env['account.move']._l10n_gr_prov_ilyda_error_code(data)

    def test_real_document_has_no_code(self):
        self.assertIsNone(self._code({'mark': '4001', 'invoiceId': 7}))

    def test_top_level_and_nested_codes(self):
        self.assertEqual(self._code({'code': 'A0004'}), 'A0004')
        self.assertEqual(self._code({'errors': [{'code': 'A0002'}]}), 'A0002')

    def test_unparseable_is_an_error_not_a_document(self):
        self.assertEqual(self._code(None), 'A0000')
        self.assertEqual(self._code([{'code': 'A0004'}]), 'A0000')
        self.assertEqual(self._code({'errors': [{'msg': 'no code'}]}), 'A0000')

    def test_lookup_not_found_returns_none(self):
        for code in ('A0002', 'A0003', 'A0004', 'A0005', 'A0006'):
            with self.subTest(code=code):
                self.assertIsNone(self.move._l10n_gr_prov_ilyda_lookup(
                    lambda key: {'code': code}, 'uid'))

    def test_lookup_other_error_raises(self):
        """An auth/server failure must never be read as "safe to resend"."""
        with self.assertRaises(UserError):
            self.move._l10n_gr_prov_ilyda_lookup(lambda key: {'code': 'A9999'}, 'uid')
        with self.assertRaises(UserError):
            self.move._l10n_gr_prov_ilyda_lookup(lambda key: 'not json', 'uid')

    def test_lookup_returns_the_document(self):
        doc = {'mark': '4001'}
        self.assertEqual(
            self.move._l10n_gr_prov_ilyda_lookup(lambda key: doc, 'uid'), doc)


@tagged('post_install', '-at_install')
class TestIlydaFormatError(TransactionCase):

    def _fmt(self, error):
        return self.env['account.move']._l10n_gr_prov_ilyda_format_error(error)

    def test_aade_message_is_appended(self):
        self.assertEqual(
            self._fmt({'code': 'I0004', 'defaultMessage': 'Invalid',
                       'aadeMessage': 'MDP-0050'}),
            'I0004: Invalid (MDP-0050)')

    def test_aade_message_alone(self):
        self.assertEqual(self._fmt({'code': 'I0004', 'aadeMessage': 'MDP-0050'}),
                         'I0004: MDP-0050')

    def test_no_duplication_when_identical(self):
        self.assertEqual(self._fmt({'code': 'X', 'defaultMessage': 'same',
                                    'aadeMessage': 'same'}), 'X: same')

    def test_error_fields_are_listed(self):
        self.assertEqual(
            self._fmt({'code': 'I0001', 'defaultMessage': 'Bad',
                       'errorFields': [{'field': 'vat', 'value': '123'}]}),
            'I0001: Bad [vat=123]')


@tagged('post_install', '-at_install')
class TestIlydaHandleResponse(TransactionCase):
    """Submit-response branches. Wrong branch = unmarked document printed."""

    def setUp(self):
        super().setUp()
        self.move = self.env['account.move'].create({'move_type': 'out_invoice'})

    def _handle(self, data):
        return self.move._l10n_gr_prov_ilyda_handle_response(data)

    _MARKING = {
        'mark': '400001234567890',
        'invoiceId': 42,
        'verificationHash': 'abc',
        'invoiceIdentifier': 'DEADBEEF',
        'qrCode': 'https://vs.gr/qr/1',
        'providerUrl': 'https://vs.gr/inv/42',
    }

    def test_marked(self):
        self.assertEqual(self._handle({'invoiceMarking': self._MARKING}), 'sent')
        self.assertEqual(self.move.l10n_gr_prov_mark, '400001234567890')
        self.assertEqual(self.move.l10n_gr_prov_invoice_id, '42')
        self.assertEqual(self.move.l10n_gr_prov_qr_url, 'https://vs.gr/qr/1')
        self.assertEqual(self.move.l10n_gr_prov_uid, 'deadbeef',
                         'the UID is stored lower-cased for lookups')

    def test_previously_submitted_flag(self):
        marking = dict(self._MARKING, aadePreviouslySubmittedError228=True)
        self._handle({'invoiceMarking': marking})
        self.assertTrue(self.move.l10n_gr_prov_previously_submitted)

    def test_i0008_is_accepted(self):
        """Same number already marked — the response carries the original MARK."""
        self.assertEqual(self._handle({
            'invoiceMarking': self._MARKING,
            'errors': [{'code': 'I0008', 'defaultMessage': 'already marked'}],
        }), 'sent')
        self.assertEqual(self.move.l10n_gr_prov_mark, '400001234567890')

    def test_queued_wins_over_the_fatal_flag(self):
        """MQ002 arrives flagged fatal alongside I9999 — it is a queue, not a
        rejection, and the identifier/QR must be stored for printing."""
        self.assertEqual(self._handle({
            'invoiceMarking': {'invoiceId': 42, 'invoiceIdentifier': 'DEADBEEF',
                               'qrCode': 'https://vs.gr/qr/1'},
            'errors': [{'code': 'MQ002', 'fatal': True},
                       {'code': 'I9999', 'fatal': True}],
        }), 'queued')
        self.assertFalse(self.move.l10n_gr_prov_mark)
        self.assertEqual(self.move.l10n_gr_prov_invoice_identifier, 'DEADBEEF')
        self.assertEqual(self.move.l10n_gr_prov_qr_url, 'https://vs.gr/qr/1')
        self.assertEqual(self.move.l10n_gr_prov_uid, 'deadbeef')

    def test_requeue_keeps_the_stored_identifier(self):
        """MQ001 on a re-submission may come back bare — do not wipe the QR."""
        self.move.write({'l10n_gr_prov_invoice_identifier': 'DEADBEEF',
                         'l10n_gr_prov_qr_url': 'https://vs.gr/qr/1'})
        self.assertEqual(self._handle({
            'invoiceMarking': {},
            'errors': [{'code': 'MQ001'}],
        }), 'queued')
        self.assertEqual(self.move.l10n_gr_prov_qr_url, 'https://vs.gr/qr/1')

    def test_queued_without_identifier_raises(self):
        """Nothing to print and nothing to poll with — better to fail loudly."""
        with self.assertRaises(UserError):
            self._handle({'invoiceMarking': {}, 'errors': [{'code': 'MQ002'}]})

    def test_fatal_rejection_raises(self):
        with self.assertRaises(UserError):
            self._handle({'invoiceMarking': {},
                          'errors': [{'code': 'I0004', 'fatal': True,
                                      'defaultMessage': 'Invalid VAT'}]})

    def test_no_marking_raises(self):
        with self.assertRaises(UserError):
            self._handle({'invoiceMarking': {}})

    def test_bare_list_response_raises(self):
        with self.assertRaises(UserError):
            self._handle([{'code': 'I0004', 'defaultMessage': 'Invalid'}])

    def test_non_fatal_warnings_do_not_block(self):
        self.assertEqual(self._handle({
            'invoiceMarking': self._MARKING,
            'errors': [{'code': 'W0001', 'fatal': False, 'defaultMessage': 'fyi'}],
        }), 'sent')


@tagged('post_install', '-at_install')
class TestIlydaUid(TransactionCase):
    """series/serial and the A.1035-B2 UID — must stay byte-identical to what
    the payload sends, or the duplicate guard looks up the wrong document."""

    def setUp(self):
        super().setUp()
        self.move = self.env['account.move'].create({'move_type': 'out_invoice'})

    def test_series_serial_split(self):
        self.move.name = 'ΑΛΠ/2026/0001'
        self.assertEqual(self.move._l10n_gr_prov_ilyda_series_serial(),
                         ('ΑΛΠ_2026', '0001'))

    def test_series_falls_back_to_journal_code(self):
        self.move.name = '0007'
        series, serial = self.move._l10n_gr_prov_ilyda_series_serial()
        self.assertEqual(series, self.move.journal_id.code)
        self.assertEqual(serial, '0007')

    def test_uid_is_a_sha1_and_survives_greek(self):
        """The digest is taken over ISO-8859-7 bytes — Greek must not crash it."""
        self.move.name = 'ΑΛΠ/2026/0001'
        [(scheme, uid)] = self.move._l10n_gr_prov_ilyda_uid_candidates()
        self.assertEqual(scheme, 'A.1035-B2')
        self.assertEqual(len(uid), 40)
        self.assertEqual(uid, uid.lower())
        int(uid, 16)  # hex

    def test_uid_changes_with_the_serial(self):
        self.move.name = 'ΑΛΠ/2026/0001'
        first = self.move._l10n_gr_prov_ilyda_uid_candidates()
        self.move.name = 'ΑΛΠ/2026/0002'
        self.assertNotEqual(self.move._l10n_gr_prov_ilyda_uid_candidates(), first)

    def test_credit_note_type_is_derived_not_read_from_the_journal(self):
        """The journal default carries the forward type — always wrong here."""
        refund = self.env['account.move'].create({'move_type': 'out_refund'})
        if refund.journal_id.l10n_gr_edi_inv_type_default in ('11.4', '8.5'):
            self.skipTest('retail/POS journal: 11.4 and 8.5 are correct as-is')
        self.assertEqual(refund._l10n_gr_prov_ilyda_inv_type(), '5.2',
                         'a standalone credit note is 5.2, never the journal type')
