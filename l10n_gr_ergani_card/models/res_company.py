import re

from odoo import fields, models

ERGANI_MODES = [
    ('off', 'Ανενεργό'),
    ('simulation', 'Προσομοίωση'),
    ('trial', 'Δοκιμαστικό (trial)'),
    ('production', 'Παραγωγικό'),
]
TRIAL_URL = 'https://trialv2eservices.yeka.gr/WebServicesApi/api/'
# Answers 401 to an anonymous call (checked 2026-10-24); that it is ΕΡΓΑΝΗ ΙΙ and not
# the old ΕΡΓΑΝΗ Ι is confirmed only by the first «Δοκιμή σύνδεσης» with real credentials.
PRODUCTION_URL = 'https://eservices.yeka.gr/WebServicesAPI/api/'


class ResCompany(models.Model):
    _inherit = 'res.company'

    ergani_mode = fields.Selection(
        ERGANI_MODES, string='ΕΡΓΑΝΗ', default='simulation', required=True,
        help='Προσομοίωση: οι κάρτες καταγράφονται αλλά δεν στέλνονται πουθενά.')
    ergani_username = fields.Char(string='Χρήστης ΕΡΓΑΝΗ', groups='base.group_system')
    ergani_password = fields.Char(string='Κωδικός ΕΡΓΑΝΗ', groups='base.group_system')
    ergani_branch_aa = fields.Integer(string='Α/Α Παραρτήματος', default=0)
    ergani_late_reason_code = fields.Char(
        string='Κωδικός αιτιολογίας «σύνδεση ΕΡΓΑΝΗ»',
        help='Μπαίνει αυτόματα σε εκπρόθεσμη κάρτα όταν η καθυστέρηση οφείλεται σε '
             'καταγεγραμμένη αποτυχία σύνδεσης. Ο κωδικός επιβεβαιώνεται στο trial.')
    ergani_late_reason_id = fields.Many2one(
        'ergani.delay.reason', string='Αιτιολογία «σύνδεση ΕΡΓΑΝΗ»',
        help='Μπαίνει αυτόματα σε εκπρόθεσμη κάρτα όταν η καθυστέρηση οφείλεται σε '
             'καταγεγραμμένη αποτυχία σύνδεσης. Η λίστα έρχεται από το ΕΡΓΑΝΗ.')
    ergani_night_shift = fields.Boolean(
        string='Νυχτερινή εργασία',
        help='Η αποχώρηση μπορεί να γίνει την επόμενη μέρα έως τις 11:00, με ημερομηνία αναφοράς '
             'της προσέλευσης (Ενιαίος Οδηγός σ. 18). Ανενεργό: η χθεσινή ανοιχτή προσέλευση '
             'θεωρείται ξεχασμένη, ώστε να μη «καταπιεί» τη σημερινή.')
    ergani_manager_id = fields.Many2one(
        'res.users', string='Υπεύθυνος ΕΡΓΑΝΗ',
        default=lambda self: self.env.ref('base.user_admin', raise_if_not_found=False),
        help='Παίρνει τις ειδοποιήσεις για προβλήματα αποστολής.')
    ergani_tolerance_minutes = fields.Integer(
        string='Ανοχή καθυστέρησης / προαναχώρησης (λεπτά)', default=10,
        help='Μόνο για την «Πληροφορία προσωπικού» της κατάστασης κινήσεων. Η εργασία έξω '
             'από το ωράριο (πριν την έναρξη, μετά τη λήξη, σε ρεπό) δεν έχει ανοχή.')
    ergani_paused = fields.Boolean(string='Παύση αποστολής', readonly=True)
    ergani_pause_reason = fields.Char(string='Αιτία παύσης', readonly=True)

    def write(self, vals):
        # Tokens belong to one environment and one account: drop them when
        # either changes, so a trial token never reaches production.
        if {'ergani_mode', 'ergani_username', 'ergani_password'} & set(vals):
            self.env['ergani.session'].sudo().search(
                [('company_id', 'in', self.ids)]).unlink()
        return super().write(vals)

    def _ergani_base_url(self):
        self.ensure_one()
        if self.ergani_mode == 'production':
            return PRODUCTION_URL
        return TRIAL_URL

    def _ergani_vat(self):
        """Company VAT as ΕΡΓΑΝΗ wants it: 9 digits, no EL/GR prefix."""
        self.ensure_one()
        vat = re.sub(r'[^0-9A-Za-z]', '', self.vat or '').upper()
        return vat[2:] if vat[:2] in ('EL', 'GR') else vat
