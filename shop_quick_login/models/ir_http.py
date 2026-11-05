import time

from odoo import models
from odoo.http import SessionExpiredException, request

DEFAULT_IDLE_MINUTES = 15
SERVER_GRACE_MINUTES = 5
# Αιτήματα που κάνει ο browser μόνος του: δεν μετρούν ως δραστηριότητα του ανθρώπου.
BACKGROUND_PATHS = ('/websocket', '/longpolling', '/bus/', '/web/webclient/version_info')


def idle_minutes(env):
    try:
        return max(0, int(env['ir.config_parameter'].sudo().get_param(
            'shop_quick_login.idle_minutes', DEFAULT_IDLE_MINUTES)))
    except (TypeError, ValueError):
        return DEFAULT_IDLE_MINUTES


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    @classmethod
    def _authenticate(cls, endpoint):
        super()._authenticate(endpoint)
        cls._ql_server_idle()

    @classmethod
    def _ql_server_idle(cls):
        """Δίχτυ ασφαλείας στον server, μόνο για συνεδρίες γρήγορης σύνδεσης: αν ο browser έπαψε
        να στέλνει αιτήματα ανθρώπου για (λεπτά αδράνειας + 5'), η συνεδρία λήγει. Το ταμείο
        μετρά ως δραστηριότητα, οπότε ένα ανοιχτό ταμείο δεν κλείνει ποτέ από εδώ."""
        session = request.session
        seen = session.get('ql_seen')
        if not seen or not session.uid:
            return
        if (request.httprequest.path or '').startswith(BACKGROUND_PATHS):
            return
        minutes = idle_minutes(request.env)
        if session.get('ql_no_idle') or not minutes:
            return
        now = time.time()
        if now - seen > (minutes + SERVER_GRACE_MINUTES) * 60:
            session.logout(keep_db=True)
            raise SessionExpiredException('Αποσύνδεση λόγω αδράνειας')
        if now - seen > 30:
            session['ql_seen'] = now

    def session_info(self):
        info = super().session_info()
        device = self.env['shop.ql.device']._from_request()
        info['ql_idle_minutes'] = 0 if (device and device.no_idle_logout) else idle_minutes(self.env)
        return info
