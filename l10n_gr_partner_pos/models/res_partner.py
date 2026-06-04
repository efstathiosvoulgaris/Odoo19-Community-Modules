# -*- coding: utf-8 -*-
from odoo import api, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    @api.model
    def _load_pos_data_fields(self, config):
        fields = super()._load_pos_data_fields(config)
        for f in ("eponymia", "kinito", "doy", "drastiriotita"):
            if f not in fields:
                fields.append(f)
        return fields
