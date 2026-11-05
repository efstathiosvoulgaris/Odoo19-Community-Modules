from odoo import fields, models


class ErganiBranch(models.Model):
    """Παραρτήματα του εργοδότη όπως τα ξέρει το ΕΡΓΑΝΗ (EX_BASE_02). The
    card declares the employee's branch; without one, the company default."""
    _name = 'ergani.branch'
    _description = 'Παράρτημα ΕΡΓΑΝΗ'
    _order = 'aa'

    aa = fields.Integer(string='Α/Α', required=True, help='0 = έδρα.')
    name = fields.Char(string='Περιγραφή', required=True)
    address = fields.Char(string='Διεύθυνση')
    company_id = fields.Many2one('res.company', required=True, default=lambda s: s.env.company)
    active = fields.Boolean(default=True)
    last_sync = fields.Datetime(string='Συγχρονισμός', readonly=True)

    _company_aa_unique = models.Constraint(
        'UNIQUE (company_id, aa)', 'Ο Α/Α παραρτήματος υπάρχει ήδη.')

    def _compute_display_name(self):
        for branch in self:
            branch.display_name = '%s — %s' % (branch.aa, branch.name or '')
