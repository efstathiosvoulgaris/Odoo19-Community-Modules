from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    ql_idle_minutes = fields.Integer(
        'Αποσύνδεση μετά από (λεπτά αδράνειας)', default=15,
        config_parameter='shop_quick_login.idle_minutes',
        help='0 = χωρίς αποσύνδεση αδράνειας. Όσο είναι ανοιχτό ταμείο στον browser, δεν γίνεται αποσύνδεση.')
