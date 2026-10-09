# -*- coding: utf-8 -*-
"""Geniki Taxydromiki Web API V2 — spec: Courier API/GENIKI/jobservicesapiv2.md.

SOAP (JobServicesV2.asmx). Authenticate returns a key used by every other
call until it expires (result 11 → authenticate again). A test service
exists. Vouchers are finalised with ClosePendingJobsByDate before the
parcels are handed over — the equivalent of the ACS pickup list, without a
document. Production credentials are issued only after Geniki confirms
authenticate / create / print / cancel / finalise are implemented.
"""
import logging
from datetime import datetime, time

import requests

from odoo import _, fields, models
from odoo.exceptions import UserError
from odoo.tools.zeep import Client

from .courier_boxnow import _intl_phone

_logger = logging.getLogger(__name__)

GENIKI_URL = {
    True: 'https://testvoucher.taxydromiki.gr/JobServicesV2.asmx',
    False: 'https://voucher.taxydromiki.gr/JobServicesV2.asmx',
}
GENIKI_TIMEOUT = 60
GENIKI_INVALID_KEY = 11
GENIKI_ERRORS = {
    1: 'Αποτυχία σύνδεσης (λάθος username, password ή application key)',
    3: 'Δεν στάλθηκαν δεδομένα',
    4: 'Μη επιτρεπτή ενέργεια (το voucher έχει ήδη οριστικοποιηθεί)',
    700: 'Λείπει όνομα, διεύθυνση ή πόλη',
    701: 'Υπηρεσία αντικαταβολής χωρίς ποσό',
    702: 'Ποσό αντικαταβολής χωρίς υπηρεσία',
    703: 'Υπέρβαση ορίου αντικαταβολής',
    706: 'Η ημερομηνία παραλαβής είναι παλαιότερη από σήμερα',
    8: 'Εσωτερικό σφάλμα της Γενικής (SQL)',
    9: 'Το voucher δεν υπάρχει',
    10: 'Δεν έχετε δικαίωμα σε αυτό το voucher',
    11: 'Το κλειδί σύνδεσης έληξε',
    12: 'Εσωτερικό σφάλμα της Γενικής',
    13: 'Το voucher είναι ακυρωμένο',
    14: 'Ο server της Γενικής είναι απασχολημένος — ξαναδοκιμάστε',
    15: 'Όριο κλήσεων — ξαναδοκιμάστε σε λίγο',
}
# One parsed WSDL per environment and process: it is fetched over the network.
_CLIENTS = {}


