# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    # MegEftPosRestServices — the local driver service. Without a URL the
    # module keeps working exactly as before: the cashier charges the terminal
    # by hand and types the transaction id.
    l10n_gr_prov_eft_driver_url = fields.Char(
        string='MegEftPos Driver URL',
        help='Διεύθυνση του MegEftPosRestServices, π.χ. http://127.0.0.1:8080. '
             'Κενό = χειροκίνητη χρέωση τερματικού (ο χειριστής καταχωρεί την '
             'Ταυτότητα Συναλλαγής).')
    l10n_gr_prov_eft_license_key = fields.Char(
        string='MegEftPos License Key', groups='base.group_system',
        help='Το License Key του driver, εκδίδεται ανά ΑΦΜ εμπόρου από την ΙΛΥΔΑ.')
    l10n_gr_prov_eft_vat = fields.Char(
        string='ΑΦΜ Άδειας MegEftPos',
        help='Το ΑΦΜ με το οποίο εκδόθηκε το License Key. Στα δοκιμαστικά '
             'κλειδιά αυτό ΔΕΝ είναι πάντα το ΑΦΜ της εταιρείας — η ΙΛΥΔΑ '
             'ορίζει ποιο ΑΦΜ περνά στον driver. Κενό = το ΑΦΜ της εταιρείας.')

    def _l10n_gr_prov_eft_driver_vat(self):
        """Bare ΑΦΜ the driver licence is bound to."""
        self.ensure_one()
        vat = self.l10n_gr_prov_eft_vat or self.vat or ''
        return vat.upper().replace('EL', '').replace('GR', '').replace(' ', '')
