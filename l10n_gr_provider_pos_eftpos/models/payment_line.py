# -*- coding: utf-8 -*-
from odoo import fields, models


class L10nGrProvPayment(models.Model):
    _inherit = 'l10n.gr.prov.payment'

    # Α.1155 signature fields carried straight on the myDATA payment line for
    # POS card payments (which have no l10n.gr.prov.eft.payment record — that
    # model is invoice-bound; here the signature is taken before the invoice
    # exists). The transaction id reuses the existing transaction_id field.
    l10n_gr_prov_eft_signature = fields.Text(copy=False)
    l10n_gr_prov_eft_signing_author = fields.Char(copy=False)
    l10n_gr_prov_eft_terminal_code = fields.Char(copy=False)
