# -*- coding: utf-8 -*-
"""BOX NOW Partner API — spec: Courier API/BOXNOW/BoxNow API Manual (v.7.2).md.

OAuth2 client credentials (token valid 1 h, Bearer header). The business
drops parcels at any locker itself (AnyAPM, origin locationId "2"), so the
compartment size is mandatory. The recipient collects from a locker (APM):
the destination is a locker id, not a street address. No pickup list.
There is a Stage (sandbox) environment.
"""
import logging
import re
from datetime import timedelta

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

BOXNOW_TIMEOUT = 60
BOXNOW_ANYAPM_ID = '2'
# Locations (lockers) have their own host, per environment (manual §3.2/3.3).
BOXNOW_LOCATION_API = {
    True: 'https://locationapi-stage.boxnow.gr/api/v1',
    False: 'https://locationapi-production.boxnow.gr/api/v1',
}
# Parcel state → voucher state; anything else stays where it is.
BOXNOW_STATES = {
    'delivered': 'delivered',
    'returned': 'returned',
    'cancelled': 'cancelled',
}
COMPARTMENT_SIZES = [('1', 'Μικρό'), ('2', 'Μεσαίο'), ('3', 'Μεγάλο')]


def _intl_phone(number):
    """+30 international format (error P405 otherwise)."""
    digits = re.sub(r'[^\d+]', '', number or '')
    if digits.startswith('+'):
        return digits
    if digits.startswith('0030'):
        return '+' + digits[2:]
    if digits.startswith('30') and len(digits) == 12:
        return '+' + digits
    if len(digits) == 10:
        return '+30' + digits
    return digits


class CourierBoxnowLocker(models.Model):
    _name = 'courier.boxnow.locker'
    _description = 'Locker BOX NOW'
    _order = 'zip, name'
    _rec_names_search = ['name', 'zip', 'city', 'street', 'boxnow_id']

    boxnow_id = fields.Char(string='ID Locker', required=True, index=True)
    name = fields.Char(string='Όνομα', required=True)
    street = fields.Char(string='Διεύθυνση')
    city = fields.Char(string='Περιοχή')
    zip = fields.Char(string='Τ.Κ.', index=True)
    note = fields.Char(string='Σημείωση')
    latitude = fields.Float(string='Γεωγρ. Πλάτος', digits=(10, 7))
    longitude = fields.Float(string='Γεωγρ. Μήκος', digits=(10, 7))
    active = fields.Boolean(default=True)

    _boxnow_id_uniq = models.Constraint('unique(boxnow_id)', 'Το locker υπάρχει ήδη.')

    @api.depends('name', 'zip', 'street')
    def _compute_display_name(self):
        for locker in self:
            locker.display_name = ' — '.join(filter(None, (
                locker.zip, locker.name, locker.street)))

    @api.model
    def _boxnow_upsert(self, data):
        """Find or create a locker from a BOX NOW location payload."""
        vals = {
            'boxnow_id': str(data['id']),
            'name': data.get('name') or data.get('title') or str(data['id']),
            'street': data.get('addressLine1') or False,
            'city': data.get('addressLine2') or False,
            'zip': (data.get('postalCode') or '').replace(' ', '') or False,
            'note': data.get('note') or False,
            'latitude': float(data.get('lat') or 0.0),
            'longitude': float(data.get('lng') or 0.0),
            'active': True,
        }
        locker = self.with_context(active_test=False).search(
            [('boxnow_id', '=', vals['boxnow_id'])], limit=1)
        if locker:
            locker.write(vals)
        else:
            locker = self.create(vals)
        return locker


