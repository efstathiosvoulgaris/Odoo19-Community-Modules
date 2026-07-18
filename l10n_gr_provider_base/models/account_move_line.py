# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from .gr_mydata import (
    CLS_CATEGORIES, CLS_TYPES, VAT_EXEMPTION_CODES,
    valid_cls_categories, valid_cls_types, preferred_e3, INV_TYPE_ZERO_TAX,
    gr_tax,
)


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    l10n_gr_prov_cls_category = fields.Selection(
        selection=CLS_CATEGORIES,
        string='Κατηγορία Χαρακτηρισμού',
        copy=True,
        help='myDATA income/expense classification category for this line.',
    )
    l10n_gr_prov_cls_type = fields.Selection(
        selection=CLS_TYPES,
        string='Κωδικός Χαρακτηρισμού (E3)',
        copy=True,
        help='myDATA E3 classification type for this line.',
    )
    l10n_gr_prov_vat_exemption = fields.Selection(
        selection=VAT_EXEMPTION_CODES,
        string='Αιτία Απαλλαγής ΦΠΑ',
        copy=True,
        help='VAT exemption reason code (vatExemptionCategory). '
             'Required when this line carries 0% VAT.',
    )

    def _l10n_gr_prov_inv_type(self):
        """Effective myDATA type governing this line's classification (from journal)."""
        self.ensure_one()
        move = self.move_id
        return (move.l10n_gr_edi_inv_type
                or move.journal_id.l10n_gr_edi_inv_type_default)

    @api.onchange('l10n_gr_prov_cls_category')
    def _onchange_l10n_gr_prov_cls_category(self):
        """Auto-set the E3 code when the type+category allows exactly one; else
        clear an E3 that is no longer valid for the chosen category."""
        for line in self:
            inv_type = line._l10n_gr_prov_inv_type()
            cat = line.l10n_gr_prov_cls_category
            if not inv_type or not cat:
                continue
            valid = valid_cls_types(inv_type, cat)
            e3 = line.l10n_gr_prov_cls_type
            # Fill the preferred E3 whenever the category needs one and the
            # current value is empty or invalid (category*_95/category3 take
            # none, so valid is empty and E3 is cleared).
            if not valid:
                line.l10n_gr_prov_cls_type = False
            elif not e3 or e3 not in valid:
                line.l10n_gr_prov_cls_type = preferred_e3(inv_type, valid)

    @api.constrains('l10n_gr_prov_cls_category', 'l10n_gr_prov_cls_type')
    def _check_l10n_gr_prov_classification(self):
        """Reject category/E3 combos that AADE does not allow for the inv type."""
        for line in self:
            if line.display_type or line.company_id.country_code != 'GR':
                continue
            inv_type = line._l10n_gr_prov_inv_type()
            cat = line.l10n_gr_prov_cls_category
            e3 = line.l10n_gr_prov_cls_type
            if not inv_type or not cat:
                continue
            if cat not in valid_cls_categories(inv_type):
                raise ValidationError(_(
                    'Κατηγορία %(cat)s δεν επιτρέπεται για τον τύπο παραστατικού %(t)s.',
                    cat=cat, t=inv_type))
            valid = valid_cls_types(inv_type, cat)
            # empty valid set = category takes no E3 (e.g. category*_95 / category3)
            if valid and e3 and e3 not in valid:
                raise ValidationError(_(
                    'Κωδικός E3 %(e3)s δεν επιτρέπεται για %(t)s / %(cat)s.',
                    e3=e3, t=inv_type, cat=cat))

    @api.onchange('product_id')
    def _onchange_l10n_gr_prov_zero_tax(self):
        """Cross-border journals (1.2/2.2/1.3/2.3): force the mapped 0% tax and
        the Απαλλαγή ΦΠΑ reason on product lines (mapping confirmed with user)."""
        for line in self:
            move = line.move_id
            if move.company_id.country_code != 'GR' or not line.product_id:
                continue
            zero = INV_TYPE_ZERO_TAX.get(line._l10n_gr_prov_inv_type())
            if not zero:
                continue
            template_id, exemption = zero
            # Resolve by chart xmlid, not name — taxes are user-renameable.
            tax = gr_tax(self.env, move.company_id, template_id)
            if tax:
                line.tax_ids = [(6, 0, tax.ids)]
            line.l10n_gr_prov_vat_exemption = exemption

    @api.onchange('product_id')
    def _onchange_l10n_gr_prov_dispatch_zero_price(self):
        """Pure dispatch notes (9.x/10.x) carry no values — default lines to 0.
        (Converting to ΤΙΜ re-prices from the product.)"""
        for line in self:
            if line.product_id and line.move_id.l10n_gr_prov_is_dispatch_only:
                line.price_unit = 0.0

    @api.onchange('product_id')
    def _onchange_l10n_gr_prov_cls_from_product(self):
        """Fill line classification from the defaults table (override → derived).

        Product-template overrides win first; otherwise the (inv_type, product
        type) default is used. Fields stay editable for inline special cases.
        """
        for line in self:
            move = line.move_id
            if move.company_id.country_code != 'GR':
                continue
            inv_type = line._l10n_gr_prov_inv_type()
            if not inv_type:
                continue
            tmpl = line.product_id.product_tmpl_id
            # Fall back to 'goods' when the product has no Greek type set —
            # goods is the overwhelmingly common case, so a line is never blank.
            ptype = tmpl.l10n_gr_prov_product_type_gr or 'goods'
            cat, e3 = self.env['l10n.gr.prov.cls.default'].get_default(
                inv_type, ptype, move.company_id.id)
            # Product-template overrides win, but only when valid for this
            # invoice type (a fixed domestic E3 is wrong on 1.2/1.3); missing
            # or invalid pieces fall back to the map derivation.
            tmpl_cat = tmpl.l10n_gr_prov_cls_category
            if tmpl_cat and tmpl_cat in valid_cls_categories(inv_type):
                cat = tmpl_cat
                valid = valid_cls_types(inv_type, cat)
                tmpl_e3 = tmpl.l10n_gr_prov_cls_type
                if tmpl_e3 and tmpl_e3 in valid:
                    e3 = tmpl_e3
                else:
                    e3 = preferred_e3(inv_type, valid) or False
            if cat:
                line.l10n_gr_prov_cls_category = cat
                line.l10n_gr_prov_cls_type = e3
