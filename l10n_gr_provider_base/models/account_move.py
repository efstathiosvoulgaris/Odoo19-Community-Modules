# -*- coding: utf-8 -*-
import base64
import logging
import unicodedata
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from .gr_mydata import (
    ProviderUnreachableError,
    WITHHOLDING_CATEGORY_SELECTION, WITHHOLDING_CATEGORY_RATE,
    FEES_CATEGORY_SELECTION, FEES_CATEGORY_RATE, FEES_CATEGORY_FIXED,
    OTHER_TAXES_CATEGORY_SELECTION, OTHER_TAXES_CATEGORY_RATE, OTHER_TAXES_CATEGORY_FIXED,
    STAMP_DUTY_CATEGORY_SELECTION, STAMP_DUTY_CATEGORY_RATE,
    partner_class, journal_types_for_class,
    INV_TYPE_ZERO_TAX, DOMESTIC_TAX_RATES, DOMESTIC_ZERO_TAX_TEMPLATES, gr_tax,
    TYPES_DISPATCH,
    VAT_EXEMPTION_CODES, TYPES_SELF_BILLED, TYPES_POS_ONLY,
    TYPES_NO_VAT, valid_cls_categories,
)

_logger = logging.getLogger(__name__)

PROVIDER_STATES = [
    ('to_send', 'To Send'),
    # TF-2: the provider accepted the document but AADE was unreachable — it sits
    # in the provider's transmission queue; the QR/identifier already exist and
    # the printed document must carry them. The MARK arrives later via recovery.
    ('queued', 'Queued at Provider (AADE offline)'),
    # TF-1: WE could not reach the provider — the document was issued with a
    # locally signed offline QR (Α.1112/2025) and must be transmitted online
    # within 1 calendar day. The cron keeps retrying.
    ('offline', 'Offline QR (προς διαβίβαση)'),
    ('sent', 'Issued (Marked)'),
    ('error', 'Error'),
]


