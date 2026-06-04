# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    aade_username = fields.Char(
        string="AADE Username",
        help="Όνομα χρήστη TaxisNet εξουσιοδοτημένο για την υπηρεσία RgWsPublic2.",
    )
    aade_password = fields.Char(
        string="AADE Password",
        help="Κωδικός TaxisNet για την υπηρεσία RgWsPublic2.",
    )
