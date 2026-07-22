# -*- coding: utf-8 -*-
from odoo import fields, models
from odoo.addons.l10n_gr_edi.models.preferred_classification import INVOICE_TYPES_SELECTION

from .gr_mydata import OTHER_TAXES_CATEGORY_SELECTION

_EXTRA_SELECTION = [
    ('8.4',  '8.4 - Απόδειξη Είσπραξης POS'),
    ('8.5',  '8.5 - Απόδειξη Επιστροφής POS'),
    ('8.6',  '8.6 - Δελτίο Παραγγελίας Εστίασης'),
    ('9.1',  '9.1 - Δελτίο Αποστολής Συσχετιζόμενο'),
    ('9.2',  '9.2 - Συγκεντρωτικό Δελτίο Αποστολής'),
    ('9.3',  '9.3 - Δελτίο Αποστολής'),
    ('10.1', '10.1 - Δελτίο Ποσοτικής Παραλαβής Συσχετιζόμενο'),
    ('10.2', '10.2 - Δελτίο Ποσοτικής Παραλαβής Μη Συσχετιζόμενο'),
]

# (xmlid_suffix, name, code, journal_type, inv_type_default)
# journal_type 'sale'     → Πωλήσεις menu  (out_invoice / out_refund)
# journal_type 'purchase' → Αγορές menu     (in_invoice / in_refund)
GR_JOURNALS = [
    # ── Πωλήσεις ─────────────────────────────────────────────────────────────
    ('gr_j_1_1',   'Τιμολόγιο Πώλησης',                          'ΤΙΜ',  'sale',     '1.1'),
    ('gr_j_1_2',   'Τιμολόγιο Πώλησης / Ενδοκοινοτικές',        'ΤΙΜΕ', 'sale',     '1.2'),
    ('gr_j_1_3',   'Τιμολόγιο Πώλησης / Τρίτες Χώρες',          'ΤΙΜΤ', 'sale',     '1.3'),
    ('gr_j_1_4',   'Τιμολόγιο Πώλησης / Πώληση για Λ/Σ Τρίτων', 'ΤΙΛΤ', 'sale',     '1.4'),
    ('gr_j_1_5',   'Τιμολόγιο Πώλησης / Εκκαθάριση Τρίτων',     'ΤΙΕΚ', 'sale',     '1.5'),
    ('gr_j_1_6',   'Τιμολόγιο Πώλησης / Συμπληρωματικό',        'ΤΙΜΣ', 'sale',     '1.6'),
    ('gr_j_2_1',   'Τιμολόγιο Παροχής Υπηρεσιών',               'ΤΠΥ',  'sale',     '2.1'),
    ('gr_j_2_2',   'ΤΠΥ / Ενδοκοινοτικές',                      'ΤΠΥΕ', 'sale',     '2.2'),
    ('gr_j_2_3',   'ΤΠΥ / Τρίτες Χώρες',                        'ΤΠΥΤ', 'sale',     '2.3'),
    ('gr_j_2_4',   'ΤΠΥ / Συμπληρωματικό',                      'ΤΠΥΣ', 'sale',     '2.4'),
    # Τίτλος Κτήσης is self-billed: we issue/transmit it but book it as OUR
    # expense, so it lives on the purchase side (vendor bill / in_invoice).
    ('gr_j_3_1',   'Τίτλος Κτήσης (μη υπόχρεος)',                'ΤΚ1',  'purchase', '3.1'),
    ('gr_j_3_2',   'Τίτλος Κτήσης (αρνούμενος)',                 'ΤΚ2',  'purchase', '3.2'),
    ('gr_j_1_1_dn', 'Τιμολόγιο – Δελτίο Αποστολής',             'ΤΔΑ',  'sale',     '1.1'),
    ('gr_j_5_1',   'Πιστωτικό Τιμολόγιο (Συσχετισμένο)',        'ΠΙΣΤ', 'sale',     '5.1'),
    ('gr_j_5_1_dn', 'Πιστωτικό Τιμολόγιο – Δελτίο Αποστολής',   'ΠΤΔΑ', 'sale',     '5.1'),
    ('gr_j_5_2',   'Πιστωτικό Τιμολόγιο (Μη Συσχετισμένο)',     'ΠΙΜΣ', 'sale',     '5.2'),
    ('gr_j_6_1',   'Στοιχείο Αυτοπαράδοσης',                    'ΑΥΠ',  'sale',     '6.1'),
    ('gr_j_6_2',   'Στοιχείο Ιδιοχρησιμοποίησης',               'ΙΔΧ',  'sale',     '6.2'),
    ('gr_j_7_1',   'Συμβόλαιο – Έσοδα',                         'ΣΥΜΕ', 'sale',     '7.1'),
    ('gr_j_8_1',   'Ενοίκια – Έσοδα',                           'ΕΝΟΕ', 'sale',     '8.1'),
    ('gr_j_8_2',   'Ειδικό Στοιχείο Τέλους Διαμονής',           'ΤΔΙ',  'sale',     '8.2'),
    ('gr_j_8_4',   'Απόδειξη Είσπραξης POS',                    'ΠΟΣ',  'sale',     '8.4'),
    ('gr_j_8_5',   'Απόδειξη Επιστροφής POS',                   'ΠΟΣΕ', 'sale',     '8.5'),
    ('gr_j_8_6',   'Δελτίο Παραγγελίας Εστίασης',               'ΔΠΕ',  'sale',     '8.6'),
    ('gr_j_9_1',   'Δελτίο Αποστολής Συσχετιζόμενο',            'ΔΑΣ',  'sale',     '9.1'),
    ('gr_j_9_2',   'Συγκεντρωτικό Δελτίο Αποστολής',            'ΣΔΑ',  'sale',     '9.2'),
    ('gr_j_9_3',   'Δελτίο Αποστολής',                          'ΔΑ',   'sale',     '9.3'),
    ('gr_j_10_1',  'Δελτίο Ποσοτικής Παραλαβής Συσχετιζόμενο',  'ΔΠΠ',  'sale',     '10.1'),
    ('gr_j_10_2',  'Δελτίο Ποσοτικής Παραλαβής Μη Συσχετ.',     'ΔΠΠΜ', 'sale',     '10.2'),
    ('gr_j_11_1',  'Απόδειξη Λιανικής Πώλησης',                 'ΑΛΠ',  'sale',     '11.1'),
    ('gr_j_11_2',  'Απόδειξη Παροχής Υπηρεσιών',                'ΑΠΥ',  'sale',     '11.2'),
    ('gr_j_11_3',  'Απλοποιημένο Τιμολόγιο',                    'ΑΠΛ',  'sale',     '11.3'),
    ('gr_j_11_4',  'Πιστωτικό Λιανικής',                        'ΠΛΠ',  'sale',     '11.4'),
    ('gr_j_11_5',  'ΑΛΠ για Λ/Σ Τρίτων',                       'ΑΛΠΤ', 'sale',     '11.5'),
    # ── Αγορές ───────────────────────────────────────────────────────────────
    ('gr_j_13_1',  'Έξοδα – Αγορές Λιανικής',                   'ΑΓΛ',  'purchase', '13.1'),
    ('gr_j_13_2',  'Παροχή Λιανικής Ημεδαπής/Αλλοδαπής',       'ΠΑΡ',  'purchase', '13.2'),
    ('gr_j_13_3',  'Κοινόχρηστα',                               'ΚΟΙ',  'purchase', '13.3'),
    ('gr_j_13_4',  'Συνδρομές',                                  'ΣΥΝ',  'purchase', '13.4'),
    ('gr_j_13_30', 'Αυτοαπογραφόμενα Έξοδα (Δυναμικό)',         'ΑΑΔ',  'purchase', '13.30'),
    ('gr_j_13_31', 'Πιστωτικό Λιανικής Αγοράς',                 'ΠΛΑ',  'purchase', '13.31'),
    ('gr_j_14_1',  'Τιμολόγιο / Ενδοκοινοτικές Αποκτήσεις',    'ΕΑΠ',  'purchase', '14.1'),
    ('gr_j_14_2',  'Τιμολόγιο / Αποκτήσεις Τρίτων Χωρών',      'ΑΠΤΧ', 'purchase', '14.2'),
    ('gr_j_14_3',  'Τιμολόγιο / Ενδοκοινοτικές Λήψεις',        'ΕΛΠ',  'purchase', '14.3'),
    ('gr_j_14_4',  'Τιμολόγιο / Λήψεις Τρίτων Χωρών',          'ΛΗΤΧ', 'purchase', '14.4'),
    ('gr_j_14_5',  'ΕΦΚΑ',                                       'ΕΦΚ',  'purchase', '14.5'),
    ('gr_j_14_30', 'Αυτοαπογραφόμενα Αγορές (Δυναμικό)',        'ΑΑΔΑ', 'purchase', '14.30'),
    ('gr_j_14_31', 'Πιστωτικό Αγοράς Ημεδαπής/Αλλοδαπής',      'ΠΑΠ',  'purchase', '14.31'),
    ('gr_j_15_1',  'Συμβόλαιο – Έξοδα',                         'ΣΥΜΞ', 'purchase', '15.1'),
    ('gr_j_16_1',  'Ενοίκια – Έξοδα',                           'ΕΝΟΞ', 'purchase', '16.1'),
    ('gr_j_17_1',  'Μισθοδοσία',                                 'ΜΙΣ',  'purchase', '17.1'),
    ('gr_j_17_2',  'Αποσβέσεις',                                 'ΑΠΟ',  'purchase', '17.2'),
    ('gr_j_17_3',  'Λοιπές Εγγραφές Εσόδων – Λογιστική Βάση',  'ΛΕΕ',  'purchase', '17.3'),
    ('gr_j_17_4',  'Λοιπές Εγγραφές Εσόδων – Φορολογική Βάση', 'ΛΕΦ',  'purchase', '17.4'),
    ('gr_j_17_5',  'Λοιπές Εγγραφές Εξόδων – Λογιστική Βάση',  'ΛΕΞ',  'purchase', '17.5'),
    ('gr_j_17_6',  'Λοιπές Εγγραφές Εξόδων – Φορολογική Βάση', 'ΛΕΞΦ', 'purchase', '17.6'),
]

