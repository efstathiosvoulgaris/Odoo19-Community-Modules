# -*- coding: utf-8 -*-
from odoo import api, models

class ResPartner(models.Model):
    _inherit = 'res.partner'

    @api.model
    def _get_view(self, view_id=None, view_type='form', **options):
        arch, view = super()._get_view(view_id, view_type, **options)
        country = self.env.company.country_id
        if country == self.env.ref('base.gr', raise_if_not_found=False):
            for node in arch.iterfind(".//field[@name='vat']"):
                node.set('string', 'ΑΦΜ')
            for node in arch.iterfind(".//label[@for='vat']"):
                node.set('string', 'ΑΦΜ')
        return arch, view
