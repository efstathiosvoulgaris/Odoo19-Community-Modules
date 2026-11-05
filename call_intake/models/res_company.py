from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    call_intake_project_id = fields.Many2one(
        'project.project', string='Έργο Αιτημάτων',
        help='Το έργο όπου καταχωρίζονται τα τηλεφωνήματα.')

    def _call_intake_project(self):
        """The configured project, else the one this module ships."""
        self.ensure_one()
        return (self.call_intake_project_id
                or self.env.ref('call_intake.project_customer_requests',
                                raise_if_not_found=False)
                or self.env['project.project'])
