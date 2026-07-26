# -*- coding: utf-8 -*-
from odoo import fields, models

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

    def _l10n_gr_prov_create_pos_payment_methods(self, company):
        """Create the Greek POS payment methods missing from a standard setup.

        Idempotent (own xmlids); they ride the company's bank journal and are
        NOT attached to any POS config — tick the ones you need per till.
        Returns the number created."""
        journal = self.env['account.journal'].search([
            ('type', '=', 'bank'),
            ('company_id', '=', company.id),
        ], limit=1)
        if not journal:
            return 0
        created = 0
        for xmlid, name, code in GR_POS_PAYMENT_METHODS:
            full_xmlid = f'l10n_gr_provider_pos.{xmlid}_{company.id}'
            if self.env.ref(full_xmlid, raise_if_not_found=False):
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
            created += 1
        return created
