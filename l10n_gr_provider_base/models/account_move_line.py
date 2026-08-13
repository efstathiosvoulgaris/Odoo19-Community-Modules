# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from .gr_mydata import (
    CLS_CATEGORIES, CLS_TYPES, VAT_EXEMPTION_CODES,
    valid_cls_categories, valid_cls_types, preferred_e3, INV_TYPE_ZERO_TAX,
    gr_tax,
)
from .uom_uom import REC20_BY_AADE_UNIT


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
    # §8.15 Επισήμανση — mandatory on 1.5 (Εκκαθάριση Πωλήσεων Τρίτων), which
    # must carry both kinds of line: the third-party sales being cleared and
    # the agent's commission on them (MDP-0083/0084).
    l10n_gr_prov_detail_type = fields.Selection(
        selection=[
            ('1', '1 - Εκκαθάριση Πωλήσεων Τρίτων'),
            ('2', '2 - Αμοιβή από Πωλήσεις Τρίτων'),
        ],
        string='Επισήμανση Γραμμής',
        copy=True,
        help='Υποχρεωτικό για Εκκαθάριση Πωλήσεων Τρίτων (1.5): κάθε γραμμή '
             'δηλώνεται είτε ως αξία πωλήσεων τρίτων (1) είτε ως αμοιβή του '
             'εκκαθαριστή (2). Το παραστατικό απαιτεί τουλάχιστον μία από κάθε είδος.',
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

    # 8.2 Ειδικό Στοιχείο: the line is only the fee description — the amount
    # lives in Λοιποί Φόροι. Hook the computes (not an onchange): they re-run
    # after any product/account change, so price and VAT can never sneak back.
    def _compute_price_unit(self):
        super()._compute_price_unit()
        for line in self:
            if line.move_id.journal_id.l10n_gr_edi_inv_type_default == '8.2':
                line.price_unit = 0.0

    def _compute_tax_ids(self):
        super()._compute_tax_ids()
        for line in self:
            if line.move_id.journal_id.l10n_gr_edi_inv_type_default == '8.2':
                line.tax_ids = [(5, 0, 0)]

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
            # 8.2 Ειδικό Στοιχείο: the only valid income combo is category1_95
            # (informational, takes NO E3 code) — the derived goods/service
            # default would be wrong here.
            if inv_type == '8.2':
                line.l10n_gr_prov_cls_category = 'category1_95'
                line.l10n_gr_prov_cls_type = False
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

    def _l10n_gr_prov_measurement_unit(self):
        """(AADE §8.13 code, title) for this line's unit of measure.

        An unmapped unit is transmitted as 7 (Λοιπές Περιπτώσεις) carrying its
        real name, which AADE requires alongside the code."""
        self.ensure_one()
        uom = self.product_uom_id
        code = uom.l10n_gr_prov_measurement_unit
        if code:
            return int(code), None
        return 7, (uom.name or '')[:50]

    def _l10n_gr_prov_quantity_units(self):
        """UN/ECE Rec 20 code for this line's unit — EN16931 BT-130.

        Kept in step with the AADE code: a line billed in κιλά used to be
        transmitted as measurementUnit 2 to AADE and «EA» to the buyer."""
        self.ensure_one()
        code, _title = self._l10n_gr_prov_measurement_unit()
        return REC20_BY_AADE_UNIT.get(str(code), 'EA')

    def _l10n_gr_prov_net_unit_price(self):
        """price_unit with any tax-included percentage taxes stripped out."""
        self.ensure_one()
        included = self.tax_ids.filtered(
            lambda t: t.price_include and t.amount_type == 'percent')
        factor = 1.0 + sum(included.mapped('amount')) / 100.0
        return self.price_unit / factor if factor else self.price_unit

    def _l10n_gr_prov_report_amounts(self):
        """Net figures for one printed line — {unit, before, discount, after}.

        price_subtotal is the only amount Odoo guarantees to be
        tax-EXCLUSIVE; price_unit carries the VAT whenever the price list
        includes tax. The form used to derive ΑΞΙΑ as price_unit × quantity
        and ΕΚΠΤΩΣΗ as the gap to price_subtotal, which on a tax-included
        document printed the gross value under ΑΞΙΑ and relabelled the VAT
        as a discount that did not exist. Everything here therefore comes
        off price_subtotal and the line's own discount percentage.
        """
        self.ensure_one()
        after = self.price_subtotal
        disc = self.discount or 0.0
        if disc and disc < 100:
            before = after / (1 - disc / 100.0)
        elif disc:
            # 100% discount: the subtotal is 0 and carries no information,
            # so recover the undiscounted net from the unit price.
            before = self._l10n_gr_prov_net_unit_price() * self.quantity
        else:
            before = after
        return {
            'unit': (before / self.quantity) if self.quantity else 0.0,
            'before': before,
            'discount': before - after,
            'after': after,
        }

    def _l10n_gr_prov_lot_names(self):
        """SN/LN delivered against these invoice lines, via their sale order
        lines: {line_id: [names]}, batched — one traversal of
        sale_line_ids → stock.move → stock.move.line for the whole recordset
        instead of a query cascade per printed line.

        Empty when sale/stock are not installed (no sale_line_ids field)."""
        if 'sale_line_ids' not in self._fields or not self:
            return {}
        # Prefetch the whole chain once; the per-line reads below then hit
        # the ORM cache.
        all_smls = self.sale_line_ids.move_ids.move_line_ids
        if not all_smls:
            return {}
        done = all_smls.filtered(
            lambda sml: sml.state == 'done' and sml.lot_id
            and sml._should_show_lot_in_invoice())
        if not done:
            return {}
        keep = set(done.ids)
        result = {}
        for line in self:
            names = {sml.lot_id.name
                     for sml in line.sale_line_ids.move_ids.move_line_ids
                     if sml.id in keep}
            if names:
                result[line.id] = sorted(names)
        return result

    @api.model_create_multi
    def create(self, vals_list):
        """Lines created outside the form onchange path (sale order invoicing,
        imports, API) never receive the myDATA defaults — derive them here.
        Lines that already carry a classification (form UI, POS) are left
        untouched."""
        lines = super().create(vals_list)
        todo = lines.filtered(
            lambda l: l.display_type == 'product' and l.product_id
            and not l.l10n_gr_prov_cls_category
            and l.company_id.country_code == 'GR'
            and l._l10n_gr_prov_inv_type())
        if todo:
            todo._onchange_l10n_gr_prov_cls_from_product()
            todo._onchange_l10n_gr_prov_zero_tax()
        return lines
