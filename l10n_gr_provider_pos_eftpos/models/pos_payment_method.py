# -*- coding: utf-8 -*-
from odoo import api, models


class PosPaymentMethod(models.Model):
    _inherit = 'pos.payment.method'

    @api.model
    def _load_pos_data_fields(self, config):
        # Expose the myDATA payment type in the POS session so the payment
        # screen can tell which methods are card (type 7 → Α.1155 flow).
        fields = super()._load_pos_data_fields(config)
        if 'l10n_gr_prov_payment_type' not in fields:
            fields.append('l10n_gr_prov_payment_type')
        return fields
