import base64
import json
import logging

from psycopg2 import IntegrityError, OperationalError
from werkzeug.exceptions import NotFound

from odoo import fields, http
from odoo.http import Response, request

_logger = logging.getLogger(__name__)
MAX_BODY = 1024 * 1024
MAX_PAYMENTS = 500


def _json(data, status=200, headers=None):
    return Response(json.dumps(data), status=status,
                    headers=[('Content-Type', 'application/json')] + (headers or []))


def _deny():
    # Ίδια απάντηση για κάθε άρνηση: ο άγνωστος δεν μαθαίνει τι λείπει.
    return _json({'error': 'unauthorized'}, status=401,
                 headers=[('WWW-Authenticate', 'Basic realm="dias"')])


class DiasController(http.Controller):
    """Υποδοχή ΔΙΑΣ DCT Creditor. Η βάση έρχεται στη διαδρομή· το nginx τη δίνει στο Odoo ως
    X-Odoo-Database (ο server έχει δύο βάσεις, χωρίς dbfilter). Χωρίς βάση το Odoo απαντά 404."""

    @http.route('/dias/online/<string:db>', type='http', auth='public',
                methods=['GET', 'HEAD', 'POST'], csrf=False, readonly=False, save_session=False,
                sitemap=False)
    def online(self, db, **kw):
        if db != request.db:
            raise NotFound()
        if request.httprequest.method != 'POST':
            # Έλεγχος διαθεσιμότητας από το ΔΙΑΣ Portal.
            return request.make_response('OK', headers=[('Content-Type', 'text/plain')])
        try:
            return self._online()
        except (OperationalError, IntegrityError):
            raise  # ταυτόχρονα αιτήματα: το Odoo ξανατρέχει το αίτημα με νέο στιγμιότυπο
        except Exception:  # noqa: BLE001
            # Τίποτα από αυτό το αίτημα δεν μένει: η ΔΙΑΣ ξαναστέλνει και η εγγραφή γίνεται τότε.
            request.env.cr.rollback()
            _logger.exception('ΔΙΑΣ /dias/online: απρόσμενο σφάλμα')
            return _json({'error': 'internal error'}, status=500)

    @staticmethod
    def _company(payments):
        actor = str((payments[0].get('actorID') if payments else '') or '').strip()
        if not actor:
            return request.env['res.company']
        return request.env['res.company'].sudo().search([('dias_org_code', '=', actor)], limit=1)

    @staticmethod
    def _authorised(company):
        """Fail closed: χωρίς λίστα IP ή χωρίς Basic Auth, κανείς δεν περνά."""
        company = company.sudo()
        ips = [i.strip() for i in (company.dias_allowed_ips or '').split(',') if i.strip()]
        if not ips or request.httprequest.remote_addr not in ips:
            _logger.warning('ΔΙΑΣ: άρνηση από IP %s', request.httprequest.remote_addr)
            return False
        header = request.httprequest.headers.get('Authorization', '')
        if not header.startswith('Basic '):
            return False
        try:
            user, pwd = base64.b64decode(header[6:]).decode('utf-8').split(':', 1)
        except Exception:  # noqa: BLE001
            return False
        return company._dias_check_basic(user, pwd)

    @staticmethod
    def _vals(p):
        ri = (p.get('RI_MID') or str(p.get('remittanceInformation') or '')[:25] or '').strip()
        return {
            'name': str(p.get('RID') or '').strip(),
            'ri_mid': ri,
            'amount': float(p.get('paidAmount') or 0),
            'bk_date': p.get('bkDate') or False,
            'payment_dt': str(p.get('paymentDtTm') or ''),
            'debtor_name': p.get('debtorName') or '',
            'debtor_bic': p.get('debtorBankBIC') or '',
            'transaction_id': str(p.get('transactionID') or ''),
            'remittance': str(p.get('remittanceInformation') or '')[:140],
            'raw': json.dumps(p, ensure_ascii=False),
        }

    def _online(self):
        body = request.httprequest.get_data(cache=False)[:MAX_BODY + 1]
        if len(body) > MAX_BODY:
            return _json({'error': 'too large'}, status=413)
        try:
            data = json.loads(body.decode('utf-8'))
            msg_type = data.get('msgType')
            payments = data.get('incomingPayments') or []
            assert isinstance(payments, list)
        except Exception:  # noqa: BLE001
            return _deny()
        company = self._company(payments)
        if not company or not self._authorised(company):
            return _deny()
        # Από εδώ και πέρα ο καλών είναι η ΔΙΑΣ.
        if msg_type not in ('DPG_ON', 'DPG_ONRequest') or len(payments) > MAX_PAYMENTS:
            return _json({'error': 'bad request'}, status=400)
        env_flag = data.get('env')
        company.sudo().dias_last_message_at = fields.Datetime.now()
        if env_flag != company.sudo().dias_env:
            # Ποτέ σιωπηλό 200: μια πληρωμή που «χάνεται» εδώ δεν ξαναεμφανίζεται.
            _logger.error('ΔΙΑΣ: μήνυμα env=%s, η βάση %s είναι ρυθμισμένη %s',
                          env_flag, request.db, company.sudo().dias_env)
            company._dias_notify_manager(
                'ΔΙΑΣ: μήνυμα άλλου περιβάλλοντος',
                'Απορρίφθηκε μήνυμα περιβάλλοντος %s· η βάση %s είναι ρυθμισμένη %s. Ελέγξτε τη '
                'διεύθυνση στο ΔΙΑΣ Portal.' % (env_flag, request.db, company.sudo().dias_env))
            return _json({'error': 'environment mismatch'}, status=409)

        Payment = request.env['dias.payment'].sudo()
        statuses, to_process = [], Payment
        for p in payments:
            try:
                vals = self._vals(p)
            except (AttributeError, TypeError, ValueError):
                return _json({'error': 'bad request'}, status=400)
            if not vals['name']:
                statuses.append({'status': 'REJECTED', 'rejectionCode': 'BE06', 'RID': p.get('RID')})
                continue
            if msg_type == 'DPG_ONRequest':
                accepted, reason = Payment._dias_request_verdict(company, vals['ri_mid'], vals['amount'])
                Payment._dias_register_request(company, vals, accepted, reason)
                statuses.append({'status': 'ACCEPTED' if accepted else 'REJECTED',
                                 'rejectionCode': None if accepted else 'BE06', 'RID': p.get('RID')})
            else:
                to_process |= Payment._dias_register(company, dict(vals, source='online'),
                                                     confirmed=True)
        if to_process:
            # Η καταχώρηση γίνεται μετά το commit, από το cron: η απάντηση στη ΔΙΑΣ δεν
            # περιμένει τη λογιστική, και μια αποτυχία εκεί δεν χάνει την πληρωμή.
            request.env.ref('l10n_gr_dias_rf.ir_cron_dias_process').sudo()._trigger()
        if msg_type == 'DPG_ON':
            return _json({'env': env_flag, 'msgType': 'DPG_ON'})
        return _json({'env': env_flag, 'msgType': 'DPG_ONResponse',
                      'incomingPaymentsStatus': statuses})