class AccountMove(models.Model):
    _inherit = 'account.move'

    # ── Provider transmission state ───────────────────────────────────────────
    l10n_gr_prov_state = fields.Selection(
        PROVIDER_STATES, string='Provider Status', copy=False, tracking=True)
    l10n_gr_prov_error = fields.Text(string='Provider Error', copy=False)
    l10n_gr_prov_send_datetime = fields.Datetime(string='Provider Sent At', copy=False)

    # ── Legal markings returned by the provider (A.1035/2020) ────────────────
    l10n_gr_prov_mark = fields.Char(string='MARK (Provider)', copy=False)
    l10n_gr_prov_invoice_id = fields.Char(string='Provider Invoice ID', copy=False)
    l10n_gr_prov_verification_hash = fields.Char(
        string='Authentication String', copy=False,
        help='SHA-1 verification hash (Συμβολοσειρά Αυθεντικοποίησης), Appendix B1 of A.1035/2020.')
    l10n_gr_prov_invoice_identifier = fields.Char(
        string='Invoice Identifier', copy=False,
        help='SHA-1 invoice identifier (Αναγνωριστικό Παραστατικού), Appendix B2 of A.1035/2020.')
    l10n_gr_prov_uid = fields.Char(
        string='myDATA UID', copy=False, readonly=True,
        help='Deterministic document UID (ET-7): SHA-1 over issuer VAT, issue date, '
             'branch, invoice type, series and number. Used to look the document up '
             'at the provider when a submission response was lost.')
    l10n_gr_prov_offline_token = fields.Char(
        string='Offline QR Token', copy=False, readonly=True,
        help='JWS token of the offline QR issued while the provider was '
             'unreachable (TF-1). Kept for the audit link between the UID and '
             'the token required by Α.1112/2025.')
    l10n_gr_prov_qr_url = fields.Char(string='Provider QR URL', copy=False)
    l10n_gr_prov_provider_url = fields.Char(string='Provider Site', copy=False)
    l10n_gr_prov_previously_submitted = fields.Boolean(
        string='Previously Submitted', copy=False,
        help='Set when the provider recovered the marking from a prior submission '
             '(AADE error 228 handling).')
    l10n_gr_prov_pdf_uploaded = fields.Boolean(string='PDF Uploaded to Provider', copy=False)

    # ── B2G (Peppol) ──────────────────────────────────────────────────────────
    l10n_gr_prov_b2g = fields.Boolean(
        string='B2G (Public Sector)', copy=False,
        help='Route this document through the Peppol network (public contracts).')
    l10n_gr_prov_contract_ref = fields.Char(
        string='Contract Reference (BT-12, ΑΔΑΜ)', copy=False,
        help='Public contract reference (ΑΔΑΜ), e.g. 20SYMV006467658.')
    l10n_gr_prov_budget_type = fields.Selection(
        selection=[
            ('1', '1 - Τακτικός Προϋπολογισμός (ΑΔΑ Ανάληψης)'),
            ('2', '2 - Πρόγραμμα Δημοσίων Επενδύσεων (Ενάριθμος έργου)'),
            ('3', '3 - Λοιποί Προϋπολογισμοί (ΑΔΑ Ανάληψης)'),
        ],
        string='Budget Type (BT-11)', copy=False, default='1')
    l10n_gr_prov_budget_ref = fields.Char(
        string='Budget Identifier (BT-11)', copy=False,
        help='ΑΔΑ Ανάληψης (budget types 1/3) or Ενάριθμος έργου ΠΔΕ (type 2). '
             'Sent as "<type>|<identifier>".')
    l10n_gr_prov_purchase_order_ref = fields.Char(
        string='Purchase Order (BT-13)', copy=False,
        help='Purchase order reference issued by the buyer (Αναγνωριστικό Εντολής Αγοράς).')
    l10n_gr_prov_receiving_advice_ref = fields.Char(
        string='Receiving Advice Reference (BT-15)', copy=False,
        help='Reference of the goods/services receiving advice (Αναγνωριστικό '
             'Ειδοποίησης Παραλαβής), when the buyer confirms receipt before '
             'payment. B2G element; optional.')
    l10n_gr_prov_buyer_ref = fields.Char(
        string='Buyer Reference (BT-10)', copy=False,
        compute='_compute_l10n_gr_prov_buyer_ref', store=True, readonly=False,
        help='Routing reference: "<Περιγραφή Α.Α>|<ΑΑΗΤ or internal unit code>", '
             'e.g. "Νοσοκ ΕΥΑΓΓΕΛΙΣΜΟΣ|XYZ123ABC". Defaults from the customer '
             'name and its ΑΑΗΤ code; adjust if the contracting authority differs.')
    l10n_gr_prov_b2g_status = fields.Char(string='B2G Status', copy=False)

    # ── Dispatch note (9.3) ───────────────────────────────────────────────────
    # v2.0.1 §8.14 — codes 6/15/16/17 exist in the schema but are marked
    # «δεν είναι δυνατή η αποστολή» (blocked at ILYDA validation).
    l10n_gr_prov_move_purpose = fields.Selection(
        selection=[
            ('1',  '1 - Πώληση'),
            ('2',  '2 - Πώληση για Λογαριασμό Τρίτων'),
            ('3',  '3 - Δειγματισμός'),
            ('4',  '4 - Έκθεση'),
            ('5',  '5 - Επιστροφή'),
            ('6',  '6 - Φύλαξη (μη αποδεκτό προς αποστολή)'),
            ('7',  '7 - Επεξεργασία / Συναρμολόγηση'),
            ('8',  '8 - Μεταξύ Εγκαταστάσεων Οντότητας'),
            ('9',  '9 - Αγορά'),
            ('10', '10 - Εφοδιασμός πλοίων και αεροσκαφών'),
            ('11', '11 - Δωρεάν διάθεση'),
            ('12', '12 - Εγγύηση'),
            ('13', '13 - Χρησιδανεισμός'),
            ('14', '14 - Αποθήκευση σε Τρίτους'),
            ('15', '15 - Επιστροφή από Φύλαξη (μη αποδεκτό προς αποστολή)'),
            ('16', '16 - Ανακύκλωση (μη αποδεκτό προς αποστολή)'),
            ('17', '17 - Καταστροφή άχρηστου υλικού (μη αποδεκτό προς αποστολή)'),
            ('18', '18 - Διακίνηση Παγίων (Ενδοδιακίνηση)'),
            ('19', '19 - Λοιπές Διακινήσεις'),
            ('20', '20 - Μεταφορές / Ταχυμεταφορές'),
        ],
        string='Σκοπός Διακίνησης', copy=False, default='1',
        help='Mandatory for dispatch notes (9.x). Σκοπός Διακίνησης per myDATA v2.0.1 §8.14.'
    )

    # Δελτίο Παραγγελίας Εστίασης (8.6): table number, mandatory for the type
    l10n_gr_prov_table_aa = fields.Char(
        string='ΑΑ Τραπεζιού', size=50, copy=False,
        help='Αριθμός τραπεζιού — υποχρεωτικό για Δελτίο Παραγγελίας Εστίασης (8.6).')

    # ── myDATA invoice fields (clean-slate, no l10n_gr_edi dependency) ───────
    # inv_type and payment_method come from l10n_gr_edi_inv_type / l10n_gr_edi_payment_method
    l10n_gr_prov_withholding_category = fields.Selection(
        selection=WITHHOLDING_CATEGORY_SELECTION,
        string='Κρατήσεις (κατηγορία ΑΑΔΕ)',
        copy=False,
        help='AADE withholding tax category (§8.4). Amount is auto-calculated for fixed-rate '
             'categories; enter manually for variable-rate ones (11,14,15,16,17).',
    )
    l10n_gr_prov_withholding_amount = fields.Monetary(
        string='Κρατήσεις (ποσό)',
        currency_field='currency_id',
        compute='_compute_l10n_gr_prov_withholding_amount',
        store=True, readonly=False, copy=False,
        help='Auto-calculated from the selected AADE category rate × net total. '
             'Editable for variable-rate categories.',
    )
    l10n_gr_prov_stamp_duty_category = fields.Selection(
        selection=STAMP_DUTY_CATEGORY_SELECTION,
        string='Ψηφιακό Τέλος Συναλλαγής (κατηγορία ΑΑΔΕ)',
        copy=False,
        help='AADE digital transaction fee category (v2.0.1 §8.6, πρώην χαρτόσημο). '
             'Categories 1–3 auto-calculate the amount.',
    )
    l10n_gr_prov_stamp_duty_amount = fields.Monetary(
        string='Ψηφιακό Τέλος Συναλλαγής (ποσό)',
        currency_field='currency_id',
        compute='_compute_l10n_gr_prov_stamp_duty_amount',
        store=True, readonly=False, copy=False,
        help='Auto-calculated for fixed-rate categories (1,2,3); manual otherwise.',
    )
    l10n_gr_prov_fees_category = fields.Selection(
        selection=FEES_CATEGORY_SELECTION,
        string='Τέλη (κατηγορία ΑΑΔΕ)',
        copy=False,
        help='AADE fees category (§8.7). Percentage categories auto-calculate the amount.',
    )
    l10n_gr_prov_fees_amount = fields.Monetary(
        string='Τέλη (ποσό)',
        currency_field='currency_id',
        compute='_compute_l10n_gr_prov_fees_amount',
        store=True, readonly=False, copy=False,
        help='Auto-calculated for percentage categories; manual for fixed-€/unit ones.',
    )
    l10n_gr_prov_other_taxes_category = fields.Selection(
        selection=OTHER_TAXES_CATEGORY_SELECTION,
        string='Λοιποί Φόροι (κατηγορία ΑΑΔΕ)',
        copy=False,
        help='AADE other taxes category (§8.5). Percentage categories auto-calculate the amount.',
    )
    l10n_gr_prov_other_taxes_amount = fields.Monetary(
        string='Λοιποί Φόροι (ποσό)',
        currency_field='currency_id',
        compute='_compute_l10n_gr_prov_other_taxes_amount',
        store=True, readonly=False, copy=False,
        help='Auto-calculated for percentage categories; manual for fixed-€/unit ones.',
    )

    def _l10n_gr_prov_apply_rate(self, cat_field, amount_field, rate_map):
        """Amount = net × category rate; 0 when no category; untouched (manual)
        when the category has no rate in the map."""
        for move in self:
            cat = move[cat_field]
            rate = rate_map.get(cat, 0.0)
            if not cat:
                move[amount_field] = 0.0
            elif rate:
                net = Decimal(str(move.amount_untaxed))
                move[amount_field] = float(
                    (net * Decimal(str(rate))).quantize(Decimal('0.01'), ROUND_HALF_UP)
                )
            # else: manual category → leave user value

    @api.depends('l10n_gr_prov_withholding_category', 'amount_untaxed')
    def _compute_l10n_gr_prov_withholding_amount(self):
        self._l10n_gr_prov_apply_rate(
            'l10n_gr_prov_withholding_category', 'l10n_gr_prov_withholding_amount',
            WITHHOLDING_CATEGORY_RATE)

    @api.depends('l10n_gr_prov_stamp_duty_category', 'amount_untaxed')
    def _compute_l10n_gr_prov_stamp_duty_amount(self):
        self._l10n_gr_prov_apply_rate(
            'l10n_gr_prov_stamp_duty_category', 'l10n_gr_prov_stamp_duty_amount',
            STAMP_DUTY_CATEGORY_RATE)

    @api.depends('l10n_gr_prov_fees_category', 'amount_untaxed')
    def _compute_l10n_gr_prov_fees_amount(self):
        self._l10n_gr_prov_apply_rate(
            'l10n_gr_prov_fees_category', 'l10n_gr_prov_fees_amount',
            FEES_CATEGORY_RATE)

    @api.depends('l10n_gr_prov_other_taxes_category', 'amount_untaxed')
    def _compute_l10n_gr_prov_other_taxes_amount(self):
        self._l10n_gr_prov_apply_rate(
            'l10n_gr_prov_other_taxes_category', 'l10n_gr_prov_other_taxes_amount',
            OTHER_TAXES_CATEGORY_RATE)

    # Fixed-€ categories (hotel/room taxes, €/τεμ fees): default the label's
    # amount on selection; stays editable (real amount = unit × nights/pieces).
    @api.onchange('l10n_gr_prov_fees_category')
    def _onchange_l10n_gr_prov_fees_fixed(self):
        fixed = FEES_CATEGORY_FIXED.get(self.l10n_gr_prov_fees_category)
        if fixed:
            self.l10n_gr_prov_fees_amount = fixed

    @api.onchange('l10n_gr_prov_other_taxes_category')
    def _onchange_l10n_gr_prov_other_taxes_fixed(self):
        fixed = OTHER_TAXES_CATEGORY_FIXED.get(self.l10n_gr_prov_other_taxes_category)
        if fixed:
            self.l10n_gr_prov_other_taxes_amount = fixed

    @api.depends('partner_id', 'l10n_gr_prov_b2g')
    def _compute_l10n_gr_prov_buyer_ref(self):
        for move in self:
            # Only default when B2G is active and the field has no value yet.
            # Check per-record (not once before the loop) to handle multi-record sets.
            if move.l10n_gr_prov_buyer_ref or not move.l10n_gr_prov_b2g:
                continue
            partner = move.commercial_partner_id
            if partner.l10n_gr_prov_aaht:
                move.l10n_gr_prov_buyer_ref = f'{partner.name}|{partner.l10n_gr_prov_aaht}'
            elif partner:
                move.l10n_gr_prov_buyer_ref = partner.name or False

    journal_id_inv_type_default = fields.Boolean(
        compute='_compute_journal_id_inv_type_default')

    @api.depends('journal_id.l10n_gr_edi_inv_type_default')
    def _compute_journal_id_inv_type_default(self):
        for move in self:
            move.journal_id_inv_type_default = bool(move.journal_id.l10n_gr_edi_inv_type_default)

    # ── Partner-driven journal net ────────────────────────────────────────────
    # Narrow core's suitable_journal_ids (which drives the journal_id domain) to
    # the myDATA types valid for the selected partner's class. Journals with no
    # myDATA type default are left untouched (non-GR / generic journals).
    @api.depends('move_type', 'company_id',
                 'partner_id.is_company', 'partner_id.country_id', 'partner_id.vat')
    def _compute_suitable_journal_ids(self):
        super()._compute_suitable_journal_ids()
        eu = self.env.ref('base.europe', raise_if_not_found=False)
        eu_codes = set(eu.country_ids.mapped('code') if eu else []) - {'GR'}
        for move in self:
            partner = move.partner_id
            if (not partner
                    or not move.is_sale_document(include_receipts=True)
                    or not move.company_id._l10n_gr_prov_active()):
                continue
            cls = partner_class(
                partner.is_company, partner.country_id.code,
                eu_codes, bool(partner.vat),
            )
            valid = journal_types_for_class(cls)
            move.suitable_journal_ids = move.suitable_journal_ids.filtered(
                lambda j: not j.l10n_gr_edi_inv_type_default
                or j.l10n_gr_edi_inv_type_default in valid
            )

    # ── Journal-driven tax net ────────────────────────────────────────────────
    # Cross-border journals (1.2/2.2/1.3/2.3) → only their mapped 0% tax;
    # domestic GR journals → standard + island rates + domestic 0% specials;
    # dispatch / non-GR / purchase → no extra restriction beyond core's.
    l10n_gr_prov_suitable_tax_ids = fields.Many2many(
        'account.tax', compute='_compute_l10n_gr_prov_suitable_tax_ids')

    @api.depends('journal_id.l10n_gr_edi_inv_type_default', 'company_id')
    def _compute_l10n_gr_prov_suitable_tax_ids(self):
        Tax = self.env['account.tax']
        for move in self:
            is_sale = move.is_sale_document(include_receipts=True)
            base = [
                ('type_tax_use', '=', 'sale' if is_sale else 'purchase'),
                ('company_id', 'parent_of', move.company_id.id),
            ]
            inv_type = move.journal_id.l10n_gr_edi_inv_type_default
            if (not is_sale
                    or not move.company_id._l10n_gr_prov_active()
                    or not inv_type or inv_type in TYPES_DISPATCH):
                move.l10n_gr_prov_suitable_tax_ids = Tax.search(base)
            elif inv_type in INV_TYPE_ZERO_TAX:
                # Resolve by chart xmlid, not name — taxes are user-renameable.
                tax = gr_tax(self.env, move.company_id, INV_TYPE_ZERO_TAX[inv_type][0])
                move.l10n_gr_prov_suitable_tax_ids = tax or Tax.search(base)
            else:
                zero = Tax
                for template_id in DOMESTIC_ZERO_TAX_TEMPLATES:
                    zero |= gr_tax(self.env, move.company_id, template_id) or Tax
                move.l10n_gr_prov_suitable_tax_ids = Tax.search(
                    base + [('amount', 'in', DOMESTIC_TAX_RATES)]) | zero

    l10n_gr_prov_applicable = fields.Boolean(
        compute='_compute_l10n_gr_prov_applicable')

    @api.depends('move_type', 'company_id.l10n_gr_prov_provider', 'country_code',
                 'journal_id.l10n_gr_edi_inv_type_default')
    def _compute_l10n_gr_prov_applicable(self):
        for move in self:
            # Self-billing types (3.1/3.2) are vendor bills we still transmit;
            # every other purchase document is issued by the supplier, not us.
            self_billed = (
                move.is_purchase_document(include_receipts=True)
                and move.journal_id.l10n_gr_edi_inv_type_default in TYPES_SELF_BILLED)
            move.l10n_gr_prov_applicable = (
                (move.is_sale_document(include_receipts=True) or self_billed)
                and move.country_code == 'GR'
                and move.company_id._l10n_gr_prov_active()
            )

    @api.model
    def _get_suitable_journal_ids(self, move_type, company=False):
        """Drop POS/restaurant journals (8.4/8.5/8.6) from the invoice journal
        picker — those documents come from the cash register / ordering system,
        not manual invoicing. The journals still exist for that future flow."""
        journals = super()._get_suitable_journal_ids(move_type, company)
        return journals.filtered(
            lambda j: j.l10n_gr_edi_inv_type_default not in TYPES_POS_ONLY)

    # ── Tax guards: block wrong taxes at post, not at send ───────────────────
    ISLAND_RATES = (17, 9, 4)
    MAINLAND_RATES = (24, 13, 6)

    @api.model
    def _l10n_gr_prov_fp_is_island(self, fp):
        """The Aegean-islands regime is recognised structurally — the fiscal
        position carries replacement taxes at the reduced island rates — not by
        name/xmlid, which vary per chart instance."""
        return bool(fp) and any(
            int(tax.amount) in self.ISLAND_RATES
            for tax in fp.tax_ids if tax.original_tax_ids)

    def _l10n_gr_prov_check_tax_guard(self):
        """Company-toggleable pre-post validation of everything tax-shaped.

        Without it, a wrong-tax document posts cleanly and only fails at the
        provider (or as an AADE MDP error). Collects every problem and raises
        one UserError so the user fixes the document in one pass."""
        for move in self:
            company = move.company_id
            if not (company._l10n_gr_prov_active()
                    and move.country_code == 'GR'
                    and (move.is_sale_document(include_receipts=True)
                         or (move.is_purchase_document(include_receipts=True)
                             and move.journal_id.l10n_gr_edi_inv_type_default
                             in TYPES_SELF_BILLED))):
                continue
            inv_type = move.journal_id.l10n_gr_edi_inv_type_default
            if not inv_type or inv_type in TYPES_DISPATCH or inv_type in TYPES_NO_VAT:
                continue
            errors = []
            lines = move.invoice_line_ids.filtered(
                lambda l: l.display_type == 'product')
            needs_cls = bool(valid_cls_categories(inv_type))
            is_island = self._l10n_gr_prov_fp_is_island(move.fiscal_position_id)

            if company.l10n_gr_prov_guard_tax:
                suitable = move.l10n_gr_prov_suitable_tax_ids
                for line in lines:
                    label = line.product_id.display_name or line.name or _('γραμμή')
                    tax = line.tax_ids[:1]
                    if not tax:
                        errors.append(_('• %s: η γραμμή δεν έχει ΦΠΑ.', label))
                        continue
                    if suitable and tax not in suitable:
                        errors.append(_(
                            '• %(line)s: ο φόρος «%(tax)s» δεν επιτρέπεται για '
                            'παραστατικό τύπου %(type)s.',
                            line=label, tax=tax.name, type=inv_type))
                    if not int(tax.amount) and not line.l10n_gr_prov_vat_exemption:
                        errors.append(_(
                            '• %s: ΦΠΑ 0%% χωρίς αιτία απαλλαγής (άρθρο).', label))
                    if needs_cls and (not line.l10n_gr_prov_cls_category
                                      or not line.l10n_gr_prov_cls_type):
                        errors.append(_(
                            '• %s: λείπει ο χαρακτηρισμός myDATA (κατηγορία/E3).', label))

            if company.l10n_gr_prov_guard_island:
                for line in lines:
                    tax = line.tax_ids[:1]
                    if not tax:
                        continue
                    label = line.product_id.display_name or line.name or _('γραμμή')
                    rate = int(tax.amount)
                    if rate in self.ISLAND_RATES and not is_island:
                        errors.append(_(
                            '• %(line)s: νησιωτικός συντελεστής %(rate)s%% σε πελάτη '
                            'χωρίς καθεστώς Νησιών Αιγαίου.', line=label, rate=rate))
                    elif rate in self.MAINLAND_RATES and is_island:
                        errors.append(_(
                            '• %(line)s: συντελεστής %(rate)s%% ενώ ισχύει το καθεστώς '
                            'Νησιών Αιγαίου — αναμένεται ο μειωμένος.',
                            line=label, rate=rate))

            if errors:
                raise UserError(_(
                    'Το παραστατικό %(name)s δεν καταχωρίστηκε — διορθώστε πρώτα:\n'
                    '%(details)s\n\n(Οι έλεγχοι απενεργοποιούνται από τον '
                    'διαχειριστή στις Ρυθμίσεις.)',
                    name=move.name or move.ref or '', details='\n'.join(errors)))

    # ── Posting hook: queue, never call the network inside the posting tx ────
    def _post(self, soft=True):
        self._l10n_gr_prov_check_tax_guard()
        posted = super()._post(soft)
        queue = posted.filtered(
            lambda m: m.l10n_gr_prov_applicable and not m.l10n_gr_prov_mark
            and not m.l10n_gr_prov_state
        )
        if queue:
            queue.write({'l10n_gr_prov_state': 'to_send'})
        # Seed one payment line (core selection, full payable) when none exist.
        for move in queue:
            inv_type = move.journal_id.l10n_gr_edi_inv_type_default
            if (not move.l10n_gr_prov_payment_ids
                    and inv_type not in TYPES_DISPATCH
                    and move.move_type in ('out_invoice', 'out_refund')):
                move.l10n_gr_prov_payment_ids = [(0, 0, {
                    'payment_type': move.l10n_gr_edi_payment_method or '5',
                    'amount': move._l10n_gr_prov_payable(),
                })]
        return posted

    # ── Actions ───────────────────────────────────────────────────────────────
    def action_l10n_gr_prov_send(self):
        """Manual send button."""
        for move in self:
            if not move.l10n_gr_prov_applicable:
                raise UserError(_('No e-invoicing provider is configured for this document.'))
            if move.state != 'posted':
                raise UserError(_('Only posted documents can be sent to the provider.'))
            if move.l10n_gr_prov_mark:
                raise UserError(_('This document already has a MARK from the provider.'))
            move._l10n_gr_prov_try_send(raise_on_error=True)

    def action_l10n_gr_prov_refresh_b2g_status(self):
        for move in self:
            if move.l10n_gr_prov_b2g and move.l10n_gr_prov_invoice_id:
                move._l10n_gr_prov_dispatch('poll_b2g_status')

    def action_l10n_gr_prov_recover(self):
        """Look the document up at the provider by its UID.

        Marked documents: verifies the locally computed UID against the stored
        identifier (algorithm self-check). Unmarked ones: adopts the MARK if the
        provider has it, reports the queue state, or confirms it is unknown
        (safe to resend). Outcome lands in the chatter.
        """
        for move in self:
            if not move.l10n_gr_prov_applicable:
                raise UserError(_('No e-invoicing provider is configured for this document.'))
            if move.state != 'posted':
                raise UserError(_('Only posted documents can be looked up at the provider.'))
            move._l10n_gr_prov_dispatch('recover')

    def button_draft(self):
        """A transmitted document can't go back to draft — its MARK is live at
        AADE. Reversal is a credit note (5.1), not a reset."""
        stuck = self.filtered(lambda m: m.l10n_gr_prov_mark)
        if stuck:
            raise UserError(_(
                'Έχει αποσταλεί στην ΑΑΔΕ (MARK %s) και δεν επαναφέρεται σε '
                'πρόχειρο. Για ακύρωση/επιστροφή εκδώστε Πιστωτικό Τιμολόγιο (5.1).',
                ', '.join(stuck.mapped('l10n_gr_prov_mark'))))
        queued = self.filtered(lambda m: m.l10n_gr_prov_state in ('queued', 'offline'))
        if queued:
            raise UserError(_(
                'Το παραστατικό βρίσκεται σε ουρά/εκκρεμότητα διαβίβασης και το '
                'QR του έχει ήδη εκδοθεί — δεν επαναφέρεται σε πρόχειρο.'))
        return super().button_draft()

    # ── Core dispatch to the configured driver ────────────────────────────────
    def _l10n_gr_prov_dispatch(self, operation):
        """Call the driver implementation for `operation`.

        Drivers implement methods named _l10n_gr_prov_<operation>_<provider>,
        e.g. _l10n_gr_prov_send_ilyda, _l10n_gr_prov_upload_pdf_ilyda.
        """
        self.ensure_one()
        provider = self.company_id.l10n_gr_prov_provider
        handler = getattr(self, f'_l10n_gr_prov_{operation}_{provider}', None)
        if handler is None:
            raise UserError(_(
                'The configured provider "%s" does not implement "%s". '
                'Is the driver module installed?', provider, operation))
        return handler()

    def _l10n_gr_prov_try_send(self, raise_on_error=False):
        """Send one document; on failure store the error instead of crashing.

        The driver's send returns 'sent' (marked) or 'queued' (TF-2: accepted by
        the provider, AADE offline — QR/identifier stored, MARK pending).
        """
        self.ensure_one()
        try:
            # Duplicate guard: a previous attempt may have succeeded at the
            # provider with the response lost in transit. Before re-submitting a
            # failed document, look it up by UID; if it is found (marked or
            # queued) adopt that instead of creating a duplicate at AADE. If the
            # lookup itself fails we can't verify — so we do NOT resend; the
            # exception lands in the error state and the next cron pass retries.
            # Offline (TF-1) documents get the same guard: the send that made
            # them offline may in fact have reached the provider.
            if self.l10n_gr_prov_state in ('error', 'offline') and not self.l10n_gr_prov_mark:
                if self._l10n_gr_prov_dispatch('recover'):
                    return
            result = self._l10n_gr_prov_dispatch('send') or 'sent'
            if result == 'queued':
                self.write({
                    'l10n_gr_prov_state': 'queued',
                    'l10n_gr_prov_error': False,
                    'l10n_gr_prov_send_datetime': fields.Datetime.now(),
                })
                self.message_post(body=_(
                    'Ο πάροχος παρέλαβε το παραστατικό αλλά το myDATA είναι εκτός '
                    'λειτουργίας — μπήκε σε ουρά διαβίβασης. Το εκτυπωμένο '
                    'παραστατικό φέρει το QR του παρόχου· το MARK θα ανακτηθεί '
                    'αυτόματα.'))
            else:
                self.write({
                    'l10n_gr_prov_state': 'sent',
                    'l10n_gr_prov_error': False,
                    'l10n_gr_prov_send_datetime': fields.Datetime.now(),
                })
                self.message_post(body=_(
                    'Issued through the e-invoicing provider. MARK: %s', self.l10n_gr_prov_mark))
        except Exception as e:
            # TF-1: the provider is unreachable — issue the document with a
            # locally signed offline QR instead of just failing, when a verified
            # key exists. The fallback must never mask the original failure.
            if isinstance(e, ProviderUnreachableError):
                try:
                    if self._l10n_gr_prov_try_offline():
                        return
                except Exception:
                    _logger.exception('Offline QR fallback failed for %s', self.name)
            msg = str(e)
            # A document that already carries an offline QR stays 'offline'
            # through failed retries — the printed QR label and the retry cron
            # depend on the state; the error text is still recorded.
            state = 'offline' if self.l10n_gr_prov_offline_token else 'error'
            self.write({'l10n_gr_prov_state': state, 'l10n_gr_prov_error': msg})
            self.message_post(body=_('Provider submission failed: %s', msg))
            self._l10n_gr_prov_offline_deadline_warn()
            if raise_on_error:
                raise

    def _l10n_gr_prov_try_offline(self):
        """TF-1 fallback. Returns True when the document is (already) covered
        by an offline QR — the caller then stops treating the send as a
        failure. False = no key configured, fail normally."""
        self.ensure_one()
        if self.l10n_gr_prov_offline_token:
            # Already issued offline; the retry just found the provider still
            # down. Stay offline, surface the deadline if it lapsed.
            self._l10n_gr_prov_offline_deadline_warn()
            return True
        key = self.env['l10n.gr.prov.offline.key']._get_active_key(self.company_id)
        if not key:
            return False
        return bool(self._l10n_gr_prov_dispatch('issue_offline'))

    def _l10n_gr_prov_offline_deadline_warn(self):
        """Α.1112/2025: offline documents must be transmitted within 1 calendar
        day. Post the breach once (keyed on the stored error text)."""
        self.ensure_one()
        if not self.l10n_gr_prov_offline_token or self.l10n_gr_prov_mark:
            return
        if not self.invoice_date or \
                fields.Date.context_today(self) <= self.invoice_date + timedelta(days=1):
            return
        warn = _('Η προθεσμία διαβίβασης του offline παραστατικού (Α.1112/2025: '
                 'έως το τέλος της επόμενης ημέρας) έχει παρέλθει — το QR δεν '
                 'επαληθεύεται πλέον. Απαιτείται άμεση διαβίβαση.')
        if self.l10n_gr_prov_error != warn:
            self.l10n_gr_prov_error = warn
            self.message_post(body=warn)

    # ── PDF upload (after marking, once the legal PDF exists) ────────────────
    def _l10n_gr_prov_get_pdf(self):
        """Return (filename, bytes) of the invoice PDF, rendering it if needed."""
        self.ensure_one()
        attachment = self.invoice_pdf_report_id
        if attachment:
            return attachment.name, base64.b64decode(attachment.datas)
        report = self.env.ref('account.account_invoices')
        content, _type = self.env['ir.actions.report']._render_qweb_pdf(
            report, res_ids=self.ids)
        return f'{(self.name or "invoice").replace("/", "_")}.pdf', content

    def _l10n_gr_prov_try_upload_pdf(self):
        self.ensure_one()
        try:
            self._l10n_gr_prov_dispatch('upload_pdf')
            self.l10n_gr_prov_pdf_uploaded = True
        except Exception as e:
            _logger.warning('Provider PDF upload failed for %s: %s', self.name, e)

    # ── Cron: retry queue ─────────────────────────────────────────────────────
    @api.model
    def _l10n_gr_prov_cron_process(self):
        """Send queued documents, upload pending PDFs, poll B2G statuses.

        Each record is processed in its own savepoint so a single failure
        does not roll back the entire batch.
        """
        # 1. Pending sends (auto-send companies) and previous errors (all companies)
        domain = [
            ('state', '=', 'posted'),
            # 'offline' (TF-1) documents retry regardless of auto_send — the
            # 1-day legal transmission deadline doesn't wait for a human.
            ('l10n_gr_prov_state', 'in', ('to_send', 'error', 'offline')),
            ('l10n_gr_prov_mark', '=', False),
        ]
        for move in self.search(domain, limit=50):
            if not move.l10n_gr_prov_applicable:
                continue
            if move.l10n_gr_prov_state == 'to_send' and not move.company_id.l10n_gr_prov_auto_send:
                continue  # manual mode: only retry documents that were attempted (error state)
            with self.env.cr.savepoint():
                move._l10n_gr_prov_try_send()

        # 1b. TF-2: poll documents queued at the provider until the MARK arrives
        for move in self.search([('l10n_gr_prov_state', '=', 'queued')], limit=50):
            with self.env.cr.savepoint():
                try:
                    move._l10n_gr_prov_dispatch('recover')
                except Exception as e:
                    _logger.warning('Provider queue poll failed for %s: %s', move.name, e)

        # 2. Upload PDFs for marked documents
        for move in self.search([
            ('l10n_gr_prov_state', '=', 'sent'),
            ('l10n_gr_prov_pdf_uploaded', '=', False),
            ('l10n_gr_prov_invoice_id', '!=', False),
        ], limit=50):
            with self.env.cr.savepoint():
                move._l10n_gr_prov_try_upload_pdf()

        # 3. Poll B2G statuses
        for move in self.search([
            ('l10n_gr_prov_b2g', '=', True),
            ('l10n_gr_prov_state', '=', 'sent'),
            ('l10n_gr_prov_invoice_id', '!=', False),
        ], limit=50):
            try:
                move._l10n_gr_prov_dispatch('poll_b2g_status')
            except Exception as e:
                _logger.warning('B2G status poll failed for %s: %s', move.name, e)

    # ── Report helpers (custom Greek PDF) ─────────────────────────────────────
    def _get_name_invoice_report(self):
        self.ensure_one()
        if self.l10n_gr_prov_applicable and self.journal_id.l10n_gr_edi_inv_type_default:
            return 'l10n_gr_provider_base.report_invoice_document_gr'
        return super()._get_name_invoice_report()

    def _l10n_gr_prov_report_title(self):
        """Greek document title, e.g. 'ΤΙΜΟΛΟΓΙΟ ΠΩΛΗΣΗΣ' (caps drop the τόνοι)."""
        self.ensure_one()
        name = (self.journal_id.name or 'ΠΑΡΑΣΤΑΤΙΚΟ').upper()
        return ''.join(c for c in unicodedata.normalize('NFD', name)
                       if not unicodedata.combining(c))

    def _l10n_gr_prov_vat_analysis(self):
        """Per-rate VAT buckets: [{'rate', 'net', 'vat', 'gross', 'exemption'}]."""
        self.ensure_one()
        buckets = {}
        for line in self.invoice_line_ids.filtered(
                lambda l: l.display_type == 'product'):
            tax = line.tax_ids[:1]
            rate = tax.amount if tax else 0.0
            exemption = line.l10n_gr_prov_vat_exemption if not rate else False
            bucket = buckets.setdefault((rate, exemption), [0.0, 0.0])
            bucket[0] += line.price_subtotal
            bucket[1] += line.price_total - line.price_subtotal
        labels = dict(VAT_EXEMPTION_CODES)
        return [{
            'rate': rate,
            'net': round(net, 2),
            'vat': round(vat, 2),
            'gross': round(net + vat, 2),
            'exemption': labels.get(exemption, '') if exemption else '',
        } for (rate, exemption), (net, vat)
          in sorted(buckets.items(), key=lambda kv: -kv[0][0])]

    def _l10n_gr_prov_qr_image(self):
        self.ensure_one()
        if not self.l10n_gr_prov_qr_url:
            return False
        barcode = self.env['ir.actions.report'].barcode(
            'QR', self.l10n_gr_prov_qr_url, width=120, height=120)
        return base64.b64encode(barcode).decode()
