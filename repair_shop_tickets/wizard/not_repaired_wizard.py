from odoo import fields, models


class ServiceTicketNotRepairedWizard(models.TransientModel):
    _name = 'service.ticket.not.repaired.wizard'
    _description = 'Δεν Επισκευάστηκε'

    ticket_id = fields.Many2one('service.ticket', required=True, ondelete='cascade')
    reason = fields.Text(string='Αιτία', required=True,
                         help='π.χ. δεν υπάρχει ανταλλακτικό, ο πελάτης αρνήθηκε')
    # Replaces the labour price so a repair quote left there is never invoiced.
    fee = fields.Float(string='Χρέωση Ελέγχου', default=0.0)

    def action_confirm(self):
        self.ticket_id._set_not_repaired(self.reason, self.fee)
        return {'type': 'ir.actions.act_window_close'}
