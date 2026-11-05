import hashlib
import logging
from urllib.parse import quote

from odoo import _, http
from odoo.http import request

_logger = logging.getLogger(__name__)


def _safe_redirect(target):
    """Only same-site paths, never '//host', '/\\host' or 'http…'."""
    if target and target.startswith('/') and not target.startswith('//') \
            and '\\' not in target and not target.startswith('/ergani/'):
        return target
    return '/odoo'


class ErganiGate(http.Controller):
    """The only place a card is created (DESIGN §3): the logged-in user's own
    employee, after he scans his own card QR. Every route here is let through the gate
    with `ergani_gate_allowed`."""

    def _employee(self):
        emp = request.env.user.sudo().employee_id
        if not emp or not emp._ergani_required():
            return None
        return emp

    @http.route('/ergani/gate', type='http', auth='user', ergani_gate_allowed=True,
                sitemap=False)
    def gate(self, redirect=None, mode=None, **kw):
        emp = self._employee()
        state = request.env.user._ergani_gate_state()
        if not emp or (mode != 'out' and not state['required']):
            return request.redirect(_safe_redirect(redirect), 303)
        if mode == 'out' and state['mode'] != 'out':
            return request.redirect('/odoo', 303)
        return request.render('l10n_gr_ergani_card.gate_page', {
            'employee': emp.name,
            'mode': 'out' if mode == 'out' else 'in',
            'has_card': state['has_card'],
            'redirect': _safe_redirect(redirect),
            'simulation': state.get('simulation'),
        })

    @http.route('/ergani/gate/punch', type='jsonrpc', auth='user', ergani_gate_allowed=True)
    def punch(self, code=None, mode='in'):
        emp = self._employee()
        if not emp:
            return {'error': _('Δεν χρειάζεται κάρτα ΕΡΓΑΝΗ.')}
        if not emp.sudo().barcode:
            return {'error': _('Δεν σας έχει δοθεί κάρτα QR. Ζητήστε τη από τον υπεύθυνο.')}
        locked = emp._ergani_scan_locked_minutes()
        if locked:
            return {'error': _('Κλειδώθηκε μετά από λάθος κάρτα. Δοκιμάστε σε %s λεπτά.', locked)}
        if not emp._ergani_check_card(code):
            request.env.cr.commit()  # the failure counter must survive
            locked = emp._ergani_scan_locked_minutes()
            if locked:
                return {'error': _('Κλειδώθηκε μετά από 5 λάθη. Δοκιμάστε σε %s λεπτά.', locked)}
            return {'error': _('Δεν είναι η δική σας κάρτα.')}
        open_in = emp._ergani_open_in_card()
        if mode == 'out' and not open_in:
            return {'error': _('Δεν υπάρχει ανοιχτή προσέλευση.')}
        if mode != 'out' and open_in:
            return {'ok': True, 'already': True}
        meta = {
            'ip': request.httprequest.remote_addr,
            'user_agent': request.httprequest.user_agent.string,
            'session_hash': hashlib.sha256((request.session.sid or '').encode()).hexdigest()[:32],
        }
        card = request.env['ergani.card'].sudo()._ergani_create_punch(
            emp, '1' if mode == 'out' else '0', meta)
        if card.state == 'pending':
            request.env.ref('l10n_gr_ergani_card.ir_cron_ergani_send').sudo()._trigger()
        time_label = card._ergani_local_dt().strftime('%H:%M')
        result = {'ok': True, 'time': time_label, 'simulation': card.state == 'simulated'}
        if mode == 'out':
            # Log out this browser only. His other devices need no revoke: the
            # gate shuts their back office until the next «Προσέλευση», and a
            # till running under his account elsewhere keeps working (DESIGN §2).
            db = request.db
            request.env.cr.commit()  # the card first, then the logout
            request.session.logout(keep_db=True)
            result['redirect'] = '/web/login?db=' + quote(db or '')
        return result
