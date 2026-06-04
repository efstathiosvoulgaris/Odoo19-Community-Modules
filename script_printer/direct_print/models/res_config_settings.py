from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    direct_print_agent_url = fields.Char(
        string='Print Agent URL',
        config_parameter='direct_print.agent_url',
        default='http://127.0.0.1:5000',
        help='URL of the local print agent running on this Windows machine',
    )
