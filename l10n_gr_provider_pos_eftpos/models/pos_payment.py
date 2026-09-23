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
    # The attempt's key: finds the l10n.gr.prov.eft.payment behind this line,
    # which holds the driver's answer and everything a Void needs. A plain key,
    # not a Many2one — the POS data layer would try to load the related model.
    l10n_gr_prov_eft_client_key = fields.Char(copy=False, index=True)

    # Before pos_eftpos 1.6 the till kept what a Void needs on the line itself;
    # the charge record holds it now. Kept so older payments stay readable.
    l10n_gr_prov_eft_signed_content = fields.Char(copy=False)
    l10n_gr_prov_eft_signature_uid = fields.Char(copy=False)
    l10n_gr_prov_eft_signature_ts = fields.Integer(copy=False)
    l10n_gr_prov_eft_ecr_reference = fields.Char(copy=False)
    l10n_gr_prov_eft_bank_auth_code = fields.Char(copy=False)
    l10n_gr_prov_eft_receipt_number = fields.Char(copy=False)
