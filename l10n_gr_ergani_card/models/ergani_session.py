from odoo import fields, models

from .res_company import ERGANI_MODES


class ErganiSession(models.Model):
    """ΕΡΓΑΝΗ tokens, one row per company and environment. Only the system
    reads or writes them; switching environment drops them (DESIGN §5.7)."""
    _name = 'ergani.session'
    _description = 'ΕΡΓΑΝΗ tokens'

    company_id = fields.Many2one('res.company', required=True, ondelete='cascade')
    environment = fields.Selection([m for m in ERGANI_MODES if m[0] != 'off'], required=True)
    access_token = fields.Char()
    refresh_token = fields.Char()
    access_expires = fields.Datetime()
    refresh_expires = fields.Datetime()

    _company_env_unique = models.Constraint(
        'UNIQUE (company_id, environment)', 'Μία συνεδρία ανά εταιρεία και περιβάλλον.')
