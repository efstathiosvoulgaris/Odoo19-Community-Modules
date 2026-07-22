# -*- coding: utf-8 -*-
from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # ΔΟΥ and δραστηριότητα are NOT redefined here — they live in
    # l10n_gr_partner as `doy` / `drastiriotita` (filled by the AADE VAT
    # lookup). We consumed those directly; a duplicate pair here only went
    # stale against the AADE data.
    l10n_gr_prov_aaht = fields.Char(
        string='ΑΑΗΤ',
        help='Unique e-invoicing code of the contracting authority (Αναθέτουσα '
             'Αρχή Ηλεκτρονικής Τιμολόγησης) from the ΜΑΑΗΤ registry '
             '(webapps.gsis.gr/dsae2/foreisreg). Used in the B2G buyer '
             'reference (BT-10).',
    )