class CourierAccount(models.Model):
    _inherit = 'courier.account'

    courier = fields.Selection(selection_add=[('boxnow', 'BOX NOW')],
                               ondelete={'boxnow': 'cascade'})
    boxnow_client_id = fields.Char(string='Client ID', groups='base.group_system')
    boxnow_client_secret = fields.Char(string='Client Secret', groups='base.group_system')
    boxnow_api_url = fields.Char(
        string='API URL', groups='base.group_system',
        help='Η διεύθυνση API που έδωσε το BOX NOW μαζί με τα στοιχεία σύνδεσης.')
    boxnow_sandbox = fields.Boolean(
        string='Δοκιμαστικό (Sandbox)', default=True,
        help='Stage περιβάλλον του BOX NOW: τα δέματα δεν είναι πραγματικά.')
    boxnow_default_compartment_size = fields.Selection(
        COMPARTMENT_SIZES, string='Προεπιλεγμένο Μέγεθος Θυρίδας', default='1',
        help='Προτείνεται σε κάθε νέο voucher· αλλάζει ανά voucher.')
    boxnow_token = fields.Char(groups='base.group_system', copy=False)
    boxnow_token_expiry = fields.Datetime(groups='base.group_system', copy=False)

    # ── transport ────────────────────────────────────────────────────────────
    def _boxnow_base(self):
        url = (self.sudo().boxnow_api_url or '').strip().rstrip('/')
        if not url:
            raise UserError(_('Συμπληρώστε το API URL του BOX NOW στον λογαριασμό «%s».', self.name))
        if not url.startswith('http'):
            url = 'https://' + url
        return re.sub(r'/api/v\d+$', '', url)

    def _boxnow_get_token(self, force=False):
        acc = self.sudo()
        now = fields.Datetime.now()
        if not force and acc.boxnow_token and acc.boxnow_token_expiry and acc.boxnow_token_expiry > now:
            return acc.boxnow_token
        if not (acc.boxnow_client_id and acc.boxnow_client_secret):
            raise UserError(_('Συμπληρώστε Client ID και Client Secret του BOX NOW.'))
        try:
            resp = requests.post(f'{self._boxnow_base()}/api/v1/auth-sessions', timeout=BOXNOW_TIMEOUT, json={
                'grant_type': 'client_credentials',
                'client_id': acc.boxnow_client_id,
                'client_secret': acc.boxnow_client_secret,
            })
        except requests.RequestException as e:
            raise UserError(_('Το BOX NOW δεν απαντά: %s', e)) from e
        if resp.status_code in (400, 401):
            raise UserError(_('Το BOX NOW απέρριψε τα Client ID / Secret (%s).', resp.status_code))
        if resp.status_code == 403:
            raise UserError(_('Ο λογαριασμός BOX NOW είναι απενεργοποιημένος (403).'))
        if resp.status_code != 200:
            raise UserError(_('Σύνδεση BOX NOW: HTTP %s.', resp.status_code))
        data = resp.json()
        acc.write({
            'boxnow_token': data['access_token'],
            # A minute's margin so a call never leaves with a token about to lapse.
            'boxnow_token_expiry': now + timedelta(seconds=int(data.get('expires_in') or 3600) - 60),
        })
        return data['access_token']

    def _boxnow_request(self, method, path, json=None, params=None, base=None, raw=False):
        """Call the Partner API (or the location API with base=...).
        Retries once with a fresh token on 401. Credentials never logged."""
        self.ensure_one()
        url = f'{base or self._boxnow_base() + "/api/v1"}{path}'
        for attempt in (0, 1):
            headers = {'Authorization': f'Bearer {self._boxnow_get_token(force=bool(attempt))}'}
            try:
                resp = requests.request(method, url, json=json, params=params,
                                        headers=headers, timeout=BOXNOW_TIMEOUT)
            except requests.RequestException as e:
                raise UserError(_('Το BOX NOW δεν απαντά: %s', e)) from e
            if resp.status_code != 401:
                break
        _logger.info('BOX NOW %s %s → %s', method, path, resp.status_code)
        if resp.status_code >= 400:
            raise UserError(_('BOX NOW (%(path)s): %(msg)s', path=path,
                              msg=self._boxnow_error_text(resp)))
        if raw:
            return resp.content
        return resp.json() if resp.content else {}

    @staticmethod
    def _boxnow_error_text(resp):
        """«P410 Order number conflict …» when the body carries a code."""
        try:
            body = resp.json()
        except ValueError:
            return f'HTTP {resp.status_code}: {resp.text[:300]}'
        if isinstance(body, dict):
            code = body.get('code') or ''
            message = body.get('message') or body.get('title') or body.get('detail') or ''
            if code or message:
                return f'{code} {message}'.strip()
        return f'HTTP {resp.status_code}: {str(body)[:300]}'

    def _boxnow_location_base(self):
        return BOXNOW_LOCATION_API[bool(self.boxnow_sandbox)]

    # ── lockers ──────────────────────────────────────────────────────────────
    def action_boxnow_sync_lockers(self):
        self.ensure_one()
        data = self._boxnow_request('GET', '/destinations', params={'locationType': 'apm'},
                                    base=self._boxnow_location_base()).get('data') or []
        Locker = self.env['courier.boxnow.locker'].sudo()
        seen = Locker
        for row in data:
            if row.get('id') and row.get('type', 'apm') == 'apm':
                seen |= Locker._boxnow_upsert(row)
        (Locker.search([]) - seen).write({'active': False})
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {'title': _('Lockers BOX NOW'), 'type': 'success',
                       'message': _('%s lockers ενημερώθηκαν.', len(seen))},
        }

    @api.model
    def _cron_boxnow_sync_lockers(self):
        for account in self.search([('courier', '=', 'boxnow')], limit=1):
            try:
                account.action_boxnow_sync_lockers()
            except Exception:
                _logger.exception('BOX NOW locker sync failed')

    def _boxnow_nearest_locker(self, voucher):
        """Closest locker to the voucher's address (manual §3.8, v2)."""
        street = ' '.join(filter(None, (voucher.street, voucher.street_number)))
        data = self._boxnow_request('POST', '/delivery-requests:checkAddressDelivery',
                                    base=self._boxnow_base() + '/api/v2', json={
            'city': voucher.city or '',
            'street': street,
            'postalCode': (voucher.zip or '').replace(' ', ''),
            'region': 'el-GR',
            'compartmentSize': int(voucher.boxnow_compartment_size or 0),
        })
        if not data.get('id'):
            raise UserError(_('Το BOX NOW δεν βρήκε locker κοντά στη διεύθυνση.'))
        return self.env['courier.boxnow.locker'].sudo()._boxnow_upsert(data)

    # ── interface ────────────────────────────────────────────────────────────
    def _boxnow_check_ready(self, voucher):
        voucher._check_missing((
            ('boxnow_locker_id', 'Locker'), ('mobile', 'Κινητό'), ('email', 'Email'),
            ('boxnow_compartment_size', 'Μέγεθος Θυρίδας')))
        if not (self.company_id.phone and self.company_id.email):
            raise UserError(_('Συμπληρώστε τηλέφωνο και email της εταιρείας: το BOX NOW '
                              'τα ζητάει για τον αποστολέα.'))

    def _boxnow_create(self, voucher):
        cod = voucher.cod_amount > 0
        order_number = f'{voucher.reference or "V"}-{voucher.id}'
        qty = max(voucher.item_quantity, 1)
        grams = int(round(voucher.weight * 1000 / qty))
        value = voucher.cod_amount or voucher.sale_order_id.amount_total or 0.0
        data = self._boxnow_request('POST', '/delivery-requests', json={
            'orderNumber': order_number,
            'invoiceValue': f'{value:.2f}',
            'paymentMode': 'cod' if cod else 'prepaid',
            'amountToBeCollected': f'{voucher.cod_amount:.2f}' if cod else '0.00',
            'allowReturn': True,
            'origin': {
                'contactNumber': _intl_phone(self.company_id.phone),
                'contactEmail': self.company_id.email,
                'contactName': self.sender_name,
                'locationId': BOXNOW_ANYAPM_ID,
            },
            'destination': {
                'contactNumber': _intl_phone(voucher.mobile),
                'contactEmail': voucher.email,
                'contactName': voucher.recipient_name,
                'locationId': voucher.boxnow_locker_id.boxnow_id,
            },
            'items': [{
                'id': str(i + 1),
                'name': voucher.reference or 'parcel',
                'value': '0.00',
                'compartmentSize': int(voucher.boxnow_compartment_size),
                'weight': grams,
            } for i in range(qty)],
        })
        parcels = [str(p['id']) for p in data.get('parcels') or [] if p.get('id')]
        if not parcels:
            raise UserError(_('Το BOX NOW δεν επέστρεψε αριθμό δέματος.'))
        voucher.write({
            'boxnow_order_number': order_number,
            'boxnow_request_id': str(data.get('id') or ''),
            'boxnow_parcel_ids': ','.join(parcels),
        })
        return parcels[0]

    def _boxnow_print(self, vouchers):
        voucher = vouchers[:1]
        parcels = (voucher.boxnow_parcel_ids or voucher.name).split(',')
        # A4 first (the business prints on A4); the manual documents only A6
        # for labels:search, so fall back to BOX NOW's own label size.
        try:
            pdf = self._boxnow_request('POST', '/labels:search', raw=True, json={
                'parcelIds': parcels, 'paperSize': 'A4', 'perPage': 4})
            if pdf[:4] == b'%PDF':
                return pdf
        except UserError as e:
            _logger.info('BOX NOW A4 labels refused, falling back: %s', e)
        if len(parcels) > 1 and voucher.boxnow_order_number:
            return self._boxnow_request(
                'GET', f'/delivery-requests/{voucher.boxnow_order_number}/label.pdf', raw=True)
        return self._boxnow_request('GET', f'/parcels/{parcels[0]}/label.pdf', raw=True)

    def _boxnow_cancel(self, voucher):
        for parcel in (voucher.boxnow_parcel_ids or voucher.name).split(','):
            self._boxnow_request('POST', f'/parcels/{parcel}:cancel')

    def _boxnow_track(self, voucher):
        data = self._boxnow_request('GET', '/parcels', params={'parcelId': voucher.name}).get('data') or []
        if not data:
            return False, voucher.tracking_status or ''
        parcel = data[0]
        events = parcel.get('events') or []
        last = events[-1] if events else {}
        text = ' — '.join(filter(None, (
            parcel.get('state'), last.get('locationDisplayName'), (last.get('createTime') or '')[:16])))
        return BOXNOW_STATES.get(parcel.get('state'), False), text

    def _boxnow_test_connection(self):
        self._boxnow_get_token(force=True)
        data = self._boxnow_request('GET', '/destinations', params={'locationType': 'apm'},
                                    base=self._boxnow_location_base()).get('data') or []
        return _('Client ID / Secret: OK (%(env)s). Διαθέσιμα lockers: %(count)s.',
                 env=_('Sandbox') if self.boxnow_sandbox else _('Παραγωγή'), count=len(data))