# Journals whose documents are invoice + delivery note combined
# (isDeliveryNote=true in myDATA: ΤΔΑ = 1.1, ΠΤΔΑ = 5.1 with dispatch data).
DELIVERY_NOTE_JOURNALS = frozenset({'gr_j_1_1_dn', 'gr_j_5_1_dn'})

# Retail receipt types print on an 80mm roll by default (ΑΛΠ/ΑΠΥ + their
# credit and third-party variants) — everything else defaults to A4.
RETAIL_80MM_TYPES = frozenset({'11.1', '11.2', '11.3', '11.4', '11.5'})


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    l10n_gr_prov_delivery_note = fields.Boolean(
        string='Τιμολόγιο – Δελτίο Αποστολής',
        help='Τα παραστατικά αυτού του ημερολογίου είναι και δελτία αποστολής '
             '(isDeliveryNote): αποστέλλονται με στοιχεία διακίνησης.',
    )

    l10n_gr_prov_print_form = fields.Selection([
        ('standard', 'Τυπική Odoo'),
        ('gr_a4', 'Παραστατικό GR (A4)'),
        ('gr_80mm', 'Απόδειξη GR (80mm)'),
    ], string='Φόρμα Εκτύπωσης', default='gr_a4',
        help='Ποια φόρμα χρησιμοποιεί η εκτύπωση «Παραστατικό» για τα '
             'έγγραφα αυτού του ημερολογίου — A4 για τιμολόγια, 80mm για '
             'αποδείξεις λιανικής σε εκτυπωτή ρολού.')

    l10n_gr_prov_other_taxes_default = fields.Selection(
        selection=OTHER_TAXES_CATEGORY_SELECTION,
        string='Προεπιλογή Λοιπών Φόρων (8.2)',
        help='Για ημερολόγια Ειδικού Στοιχείου (8.2): η κατηγορία τέλους '
             'διαμονής του καταλύματος (π.χ. Ξενοδοχείο 3 αστέρων) — '
             'συμπληρώνεται αυτόματα σε κάθε νέο παραστατικό.',
    )

    l10n_gr_edi_inv_type_default = fields.Selection(
        selection=INVOICE_TYPES_SELECTION + _EXTRA_SELECTION,
        string='Προεπιλογή Τύπου myDATA',
        help='Όταν οριστεί, νέα παραστατικά αυτού του ημερολογίου '
             'θα παίρνουν αυτόματα αυτόν τον τύπο myDATA.',
    )

    # Fallback default accounts so a fresh setup never hits «Missing required
    # account»: the accountant refines per journal/product later.
    _GR_JOURNAL_DEFAULT_ACCOUNT = {
        'sale': 'l10n_gr_70_01_01',       # Πωλήσεις εμπορευμάτων
        'purchase': 'l10n_gr_64_12_02',   # Λοιπά έξοδα
    }

    # NOTE: journals are deliberately NOT declared via @template — the chart
    # loader merges template journals onto existing ones (it grabbed the stock
    # sale journal and rewrote its code). Creation goes exclusively through
    # _l10n_gr_prov_create_journals (post_init hook + the settings button),
    # which builds fresh records under our own xmlids and never touches
    # journals it does not own.

    def _l10n_gr_prov_journal_defaults(self, company):
        """Backfill for existing companies: no refund sequences anywhere, and
        a default income/expense account on journals that lack one."""
        counts = {'refund_seq': 0, 'accounts': 0}
        journals = self.search([
            ('company_id', '=', company.id),
            ('type', 'in', ('sale', 'purchase')),
        ])
        stale = journals.filtered('refund_sequence')
        stale.write({'refund_sequence': False})
        counts['refund_seq'] = len(stale)
        for jtype, template_id in self._GR_JOURNAL_DEFAULT_ACCOUNT.items():
            account = self.env.ref(
                f'account.{company.id}_{template_id}', raise_if_not_found=False)
            if not account:
                continue
            missing = journals.filtered(
                lambda j: j.type == jtype and not j.default_account_id)
            missing.write({'default_account_id': account.id})
            counts['accounts'] += len(missing)
        retail_wrong_form = journals.filtered(
            lambda j: j.l10n_gr_edi_inv_type_default in RETAIL_80MM_TYPES
            and j.l10n_gr_prov_print_form != 'gr_80mm')
        retail_wrong_form.write({'l10n_gr_prov_print_form': 'gr_80mm'})
        counts['print_forms'] = len(retail_wrong_form)
        return counts

    def _l10n_gr_prov_create_journals(self, company):
        """Create missing Greek myDATA journals for an existing company.
        Idempotent — existing codes are skipped. Returns counts for the UI."""
        counts = self._l10n_gr_prov_journal_defaults(company)
        counts['created'] = 0
        for xmlid, name, code, jtype, inv_type in GR_JOURNALS:
            full_xmlid = f'l10n_gr_provider_base.{xmlid}_{company.id}'
            if self.env.ref(full_xmlid, raise_if_not_found=False):
                continue
            existing = self.search([
                ('code', '=', code),
                ('company_id', '=', company.id),
            ], limit=1)
            if existing:
                # a foreign journal holds our code — leave it alone entirely
                continue
            default_account = self.env.ref(
                f'account.{company.id}_{self._GR_JOURNAL_DEFAULT_ACCOUNT[jtype]}',
                raise_if_not_found=False)
            # Use a temp unique alias to avoid conflicts; clear it after creation.
            temp_alias = f'gr-mydata-{code.lower()}-{company.id}'
            journal = self.with_context(mail_create_nosubscribe=True).create({
                'name': name,
                'code': code,
                'type': jtype,
                'company_id': company.id,
                'show_on_dashboard': False,
                'refund_sequence': False,
                'default_account_id': default_account.id if default_account else False,
                'l10n_gr_edi_inv_type_default': inv_type,
                'l10n_gr_prov_delivery_note': xmlid in DELIVERY_NOTE_JOURNALS,
                'l10n_gr_prov_print_form':
                    'gr_80mm' if inv_type in RETAIL_80MM_TYPES else 'gr_a4',
                'alias_name': temp_alias,
            })
            if journal.alias_id:
                alias = journal.alias_id
                journal.sudo().write({'alias_id': False})
                alias.sudo().unlink()
            self.env['ir.model.data'].create({
                'name': f'{xmlid}_{company.id}',
                'module': 'l10n_gr_provider_base',
                'model': 'account.journal',
                'res_id': journal.id,
                'noupdate': True,
            })
            counts['created'] += 1
        return counts
