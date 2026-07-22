# -*- coding: utf-8 -*-
from odoo import fields, models

from odoo.addons.l10n_gr_provider_base.models.payment import PAYMENT_TYPE_SELECTION


class PosPaymentMethod(models.Model):
    _inherit = 'pos.payment.method'

    l10n_gr_prov_payment_type = fields.Selection(
        PAYMENT_TYPE_SELECTION, string='Τύπος Πληρωμής myDATA',
        default='3',
        help='Ο κωδικός τρόπου πληρωμής ΑΑΔΕ (§8.12) που διαβιβάζεται με το '
             'παραστατικό — 3 Μετρητά, 7 POS/κάρτα κ.λπ.')
