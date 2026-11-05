from urllib.parse import quote

import werkzeug.exceptions

from odoo import models
from odoo.http import SessionExpiredException, request

GATE_URL = '/ergani/gate'


def _ergani_exempt_path():
    """Never gated (DESIGN §5.4): the POS and anything it calls, and the
    gate itself."""
    req = request.httprequest
    path = req.path or ''
    if path.startswith(('/pos/', '/ergani/')):
        return True
    referer = req.headers.get('Referer') or ''
    return '/pos/ui' in referer or '/pos/web' in referer


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    @classmethod
    def _authenticate(cls, endpoint):
        super()._authenticate(endpoint)
        routing = endpoint.routing
        if routing.get('auth') != 'user' or routing.get('ergani_gate_allowed'):
            return
        if _ergani_exempt_path() or not cls._ergani_gate_required():
            return
        if routing.get('type') == 'http':
            werkzeug.exceptions.abort(request.redirect(
                GATE_URL + '?redirect=' + quote(request.httprequest.full_path)))
        raise SessionExpiredException('ΕΡΓΑΝΗ: απαιτείται χτύπημα κάρτας')

    @classmethod
    def _ergani_gate_required(cls):
        """True while the logged-in user still has to punch «Προσέλευση».
        Looked up on every request (two indexed reads, no session cache):
        enabling an employee takes effect at once, and a «Αποχώρηση» on
        another computer is seen at once."""
        user = request.env['res.users'].sudo().browse(request.env.uid)
        if not user or user.share:
            return False
        emp = user.employee_id
        if not emp or not emp._ergani_required():
            return False
        return not emp._ergani_open_in_card()

    def session_info(self):
        info = super().session_info()
        emp = self.env.user.sudo().employee_id
        info['ergani_in'] = bool(emp and emp._ergani_required() and emp._ergani_open_in_card())
        return info
