# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    courier_default_account_id = fields.Many2one(
        'courier.account', string='Προεπιλεγμένος Λογαριασμός Courier',
        help='Ο λογαριασμός που προτείνεται σε κάθε νέο voucher.')


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    courier_default_account_id = fields.Many2one(
        related='company_id.courier_default_account_id', readonly=False)
