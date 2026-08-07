# -*- coding: utf-8 -*-
from odoo import api, fields, models
from .gr_mydata import (
    INVOICE_TYPES, PRODUCT_TYPES_GR, CLS_CATEGORIES, CLS_TYPES,
    default_classification,
)


class L10nGrProvClsDefault(models.Model):
    """Sparse override table for line classification defaults.

    Only rows that should differ from the derived default live here; everything
    else falls back to gr_mydata.default_classification(). Keyed on
    (inv_type, product_type).
    """
    _name = 'l10n.gr.prov.cls.default'
    _description = 'myDATA Classification Default (override)'
    _rec_name = 'inv_type'

    inv_type = fields.Selection(INVOICE_TYPES, string='Τύπος Παραστατικού', required=True)
    product_type = fields.Selection(PRODUCT_TYPES_GR, string='Είδος', required=True)
    cls_category = fields.Selection(CLS_CATEGORIES, string='Κατηγορία', required=True)
    cls_type = fields.Selection(CLS_TYPES, string='Κωδικός E3')
    company_id = fields.Many2one('res.company', string='Εταιρεία',
                                 default=lambda s: s.env.company)

    _uniq_type_product_company = models.Constraint(
        'unique(inv_type, product_type, company_id)',
        'Υπάρχει ήδη προεπιλογή για αυτόν τον τύπο και είδος.',
    )

    @api.model
    def get_default(self, inv_type, product_type, company_id=None):
        """Return (category, e3): override row if present, else derived default."""
        if not inv_type or not product_type:
            return (None, None)
        company_id = company_id or self.env.company.id
        row = self.search([
            ('inv_type', '=', inv_type),
            ('product_type', '=', product_type),
            ('company_id', 'in', (company_id, False)),
        ], order='company_id desc', limit=1)
        if row:
            return (row.cls_category, row.cls_type)
        return default_classification(inv_type, product_type)
