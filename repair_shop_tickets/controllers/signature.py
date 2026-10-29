# The phone at the till talks to these routes. It has no session: it sends
# its device token as «Authorization: Bearer …» and picks the database with
# the «X-Odoo-Database» header, which Odoo 19 honours statelessly when it
# passes dbfilter (odoo/http.py, _get_session_and_dbname).
import base64
import binascii
import json

from odoo import fields, http
from odoo.http import request

MAX_PNG_BYTES = 300 * 1024


class SignatureController(http.Controller):

    def _reply(self, data, status=200):
        response = request.make_json_response(data, status=status)
        response.headers['Cache-Control'] = 'no-store'
        return response

    def _body(self):
        try:
            return json.loads(request.httprequest.get_data() or b'{}')
        except ValueError:
            return {}

    def _env(self):
        request.env['ir.http']._auth_method_public()
        return request.env

    def _device(self):
        auth = request.httprequest.headers.get('Authorization', '')
        token = auth[7:] if auth.startswith('Bearer ') else ''
        device = self._env()['service.signature.device']._from_token(token)
        now = fields.Datetime.now()
        # The phone polls every 2 s; one write a minute is enough to show it is alive.
        if device and (not device.last_seen or (now - device.last_seen).total_seconds() > 60):
            device.last_seen = now
        return device

    @http.route('/service_sign/pair', type='http', auth='none', methods=['POST'],
                csrf=False, save_session=False)
    def pair(self, **kw):
        if not request.db:
            return self._reply({'error': 'unknown database'}, 400)
        token = self._env()['service.signature.device']._pair(self._body().get('code'))
        if not token:
            return self._reply({'error': 'Λάθος ή ληγμένος κωδικός.'}, 403)
        return self._reply({'token': token})

    @http.route('/service_sign/poll', type='http', auth='none', methods=['GET'],
                csrf=False, save_session=False)
    def poll(self, **kw):
        if not request.db:
            return self._reply({'error': 'unknown database'}, 400)
        device = self._device()
        if not device:
            return self._reply({'error': 'unpaired'}, 401)
        Request = request.env['service.signature.request'].sudo()
        Request._expire_stale()
        pending = Request.search([('device_id', '=', device.id), ('state', '=', 'pending')],
                                 limit=1, order='id')
        return self._reply({'device': device.name,
                            'request': pending._payload() if pending else None})

    @http.route('/service_sign/answer', type='http', auth='none', methods=['POST'],
                csrf=False, save_session=False)
    def answer(self, **kw):
        if not request.db:
            return self._reply({'error': 'unknown database'}, 400)
        device = self._device()
        if not device:
            return self._reply({'error': 'unpaired'}, 401)
        body = self._body()
        sign_request = request.env['service.signature.request'].sudo().search(
            [('id', '=', int(body.get('id') or 0)), ('device_id', '=', device.id)])
        if not sign_request:
            return self._reply({'ok': False})
        png = None
        if body.get('decision') == 'ok':
            try:
                png = base64.b64decode(body.get('png') or '', validate=True)
            except (binascii.Error, ValueError):
                png = b''
            if not png.startswith(b'\x89PNG') or len(png) > MAX_PNG_BYTES:
                return self._reply({'error': 'bad signature image'}, 400)
        return self._reply({'ok': sign_request._answer(
            'ok' if png else 'decline', png)})
