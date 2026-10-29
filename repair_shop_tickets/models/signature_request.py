import base64
from datetime import timedelta

from odoo import _, api, fields, models

EXPIRE_MINUTES = 5


class ServiceSignatureRequest(models.Model):
    """One «Παραλήφθηκε» waiting for the customer to sign on the phone. The
    phone and the PC dialog both read it; only a signed answer moves the
    ticket to «Παραλήφθηκε»."""
    _name = 'service.signature.request'
    _description = 'Αίτημα Υπογραφής'
    _order = 'id desc'

    ticket_id = fields.Many2one('service.ticket', required=True, ondelete='cascade', index=True)
    device_id = fields.Many2one('service.signature.device', required=True, ondelete='restrict')
    kind = fields.Selection([
        ('repaired', 'Επισκευάστηκε'),
        ('not_repaired', 'Δεν Επισκευάστηκε'),
    ], required=True, default='repaired')
    state = fields.Selection([
        ('pending', 'Αναμονή'),
        ('signed', 'Υπογράφηκε'),
        ('declined', 'Άκυρο από τον πελάτη'),
        ('cancelled', 'Ακυρώθηκε'),
        ('expired', 'Έληξε'),
    ], default='pending', required=True, index=True)
    requested_by = fields.Many2one('res.users', string='Αίτημα από', required=True,
                                   default=lambda self: self.env.user)
    answered_at = fields.Datetime(readonly=True)

    @api.model
    def _expire_stale(self):
        """Pending requests older than EXPIRE_MINUTES expire; those whose ticket
        left «Επιλύθηκε» meanwhile (cancelled, reset) are cancelled. Run on
        every read, so no cron is needed."""
        pending = self.sudo().search([('state', '=', 'pending')])
        limit = fields.Datetime.now() - timedelta(minutes=EXPIRE_MINUTES)
        pending.filtered(lambda r: r.ticket_id.state != 'resolved').write({'state': 'cancelled'})
        pending.filtered(lambda r: r.state == 'pending' and r.create_date < limit) \
            .write({'state': 'expired'})

    def _payload(self):
        """What the phone shows — nothing beyond name, device and the sentence."""
        self.ensure_one()
        ticket = self.ticket_id
        company = self.env.company
        return {
            'id': self.id,
            'customer': ticket.partner_id.name or '',
            'brand': ticket.brand_id.name or '',
            'model': ticket.product_model_id.name or '',
            'sentence': (company.repair_sign_text_not_repaired if self.kind == 'not_repaired'
                         else company.repair_sign_text_repaired) or '',
        }

    def _answer(self, decision, png=None):
        """The phone's answer. False when the request is no longer pending."""
        self.ensure_one()
        self._expire_stale()
        if self.state != 'pending':
            return False
        now = fields.Datetime.now()
        # The phone has no user: log it as the employee who asked for the signature.
        ticket = self.ticket_id.with_user(self.requested_by).sudo()
        if decision != 'ok':
            self.write({'state': 'declined', 'answered_at': now})
            ticket.message_post(body=_('Ο πελάτης πάτησε «Άκυρο» στην υπογραφή παραλαβής.'))
            return True
        self.write({'state': 'signed', 'answered_at': now})
        ticket._mark_picked_up(
            pickup_signature=base64.b64encode(png),
            pickup_signed_at=now,
            pickup_request_id=self.id,
        )
        ticket.message_post(
            body=_('Παραλαβή με υπογραφή πελάτη (αίτημα από %s).', self.requested_by.name),
            attachments=[('υπογραφή-%s.png' % ticket.name.replace('/', '-'), png)],
        )
        return True

    def action_cancel(self):
        self.sudo().filtered(lambda r: r.state == 'pending').write({'state': 'cancelled'})
        return True

    def read_status(self):
        """For the waiting dialog on the PC."""
        self.ensure_one()
        self._expire_stale()
        me = self.sudo()
        return {'state': me.state, 'ticket': me.ticket_id.name}
