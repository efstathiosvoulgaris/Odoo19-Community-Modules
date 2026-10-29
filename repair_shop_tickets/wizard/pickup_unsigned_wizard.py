from odoo import _, fields, models
from odoo.exceptions import UserError


class ServiceTicketPickupUnsignedWizard(models.TransientModel):
    """The phone is off, broken or lost: a Service Manager hands the device
    over without a signature, and says why."""
    _name = 'service.ticket.pickup.unsigned.wizard'
    _description = 'Παραλήφθηκε χωρίς υπογραφή'

    ticket_id = fields.Many2one('service.ticket', required=True, ondelete='cascade')
    reason = fields.Text(string='Αιτία', required=True,
                         help='π.χ. το κινητό υπογραφών δεν λειτουργεί')

    def action_confirm(self):
        if not self.env.user.has_group('repair_shop_tickets.group_service_ticket_manager'):
            raise UserError(_('Μόνο Υπεύθυνος Service.'))
        ticket = self.ticket_id
        if ticket.state != 'resolved':
            raise UserError(_('Παραλαβή γίνεται μόνο για δελτίο σε «Επιλύθηκε».'))
        ticket._mark_picked_up(pickup_unsigned_reason=self.reason)
        ticket.message_post(body=_('Παραλαβή χωρίς υπογραφή πελάτη. Αιτία: %s', self.reason))
        return {'type': 'ir.actions.act_window_close'}
