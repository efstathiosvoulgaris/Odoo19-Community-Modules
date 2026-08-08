# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

from odoo.addons.l10n_gr_provider_base.models.payment import PAYMENT_TYPE_SELECTION

# Greek POS payment methods the standard setup doesn't ship (Odoo creates only
# cash / card / customer account). (xmlid suffix, name, AADE §8.12 code) — the
# code is stamped explicitly because Odoo sees all of these as plain «bank»
# methods and could never tell them apart on its own.
GR_POS_PAYMENT_METHODS = [
    ('gr_pm_iris',          'IRIS',                              '8'),
    ('gr_pm_web_banking',   'Web Banking',                       '6'),
    ('gr_pm_cheque',        'Επιταγή',                           '4'),
    ('gr_pm_bank_domestic', 'Τραπεζική Μεταφορά (Ημεδαπής)',     '1'),
    ('gr_pm_bank_foreign',  'Τραπεζική Μεταφορά (Αλλοδαπής)',    '2'),
]


class PosPaymentMethod(models.Model):
    _inherit = 'pos.payment.method'

    # Optional manual override. Left blank, the myDATA type is derived live from
    # the method's kind at send time (_l10n_gr_prov_mydata_type) — no stored
    # value to go stale, no compute depending on the non-stored `type` field.
    l10n_gr_prov_payment_type = fields.Selection(
        PAYMENT_TYPE_SELECTION, string='Τύπος Πληρωμής myDATA',
        help='Αφήστε κενό για αυτόματη αναγνώριση από το είδος του τρόπου '
             'πληρωμής (μετρητά → 3, κάρτα/POS → 7, IRIS → 8, επί πιστώσει → 5). '
             'Ορίστε τιμή μόνο για να παρακάμψετε την αυτόματη αναγνώριση.')

    def _l10n_gr_prov_mydata_type(self):
        """Effective AADE §8.12 payment code: the manual override if set, else
        derived from the method's journal kind / integration."""
        self.ensure_one()
        if self.l10n_gr_prov_payment_type:
            return self.l10n_gr_prov_payment_type
        if self.type == 'cash':
            return '3'    # Μετρητά
        if self.payment_method_type == 'qr_code':
            return '8'    # IRIS
        if self.type == 'bank':
            return '7'    # POS / κάρτα
        if self.type == 'pay_later':
            return '5'    # Επί Πιστώσει
        return '3'

    def _l10n_gr_prov_type_is_guessed(self):
        """True when the derivation above is a guess rather than a reading.

        Codes 1, 2, 4, 6 and 7 all look identical to Odoo — a «bank» method on
        a bank journal. Odoo has no field that separates a bank transfer from a
        cheque from a card, so with nothing declared the derivation falls
        through to 7 and the document tells AADE the customer paid by card.
        Cash, Customer Account and QR carry their own answer.
        """
        self.ensure_one()
        return (not self.l10n_gr_prov_payment_type
                and self.type == 'bank'
                and self.payment_method_type != 'qr_code')

    @api.constrains('l10n_gr_prov_payment_type', 'journal_id',
                    'payment_method_type', 'company_id')
    def _check_l10n_gr_prov_payment_type(self):
        for method in self:
            if (method._l10n_gr_prov_type_is_guessed()
                    and method.company_id._l10n_gr_prov_active()):
                raise ValidationError(_(
                    'Ορίστε τον «Τύπο Πληρωμής myDATA» για τον τρόπο πληρωμής '
                    '«%(name)s».\n\n'
                    'Η Odoo βλέπει όλους τους τραπεζικούς τρόπους πληρωμής '
                    '(κάρτα, IRIS, Web Banking, επιταγή, έμβασμα) ως ίδιους, '
                    'οπότε χωρίς ρητή δήλωση το παραστατικό θα διαβίβαζε στην '
                    'ΑΑΔΕ ότι η πληρωμή έγινε με κάρτα (τύπος 7) — και θα '
                    'ζητούσε υπογραφή Α.1155 από το τερματικό.',
                    name=method.name))

    def _l10n_gr_prov_ensure_card_method(self, company, journal):
        """Make sure a card (type 7) method exists before seeding ours.

        Odoo creates its own «Card» method only when the company has NO
        bank-journal payment method yet — `pos.config.
        _create_journal_and_payment_methods()` guards on exactly that. Every
        method we seed rides the bank journal, so seeding before the first POS
        is created suppresses Odoo's card method permanently, and a till with
        no type-7 method can never trigger the Α.1155 signature flow. Creating
        it here closes that window whichever order the two happen in.
        """
        bank_methods = self.search([
            ('journal_id.type', '=', 'bank'),
            ('company_id', 'in', company.parent_ids.ids),
            # our own seeds override the type away from 7, so they do not count
            ('l10n_gr_prov_payment_type', 'in', (False, '7')),
        ])
        if bank_methods:
            return 0
        xmlid = f'gr_pm_card_{company.id}'
        if self.env.ref(f'l10n_gr_provider_pos.{xmlid}', raise_if_not_found=False):
            return 0
        method = self.create({
            'name': 'Κάρτα-POS',
            'company_id': company.id,
            'journal_id': journal.id,
            # Declared, not left to the derivation. 7 is what a blank bank
            # method falls through to anyway, so nothing changes at send time —
            # but the form now says out loud what is transmitted, and an
            # accidental blank on some other bank method is no longer
            # indistinguishable from a deliberate card.
            'l10n_gr_prov_payment_type': '7',
            'sequence': 1,
        })
        self.env['ir.model.data'].create({
            'name': xmlid,
            'module': 'l10n_gr_provider_pos',
            'model': 'pos.payment.method',
            'res_id': method.id,
            'noupdate': True,
        })
        return 1

    def _l10n_gr_prov_create_pos_payment_methods(self, company):
        """Create — and repair — the Greek POS payment methods.

        They ride the company's bank journal and are NOT attached to any POS
        config; tick the ones you need per till. The journal is deliberately
        not repaired: which journal a method posts to is a bookkeeping decision
        for the accountant, and myDATA transmits the type, not the journal.

        The myDATA type IS repaired on the methods we own, exactly as the
        settings button repairs a journal's code and document type: it is the
        one value the whole transmission hangs on, and Odoo cannot re-derive it
        (see _l10n_gr_prov_type_is_guessed). Returns counts for the UI.
        """
        counts = {'created': 0, 'repaired': 0, 'undeclared': 0}
        journal = self.env['account.journal'].search([
            ('type', '=', 'bank'),
            ('company_id', '=', company.id),
        ], limit=1)
        if not journal:
            return counts
        counts['created'] = self._l10n_gr_prov_ensure_card_method(company, journal)
        # The card is seeded by its own path (above), so the loop below never
        # sees it — and a card created before 1.9 carries no declared type.
        card = self.env.ref(f'l10n_gr_provider_pos.gr_pm_card_{company.id}',
                            raise_if_not_found=False)
        if card and card.l10n_gr_prov_payment_type != '7':
            card.l10n_gr_prov_payment_type = '7'
            counts['repaired'] += 1
        for xmlid, name, code in GR_POS_PAYMENT_METHODS:
            full_xmlid = f'l10n_gr_provider_pos.{xmlid}_{company.id}'
            owned = self.env.ref(full_xmlid, raise_if_not_found=False)
            if owned:
                # The name is left alone — renaming «IRIS» to «IRIS (άμεση
                # πληρωμή)» is a legitimate clarification, and no myDATA field
                # carries it.
                if owned.l10n_gr_prov_payment_type != code:
                    owned.l10n_gr_prov_payment_type = code
                    counts['repaired'] += 1
                continue
            method = self.create({
                'name': name,
                'company_id': company.id,
                'journal_id': journal.id,
                'l10n_gr_prov_payment_type': code,
            })
            self.env['ir.model.data'].create({
                'name': f'{xmlid}_{company.id}',
                'module': 'l10n_gr_provider_pos',
                'model': 'pos.payment.method',
                'res_id': method.id,
                'noupdate': True,
            })
            counts['created'] += 1
        # Methods somebody else made are never touched — but a bank one with no
        # declared type is transmitting as a card right now, so say how many.
        counts['undeclared'] = len(self.search(
            [('company_id', '=', company.id)]
        ).filtered(lambda m: m._l10n_gr_prov_type_is_guessed()))
        return counts
