# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.addons.l10n_gr_edi.models.preferred_classification import CLASSIFICATION_MAP

# Invoice types added in myDATA API v1.0.9/1.0.10, missing from core l10n_gr_edi.
# Classification data from syndiasmoi_xaraktirismwn_v1.0.10.xlsx:
#   8.4 — Απόδειξη Είσπραξης POS     → category1_95 only, no E3 update, no VAT
#   8.5 — Απόδειξη Επιστροφής POS    → category1_95 only, no E3 update, no VAT
#   8.6 — Δελτίο Παραγγελίας Εστίασης → category1_95 only, no E3 update, no VAT
#   9.3 — Δελτίο Αποστολής           → no classifications (dispatch note, not financial)

# Dispatch/delivery types (v2.0.1) — no financial data
EXTRA_TYPES_DISPATCH = ('9.1', '9.2', '9.3', '10.1', '10.2')

# These types carry no VAT (VAT category 8) — same behaviour as 8.1, 8.2 in core.
EXTRA_TYPES_WITH_VAT_CATEGORY_8 = ('8.4', '8.5', '8.6') + EXTRA_TYPES_DISPATCH

# Income-bearing types (have classification on lines)
EXTRA_TYPES_WITH_INCOME = ('8.4', '8.5', '8.6')

# Patch core CLASSIFICATION_MAP so line-level compute methods don't KeyError.
# 8.4/8.5/8.6: income receipt types, only category1_95 allowed (no E3 codes).
# 9.x/10.x: dispatch notes, no classifications at all → empty dict.
CLASSIFICATION_MAP.setdefault('8.4', {'category1_95': 'blank'})
CLASSIFICATION_MAP.setdefault('8.5', {'category1_95': 'blank'})
CLASSIFICATION_MAP.setdefault('8.6', {'category1_95': 'blank'})
for _dispatch_type in EXTRA_TYPES_DISPATCH:
    CLASSIFICATION_MAP.setdefault(_dispatch_type, {})


class AccountMove(models.Model):
    _inherit = 'account.move'

    l10n_gr_edi_inv_type = fields.Selection(
        selection_add=[
            ('8.4', '8.4 - Απόδειξη Είσπραξης POS'),
            ('8.5', '8.5 - Απόδειξη Επιστροφής POS'),
            ('8.6', '8.6 - Δελτίο Παραγγελίας Εστίασης'),
            ('9.1', '9.1 - Δελτίο Αποστολής Συσχετιζόμενο'),
            ('9.2', '9.2 - Συγκεντρωτικό Δελτίο Αποστολής'),
            ('9.3', '9.3 - Δελτίο Αποστολής'),
            ('10.1', '10.1 - Δελτίο Ποσοτικής Παραλαβής Συσχετιζόμενο'),
            ('10.2', '10.2 - Δελτίο Ποσοτικής Παραλαβής Μη Συσχετιζόμενο'),
        ],
    )

    def _compute_l10n_gr_edi_available_inv_type(self):
        super()._compute_l10n_gr_edi_available_inv_type()
        for move in self:
            if move.is_sale_document(include_receipts=True) and move.l10n_gr_edi_available_inv_type:
                extras = ','.join(EXTRA_TYPES_WITH_INCOME + EXTRA_TYPES_DISPATCH)
                move.l10n_gr_edi_available_inv_type += ',' + extras

    def _get_starting_sequence(self):
        # ponytail: skip year for GR myDATA journals → ΤΙΜ/00001 not ΤΙΜ/2026/00001
        if self.journal_id.l10n_gr_edi_inv_type_default and self.country_code == 'GR':
            code = self.journal_id.code or 'INV'
            if self.journal_id.refund_sequence and self.move_type in ('out_refund', 'in_refund'):
                code = 'R' + code
            return f'{code}/00001'
        return super()._get_starting_sequence()

    def _compute_l10n_gr_edi_need_fields(self):
        # Correlated dispatch advices (9.1/10.1) need the correlated invoice too
        super()._compute_l10n_gr_edi_need_fields()
        for move in self:
            if move.l10n_gr_edi_inv_type in ('9.1', '10.1'):
                move.l10n_gr_edi_need_correlated = True

    @api.depends('journal_id', 'journal_id.l10n_gr_edi_inv_type_default',
                 'fiscal_position_id', 'l10n_gr_edi_available_inv_type')
    def _compute_l10n_gr_edi_inv_type(self):
        # Run core first (sets its default), then override with journal default when present.
        # Core preserves existing value, so we must run after it and force-write.
        super()._compute_l10n_gr_edi_inv_type()
        for move in self:
            if (move.journal_id.l10n_gr_edi_inv_type_default
                    and move.country_code == 'GR'
                    and move.move_type not in ('entry', 'out_refund', 'in_refund')):
                move.l10n_gr_edi_inv_type = move.journal_id.l10n_gr_edi_inv_type_default
