# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    # MegEftPosRestServices — the local driver service. Without a URL the
    # module keeps working exactly as before: the cashier charges the terminal
    # by hand and types the transaction id.
    l10n_gr_prov_eft_driver_url = fields.Char(
        string='MegEftPos Driver URL',
        help='Διεύθυνση του MegEftPosRestServices, π.χ. http://127.0.0.1:8187 '
             '(η προεπιλεγμένη port του rest.server.port). Κενό = χειροκίνητη '
             'χρέωση τερματικού (ο χειριστής καταχωρεί την Ταυτότητα Συναλλαγής).')
    # Only when MegEftPosRestServices.config sets
    # rest.authorization.method=BASIC_AUTH; with NONE leave both empty.
    l10n_gr_prov_eft_driver_user = fields.Char(
        string='Driver Username',
        help='Μόνο αν ο REST Wrapper τρέχει με rest.authorization.method='
             'BASIC_AUTH. Κενό = χωρίς πιστοποίηση.')
    l10n_gr_prov_eft_driver_password = fields.Char(
        string='Driver Password', groups='base.group_system')
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