class CourierVoucher(models.Model):
    _inherit = 'courier.voucher'

    boxnow_locker_id = fields.Many2one('courier.boxnow.locker', string='Locker',
                                       domain="[('active', '=', True)]")
    boxnow_locker_note = fields.Char(related='boxnow_locker_id.note', string='Σημείωση Locker')
    boxnow_compartment_size = fields.Selection(
        COMPARTMENT_SIZES, string='Μέγεθος Θυρίδας',
        default=lambda self: self._default_account().boxnow_default_compartment_size or '1')
    boxnow_order_number = fields.Char(string='Αρ. Παραγγελίας BOX NOW', readonly=True, copy=False)
    boxnow_request_id = fields.Char(string='Αίτημα BOX NOW', readonly=True, copy=False)
    boxnow_parcel_ids = fields.Char(string='Δέματα BOX NOW', readonly=True, copy=False)

    def _boxnow_suggest_locker(self):
        """Quietly propose the closest locker; a failed lookup leaves the
        field for the user to pick."""
        if self.courier != 'boxnow' or self.boxnow_locker_id or not self.zip:
            return
        try:
            self.boxnow_locker_id = self.account_id._boxnow_nearest_locker(self)
        except UserError as e:
            _logger.info('BOX NOW nearest locker not found: %s', e)

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        super()._onchange_partner_id()
        self.boxnow_locker_id = False
        self._boxnow_suggest_locker()

    @api.onchange('account_id')
    def _onchange_account_id(self):
        super()._onchange_account_id()
        if self.courier == 'boxnow':
            self.boxnow_compartment_size = self.account_id.boxnow_default_compartment_size or '1'
        self._boxnow_suggest_locker()

    def action_boxnow_nearest_locker(self):
        self.ensure_one()
        if not self.zip:
            raise UserError(_('Συμπληρώστε τον Τ.Κ. του παραλήπτη.'))
        self.boxnow_locker_id = self.account_id._boxnow_nearest_locker(self)
