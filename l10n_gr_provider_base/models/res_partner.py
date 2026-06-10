# -*- coding: utf-8 -*-
from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    l10n_gr_prov_aaht = fields.Char(
        string='ΑΑΗΤ',
        help='Unique e-invoicing code of the contracting authority (Αναθέτουσα '
             'Αρχή Ηλεκτρονικής Τιμολόγησης) from the ΜΑΑΗΤ registry '
             '(webapps.gsis.gr/dsae2/foreisreg). Used in the B2G buyer '
             'reference (BT-10).',
    )
