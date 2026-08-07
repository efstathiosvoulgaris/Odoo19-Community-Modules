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

    # What the MegEftPos Driver needs to reverse this charge, kept because a
    # Void must quote the very values the Sale answered with. They are also
    # the reconciliation trail against the bank.
    l10n_gr_prov_eft_signed_content = fields.Char(copy=False)
    l10n_gr_prov_eft_signature_uid = fields.Char(copy=False)
    l10n_gr_prov_eft_signature_ts = fields.Integer(copy=False)
    l10n_gr_prov_eft_ecr_reference = fields.Char(copy=False)
    l10n_gr_prov_eft_bank_auth_code = fields.Char(copy=False)
    l10n_gr_prov_eft_receipt_number = fields.Char(copy=False)
