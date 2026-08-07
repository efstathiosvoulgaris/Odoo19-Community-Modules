# -*- coding: utf-8 -*-
from odoo import api, fields, models


class PosConfig(models.Model):
    _inherit = 'pos.config'

    # The streamlined coffee-shop UI hides the customer selector and the course
    # buttons. That is right for a counter where every sale is anonymous and
    # wrong anywhere a customer has to be named — a ΤΙΜ needs a partner with
    # ΑΦΜ, loyalty needs the customer, and a retail till usually wants both.
    # Default follows restaurant mode, exactly like pos_iface_printbill, and
    # stays overridable per till.
    pos_ca_simple_ui = fields.Boolean(
        string='Απλοποιημένο Ταμείο',
        compute='_compute_pos_ca_simple_ui', store=True, readonly=False,
        help='Κρύβει την επιλογή πελάτη και τα κουμπιά σειράς (course) από την '
             'οθόνη προϊόντων. Ξεμαρκάρετέ το σε ταμείο που χρειάζεται πελάτη '
             '— π.χ. για έκδοση Τιμολογίου (ΤΙΜ).')

    @api.depends('module_pos_restaurant')
    def _compute_pos_ca_simple_ui(self):
        for config in self:
            config.pos_ca_simple_ui = config.module_pos_restaurant


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    pos_pos_ca_simple_ui = fields.Boolean(
        related='pos_config_id.pos_ca_simple_ui', readonly=False)
