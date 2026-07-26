# -*- coding: utf-8 -*-
from odoo import fields, models


class PosPayment(models.Model):
    _inherit = 'pos.payment'

    # Α.1155 signature captured at the payment screen, carried to the invoice's
    # type-7 myDATA payment line. (POS loads all fields via read([]), so no
    # explicit _load_pos_data_fields override is needed.)
    l10n_gr_prov_eft_signature = fields.Text(copy=False)
    l10n_gr_prov_eft_signing_author = fields.Char(copy=False)
    l10n_gr_prov_eft_transaction_id = fields.Char(copy=False)
    l10n_gr_prov_eft_terminal_code = fields.Char(copy=False)
