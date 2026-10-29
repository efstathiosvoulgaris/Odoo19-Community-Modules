import hashlib
import hmac
import secrets
from datetime import timedelta

from odoo import _, api, fields, models

PAIR_MINUTES = 10
PAIR_MAX_FAILURES = 5
# No 0/O, 1/I: the code is read off a screen and typed on a phone.
PAIR_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'


def token_hash(token):
    return hashlib.sha256((token or '').encode()).hexdigest()


class ServiceSignatureDevice(models.Model):
    """The phone at the till where customers sign for their device. It holds a
    token issued once at pairing; only its hash is stored here."""
    _name = 'service.signature.device'
    _description = 'Συσκευή Υπογραφής'
    _order = 'name'

    name = fields.Char(string='Συσκευή', required=True, help='Π.χ. «Κινητό Ταμείου».')
    active = fields.Boolean(default=True)
    token_hash = fields.Char(readonly=True, copy=False, index=True)
    paired = fields.Boolean(string='Συνδεδεμένη', compute='_compute_paired')
    pair_code_hash = fields.Char(readonly=True, copy=False)
    pair_until = fields.Datetime(readonly=True, copy=False)
    pair_failures = fields.Integer(readonly=True, copy=False)
    pair_requested_by = fields.Many2one('res.users', readonly=True, copy=False)
    paired_at = fields.Datetime(string='Σύζευξη', readonly=True, copy=False)
    paired_by = fields.Many2one('res.users', string='Σύζευξη από', readonly=True, copy=False)
    last_seen = fields.Datetime(string='Τελευταία Επαφή', readonly=True, copy=False)
    # Written by every «Παραλήφθηκε»: two PCs at once collide on this row
    # instead of both creating a request.
    last_request_at = fields.Datetime(readonly=True, copy=False)

    @api.depends('token_hash')
    def _compute_paired(self):
        for device in self:
            device.paired = bool(device.token_hash)

    def action_pair(self):
        """A one-time code, valid PAIR_MINUTES, typed into the app to receive
        its token. A new code replaces the previous one."""
        self.ensure_one()
        code = ''.join(secrets.choice(PAIR_ALPHABET) for _i in range(8))
        self.write({
            'pair_code_hash': token_hash(code),
            'pair_until': fields.Datetime.now() + timedelta(minutes=PAIR_MINUTES),
            'pair_failures': 0,
            'pair_requested_by': self.env.user.id,
        })
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Κωδικός σύζευξης για «%s»', self.name),
                'message': _('%(code)s — πληκτρολογήστε τον στην εφαρμογή μέσα σε %(min)s λεπτά.',
                             code=code, min=PAIR_MINUTES),
                'sticky': True,
                'type': 'info',
            },
        }

    def action_unpair(self):
        """Lost or replaced phone: its token stops working at once."""
        self.write({'token_hash': False, 'pair_code_hash': False, 'pair_until': False,
                    'paired_at': False, 'paired_by': False})

    @api.model
    def _pair(self, code):
        """Exchange a live pairing code for a new device token, or False.
        Every wrong guess counts against all live codes; after
        PAIR_MAX_FAILURES they are wiped and a manager has to issue a new one."""
        live = self.sudo().search([('pair_until', '>', fields.Datetime.now()),
                                   ('pair_code_hash', '!=', False)])
        wanted = token_hash((code or '').strip().upper())
        device = live.filtered(lambda d: hmac.compare_digest(d.pair_code_hash, wanted))[:1]
        if not device:
            for d in live:
                failures = d.pair_failures + 1
                d.write({'pair_failures': failures} if failures < PAIR_MAX_FAILURES
                        else {'pair_failures': failures, 'pair_code_hash': False,
                              'pair_until': False})
            return False
        token = secrets.token_urlsafe(32)
        device.write({
            'token_hash': token_hash(token),
            'pair_code_hash': False,
            'pair_until': False,
            'pair_failures': 0,
            'paired_at': fields.Datetime.now(),
            'paired_by': device.pair_requested_by.id,
        })
        return token

    @api.model
    def _from_token(self, token):
        if not token:
            return self.browse()
        return self.sudo().search([('token_hash', '=', token_hash(token))], limit=1)
