# -*- coding: utf-8 -*-
from odoo import fields, models
from .gr_mydata import CLS_CATEGORIES, CLS_TYPES, PRODUCT_TYPES_GR


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    l10n_gr_prov_cpv = fields.Char(
        string='CPV Code',
        help='Common Procurement Vocabulary code (EC Reg. 213/2008), e.g. '
             '30237200-1. Required on lines of B2G invoices (BT-158, scheme STI). '
             'If no exact CPV exists, use the closest parent code.',
    )

    l10n_gr_prov_product_type_gr = fields.Selection(
        selection=PRODUCT_TYPES_GR,
        string='Τύπος Προϊόντος (myDATA)',
        help='Greek product type used to suggest the myDATA classification category '
             'and E3 code on invoice lines. Leave blank to always set manually.',
    )
    l10n_gr_prov_cls_category = fields.Selection(
        selection=CLS_CATEGORIES,
        string='Κατηγορία Χαρακτηρισμού (default)',
        help='Default myDATA classification category for lines using this product. '
             'Overrides the automatic suggestion from the product type.',
    )
    l10n_gr_prov_cls_type = fields.Selection(
        selection=CLS_TYPES,
        string='Κωδικός Χαρακτηρισμού E3 (default)',
        help='Default myDATA E3 classification code for lines using this product. '
             'Overrides the automatic suggestion from the product type.',
    )
