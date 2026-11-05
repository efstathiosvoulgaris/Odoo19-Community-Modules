import time

from odoo import _, http
from odoo.addons.web.controllers.home import Home
from odoo.addons.web.controllers.utils import _get_login_redirect_url, ensure_db
from odoo.exceptions import AccessDenied
from odoo.http import request

from ..models.device import DEVICE_DAYS, cookie_name
from ..models.res_users import AUTH_PATH, CREDENTIAL_TYPE

GENERIC_ERROR = ('Δεν έγινε σύνδεση. Ελέγξτε το PIN· μετά από πολλά λάθη η γρήγορη σύνδεση '
                 'κλειδώνει για λίγο. Μπορείτε πάντα να συνδεθείτε με τον κωδικό σας.')


class QuickLogin(http.Controller):

    @http.route('/quick-login', type='http', auth='none', sitemap=False)
    def page(self, **kw):
        ensure_db()
        request.env['ir.http']._auth_method_public()
        device = request.env['shop.ql.device']._from_request()
        users = request.env['res.users']._ql_eligible_users() if device else []
        response = request.render('shop_quick_login.quick_login_page', {
            'device': device,
            'users': [{'id': u.id, 'name': u.name} for u in users],
            'db': request.db,
        })
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Frame-Options'] = 'DENY'
        return response

    @http.route(AUTH_PATH, type='jsonrpc', auth='none', readonly=False)
    def authenticate(self, user_id=None, card=None, pin=None, **kw):
        if not request.db:
            return {'error': GENERIC_ERROR}
        request.env['ir.http']._auth_method_public()
        env = request.env
        Log = env['shop.ql.log']
        ip = request.httprequest.remote_addr
        device = env['shop.ql.device']._from_request()
        if not device:
            return {'error': _('Αυτός ο υπολογιστής δεν είναι εγγεγραμμένος για γρήγορη σύνδεση.')}
        method = 'card' if card else 'pin'
        user = env['res.users']
        if card:
            found = env['hr.employee']._ql_find_by_card(card)
            if not found.user_id:
                Log._record(env['res.users'], device, method, False, ip, 'άγνωστη κάρτα')
                device._register_failure()
                request.env.cr.commit()
                return {'error': GENERIC_ERROR}
            user = found.user_id
        elif user_id:
            user = env['res.users'].sudo().browse(int(user_id)).exists()
        if not user:
            device._register_failure()
            request.env.cr.commit()
            return {'error': GENERIC_ERROR}
        credential = {'type': CREDENTIAL_TYPE, 'login': user.sudo().login, 'pin': str(pin or '')}
        try:
            auth_info = request.session.authenticate(env, credential)
        except AccessDenied:
            Log._record(user, device, method, False, ip)
            # Οι μετρητές αποτυχιών (εργαζόμενος, συσκευή) πρέπει να μείνουν: το AccessDenied
            # θα έκανε rollback. Στη συναλλαγή δεν υπάρχει τίποτε άλλο.
            request.env.cr.commit()
            return {'error': GENERIC_ERROR}
        request.session['ql_seen'] = time.time()
        request.session['ql_no_idle'] = bool(device.no_idle_logout)
        Log._record(user, device, method, True, ip)
        return {'redirect': _get_login_redirect_url(auth_info['uid'])}

    @http.route('/quick-login/enroll/<int:device_id>/<string:nonce>', type='http', auth='user',
                methods=['GET'], sitemap=False, ergani_gate_allowed=True)
    def enroll(self, device_id, nonce, **kw):
        if not request.env.user.has_group('base.group_system'):
            return request.not_found()
        device = request.env['shop.ql.device'].browse(device_id).exists()
        token = device and device._enroll(nonce, request.httprequest.user_agent.string)
        if not token:
            return request.redirect('/odoo/ql-devices')
        request.future_response.set_cookie(
            cookie_name(request.db), token, max_age=DEVICE_DAYS * 86400, httponly=True,
            secure=True, samesite='Lax', path='/', cookie_type='required')
        return request.redirect('/odoo/ql-devices/%s' % device.id)


class QuickLoginHome(Home):

    @http.route()
    def web_login(self, redirect=None, **kw):
        response = super().web_login(redirect=redirect, **kw)
        if getattr(response, 'qcontext', None) is not None and request.db:
            device = request.env['shop.ql.device']._from_request()
            response.qcontext['ql_device_name'] = device.name if device else False
            response.qcontext['ql_idle'] = request.params.get('ql_idle') == '1'
        return response
