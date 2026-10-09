# -*- coding: utf-8 -*-
from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    courier_cod = fields.Boolean(
        string='Αντικαταβολή', copy=False,
        help='Η παραγγελία πληρώνεται στον courier. Το voucher παίρνει '
             'αυτόματα το σύνολό της ως ποσό αντικαταβολής.')
