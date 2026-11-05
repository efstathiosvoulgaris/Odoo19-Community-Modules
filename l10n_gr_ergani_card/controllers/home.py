from urllib.parse import quote

from odoo import http
from odoo.http import request
from odoo.addons.web.controllers.home import Home

from ..models.ir_http import GATE_URL


class ErganiHome(Home):
    """`/odoo` is auth="none" (it checks the session itself), so the
    ir.http hook never sees it: send a user who still has to punch to the
    gate before the web client loads (DESIGN §5.4 α)."""

    @http.route()
    def web_client(self, s_action=None, **kw):
        if request.session.uid and request.db:
            request.update_env(user=request.session.uid)
            if request.env['ir.http']._ergani_gate_required():
                return request.redirect(
                    GATE_URL + '?redirect=' + quote(
                        request.httprequest.full_path), 303)
        return super().web_client(s_action=s_action, **kw)
