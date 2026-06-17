# -*- coding: utf-8 -*-
from odoo import fields, models


class RestaurantTable(models.Model):
    _inherit = 'restaurant.table'

    table_name = fields.Char('Table Name', help="Custom text label for the table. Shown instead of the table number when set.")

    def _load_pos_data_fields(self, config):
        fields = super()._load_pos_data_fields(config)
        if 'table_name' not in fields:
            fields.append('table_name')
        return fields