class CourierAccount(models.Model):
    _inherit = 'courier.account'

    courier = fields.Selection(selection_add=[('geniki', 'Γενική Ταχυδρομική')],
                               ondelete={'geniki': 'cascade'})
    geniki_username = fields.Char(string='Username', groups='base.group_system')
    geniki_password = fields.Char(string='Password', groups='base.group_system')
    geniki_app_key = fields.Char(string='Application Key', groups='base.group_system')
    geniki_test = fields.Boolean(
        string='Δοκιμαστικό', default=True,
        help='testvoucher.taxydromiki.gr με τον δοκιμαστικό χρήστη της Γενικής.')
    geniki_auth_key = fields.Char(groups='base.group_system', copy=False)
    geniki_last_close = fields.Datetime(
        string='Τελευταία Οριστικοποίηση', readonly=True, copy=False,
        help='Η επόμενη οριστικοποίηση κλείνει ό,τι δημιουργήθηκε από τότε '
             '(πρακτική που συστήνει η Γενική).')

    # ── transport ────────────────────────────────────────────────────────────
    def _geniki_url(self):
        return GENIKI_URL[bool(self.geniki_test)]

    def _geniki_service(self):
        url = self._geniki_url()
        if url not in _CLIENTS:
            try:
                _CLIENTS[url] = Client(f'{url}?WSDL', timeout=GENIKI_TIMEOUT,
                                       operation_timeout=GENIKI_TIMEOUT)
            except Exception as e:
                raise UserError(_('Η Γενική δεν απαντά: %s', e)) from e
        return _CLIENTS[url].service

    @staticmethod
    def _geniki_raise(code, what):
        raise UserError(_('Γενική (%(what)s): %(msg)s [%(code)s]', what=what, code=code,
                          msg=GENIKI_ERRORS.get(code, _('σφάλμα'))))

    def _geniki_authenticate(self):
        acc = self.sudo()
        if not (acc.geniki_username and acc.geniki_password and acc.geniki_app_key):
            raise UserError(_('Συμπληρώστε Username, Password και Application Key της Γενικής.'))
        res = self._geniki_service().Authenticate(
            sUsrName=acc.geniki_username, sUsrPwd=acc.geniki_password,
            applicationKey=acc.geniki_app_key)
        if res.Result != 0:
            self._geniki_raise(res.Result, 'Authenticate')
        acc.geniki_auth_key = res.Key
        return res.Key

    def _geniki_call(self, method, key_arg, what, **kwargs):
        """Call with the stored key; on «invalid key» authenticate once and
        retry. Returns the raw result (int or result object)."""
        self.ensure_one()
        operation = getattr(self._geniki_service(), method)
        key = self.sudo().geniki_auth_key or self._geniki_authenticate()
        for attempt in (0, 1):
            try:
                res = operation(**{key_arg: key}, **kwargs)
            except Exception as e:
                raise UserError(_('Γενική (%(what)s): %(error)s', what=what, error=e)) from e
            code = res if isinstance(res, int) else res.Result
            if code == GENIKI_INVALID_KEY and not attempt:
                key = self._geniki_authenticate()
                continue
            break
        _logger.info('Geniki %s → %s', method, code)
        if code not in (0, 13):  # 13 = job canceled: a status, not a failure
            self._geniki_raise(code, what)
        return res

    # ── interface ────────────────────────────────────────────────────────────
    def _geniki_check_ready(self, voucher):
        voucher._check_missing((
            ('street', 'Οδός'), ('zip', 'Τ.Κ.'), ('city', 'Περιοχή'), ('mobile', 'Κινητό')))

    def _geniki_create(self, voucher):
        services = []
        if voucher.cod_amount > 0:
            services.append('ΑΜ')
        if voucher.charge_type == 'recipient':
            services.append('ΧΠ')
        res = self._geniki_call('CreateJob', 'sAuthKey', 'CreateJob', eType='Voucher', oVoucher={
            'OrderId': voucher.reference or str(voucher.id),
            'Name': voucher.recipient_name,
            'Address': ' '.join(filter(None, (voucher.street, voucher.street_number))),
            'City': voucher.city,
            'Country': voucher.country_code or 'GR',
            'Email': voucher.email or '',
            'Telephone': _intl_phone(voucher.mobile),
            'Zip': (voucher.zip or '').replace(' ', ''),
            'Weight': round(voucher.weight, 2),
            'Pieces': max(voucher.item_quantity, 1),
            'Comments': (voucher.notes or '')[:40],
            'Services': ','.join(services),
            'CodAmount': f'{voucher.cod_amount:.2f}' if voucher.cod_amount > 0 else '0',
            'InsAmount': 0,
            'VoucherNo': '',
            'SubCode': '',
            'BelongsTo': '',
            'DeliverTo': '',
            'ReceivedDate': datetime.combine(voucher.pickup_date, time.min),
            'ContentsDescription': '',
            'SendAndReturnRecipient': '',
        })
        if not res.Voucher:
            raise UserError(_('Η Γενική δεν επέστρεψε αριθμό voucher.'))
        voucher.geniki_job_id = str(res.JobId)
        return str(res.Voucher)

    def _geniki_print(self, vouchers):
        """GetVouchersPdf is plain HTTP: a PDF on success, text with the
        result code on failure. «Flyer» = A4 paper."""
        self.ensure_one()
        key = self.sudo().geniki_auth_key or self._geniki_authenticate()
        for attempt in (0, 1):
            try:
                resp = requests.get(f'{self._geniki_url()}/GetVouchersPdf', timeout=GENIKI_TIMEOUT, params=[
                    ('authKey', key), *[('voucherNumbers', v) for v in vouchers.mapped('name')],
                    ('format', 'Flyer'), ('extraInfoFormat', 'None')])
            except requests.RequestException as e:
                raise UserError(_('Η Γενική δεν απαντά: %s', e)) from e
            if resp.content[:4] == b'%PDF':
                return resp.content
            text = resp.text.strip()
            code = int(text) if text.lstrip('-').isdigit() else None
            if code == GENIKI_INVALID_KEY and not attempt:
                key = self._geniki_authenticate()
                continue
            if code is not None:
                self._geniki_raise(code, 'GetVouchersPdf')
            raise UserError(_('Γενική (GetVouchersPdf): HTTP %(status)s %(text)s',
                              status=resp.status_code, text=text[:200]))

    def _geniki_cancel(self, voucher):
        if not voucher.geniki_job_id:
            raise UserError(_('Λείπει το Job ID της Γενικής για το voucher %s.', voucher.name))
        self._geniki_call('CancelJob', 'sAuthKey', 'CancelJob',
                          nJobId=int(voucher.geniki_job_id), bCancel=True)

    def _geniki_close_day(self, date, vouchers):
        """Finalise everything created since the last finalisation."""
        now = fields.Datetime.now()
        since = self.geniki_last_close or datetime.combine(min(vouchers.mapped('pickup_date')), time.min)
        self._geniki_call('ClosePendingJobsByDate', 'sAuthKey', 'ClosePendingJobsByDate',
                          dFr=since, dTo=now)
        self.geniki_last_close = now
        return now.strftime('%Y-%m-%d %H:%M'), None, vouchers

    def _geniki_track(self, voucher):
        res = self._geniki_call('TrackAndTrace', 'authKey', 'TrackAndTrace',
                                voucherNo=voucher.name, language='el')
        checkpoints = res.Checkpoints or []
        # zeep may wrap the array: Checkpoints.Checkpoint
        if not isinstance(checkpoints, list):
            checkpoints = getattr(checkpoints, 'Checkpoint', None) or []
        last = checkpoints[-1] if checkpoints else None
        text = ' — '.join(filter(None, (
            last and last.Status, last and last.Shop,
            last and last.StatusDate and last.StatusDate.strftime('%d/%m %H:%M'))))
        status = (res.Status or '').upper()
        if (res.DeliveredAt or '').upper() == 'RETURN TO SENDER':
            return 'returned', text
        if status == 'DELIVERED':
            return 'delivered', text
        return False, text or status

    def _geniki_test_connection(self):
        self._geniki_authenticate()
        res = self._geniki_call('GetShopsList', 'authKey', 'GetShopsList')
        shops = res.Shops or []
        if not isinstance(shops, list):
            shops = getattr(shops, 'Shop', None) or []
        return _('Username, Password, Application Key: OK (%(env)s). Καταστήματα Γενικής: %(count)s.',
                 env=_('Δοκιμαστικό') if self.geniki_test else _('Παραγωγή'), count=len(shops))

    def _geniki_tracking_url(self, number):
        return f'https://www.taxydromiki.com/track/{number}'


class CourierVoucher(models.Model):
    _inherit = 'courier.voucher'

    geniki_job_id = fields.Char(string='Job ID Γενικής', readonly=True, copy=False)
