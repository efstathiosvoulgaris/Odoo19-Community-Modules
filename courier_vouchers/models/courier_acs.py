# -*- coding: utf-8 -*-
"""ACS Web Services — spec: Courier API/ACS/english-acs-web-services-2025.md.

One URL, always POST JSON {"ACSAlias", "ACSInputParameters"}, header
ACSApiKey. HTTP 200 even on business errors: ACSExecution_HasError and the
per-row Error_Message carry them. There is no test server — a voucher can be
deleted only until it is in a pickup list.
"""
import base64
import logging

import requests

from odoo import _, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

ACS_URL = 'https://webservices.acscourier.net/ACSRestServices/api/ACSAutoRest'
ACS_TIMEOUT = 60
# Tracking summary shipment_status → voucher state.
ACS_DELIVERED = {4}
ACS_RETURNED = {6, 7}


class CourierAccount(models.Model):
    _inherit = 'courier.account'

    courier = fields.Selection(selection_add=[('acs', 'ACS')], ondelete={'acs': 'cascade'})
    acs_api_key = fields.Char(string='ACS API Key', groups='base.group_system')
    acs_company_id = fields.Char(string='Company ID', groups='base.group_system')
    acs_company_password = fields.Char(string='Company Password', groups='base.group_system')
    acs_user_id = fields.Char(string='User ID', groups='base.group_system')
    acs_user_password = fields.Char(string='User Password', groups='base.group_system')
    acs_billing_code = fields.Char(string='Κωδικός Χρέωσης (Billing Code)', groups='base.group_system')

    # ── transport ────────────────────────────────────────────────────────────
    def _acs_call(self, alias, params):
        """POST one ACS alias; return ACSOutputResponce. Credentials are
        added here and never logged."""
        self.ensure_one()
        acc = self.sudo()
        if not (acc.acs_api_key and acc.acs_company_id and acc.acs_user_id):
            raise UserError(_('Συμπληρώστε τα στοιχεία σύνδεσης ACS στον λογαριασμό «%s».', self.name))
        body = {'ACSAlias': alias, 'ACSInputParameters': {
            'Company_ID': acc.acs_company_id,
            'Company_Password': acc.acs_company_password,
            'User_ID': acc.acs_user_id,
            'User_Password': acc.acs_user_password,
            'Language': None,
            **params,
        }}
        try:
            resp = requests.post(ACS_URL, json=body, timeout=ACS_TIMEOUT,
                                 headers={'ACSApiKey': acc.acs_api_key})
        except requests.RequestException as e:
            raise UserError(_('Η ACS δεν απαντά: %s', e)) from e
        if resp.status_code == 403:
            raise UserError(_('Η ACS απέρριψε το API key (403).'))
        if resp.status_code == 406:
            raise UserError(_('Πάρα πολλές κλήσεις προς την ACS — ξαναδοκιμάστε σε λίγο.'))
        if resp.status_code != 200:
            raise UserError(_('Η ACS απάντησε HTTP %s.', resp.status_code))
        data = resp.json()
        _logger.info('ACS %s → HasError=%s', alias, data.get('ACSExecution_HasError'))
        if data.get('ACSExecution_HasError'):
            raise UserError(_('ACS (%(alias)s): %(msg)s', alias=alias,
                              msg=data.get('ACSExecutionErrorMessage') or '?'))
        # The spec spells it both ways; the demo responses use «Responce».
        return data.get('ACSOutputResponce') or data.get('ACSOutputResponse') or {}

    @staticmethod
    def _acs_value(out):
        """First ACSValueOutput row, raising its Error_Message if any."""
        rows = out.get('ACSValueOutput') or [{}]
        row = rows[0] or {}
        err = row.get('Error_Message') or row.get('error_message')
        if err:
            raise UserError(_('ACS: %s', err))
        return row

    @staticmethod
    def _acs_table(out):
        return (out.get('ACSTableOutput') or {}).get('Table_Data') or []

    @staticmethod
    def _acs_pdf(out):
        """The print aliases return the PDF in ACSObjectOutput as
        {voucher: bytes}. .NET serialises byte[] as base64; accept a list of
        ints too. To be confirmed on the first real print."""
        obj = out.get('ACSObjectOutput')
        values = []
        if isinstance(obj, dict):
            values = list(obj.values())
        elif isinstance(obj, list):
            for item in obj:
                values.extend(item.values() if isinstance(item, dict) else [item])
        elif obj:
            values = [obj]
        for value in values:
            if isinstance(value, str) and value.startswith('JVBER'):
                return base64.b64decode(value)
            if isinstance(value, list) and value and isinstance(value[0], int):
                return bytes(value)
        raise UserError(_('Η ACS δεν επέστρεψε PDF (κλειδιά: %s).', ', '.join(out.keys())))

    # ── interface ────────────────────────────────────────────────────────────
    def _acs_check_ready(self, voucher):
        voucher._check_missing((
            ('street', 'Οδός'), ('zip', 'Τ.Κ.'), ('city', 'Περιοχή'), ('mobile', 'Κινητό')))

    def _acs_create(self, voucher):
        acc = self.sudo()
        cod = voucher.cod_amount > 0
        out = self._acs_call('ACS_Create_Voucher', {
            'Pickup_Date': voucher.pickup_date.isoformat(),
            'Sender': self.sender_name,
            'Recipient_Name': voucher.recipient_name,
            'Recipient_Address': voucher.street,
            'Recipient_Address_Number': voucher.street_number or None,
            'Recipient_Zipcode': (voucher.zip or '').replace(' ', ''),
            'Recipient_Region': voucher.city,
            'Recipient_Phone': voucher.phone or None,
            'Recipient_Cell_Phone': voucher.mobile,
            'Recipient_Floor': None,
            'Recipient_Company_Name': voucher.recipient_company or None,
            'Recipient_Country': voucher.country_code or 'GR',
            'Acs_Station_Destination': None,
            'Acs_Station_Branch_Destination': None,
            'Billing_Code': acc.acs_billing_code,
            'Charge_Type': 2 if voucher.charge_type == 'sender' else 4,
            'Cost_Center_Code': None,
            'Item_Quantity': voucher.item_quantity,
            'Weight': round(voucher.weight, 2),
            'Dimension_X_In_Cm': None,
            'Dimension_Y_in_Cm': None,
            'Dimension_Z_in_Cm': None,
            'Cod_Ammount': round(voucher.cod_amount, 2) if cod else None,
            'Cod_Payment_Way': 0 if cod else None,
            'Acs_Delivery_Products': 'COD' if cod else None,
            'Insurance_Ammount': None,
            'Delivery_Notes': voucher.notes or None,
            'Appointment_Until_Time': None,
            'Recipient_Email': voucher.email or None,
            'Reference_Key1': voucher.reference or None,
            'Reference_Key2': None,
            'With_Return_Voucher': None,
            'Content_Type_ID': None,
        })
        number = str(self._acs_value(out).get('Voucher_No') or '').strip()
        if not number:
            raise UserError(_('Η ACS δεν επέστρεψε αριθμό voucher.'))
        return number

    def _acs_print(self, vouchers):
        out = self._acs_call('ACS_Print_Voucher', {
            'Voucher_No': ','.join(vouchers.mapped('name')),
            'Print_Type': 2,       # A4 laser, 3 labels per page
            'Start_Position': 1,
        })
        return self._acs_pdf(out)

    def _acs_cancel(self, voucher):
        out = self._acs_call('ACS_Delete_Voucher', {'Voucher_No': voucher.name})
        self._acs_value(out)

    def _acs_close_day(self, date, vouchers):
        out = self._acs_call('ACS_Issue_Pickup_List', {
            'Pickup_Date': date.isoformat(), 'MyData': None})
        row = (out.get('ACSValueOutput') or [{}])[0] or {}
        if row.get('Unprinted_Found'):
            unprinted = ', '.join(str(r.get('Unprinted_Vouchers', '')) for r in self._acs_table(out))
            raise UserError(_('Η ACS βρήκε ατύπωτα vouchers: %s. Τυπώστε ή ακυρώστε τα '
                              'και ξαναδοκιμάστε.', unprinted))
        list_no = self._acs_value(out).get('PickupList_No')
        if not list_no:
            raise UserError(_('Η ACS δεν επέστρεψε αριθμό λίστας παραλαβής.'))
        pdf_out = self._acs_call('ACS_Print_Pickup_List', {
            'Mass_Number': list_no, 'Pickup_Date': date.isoformat()})
        # ACS lists only the given day's vouchers.
        return (str(list_no), self._acs_pdf(pdf_out),
                vouchers.filtered(lambda v: v.pickup_date == date))

    def _acs_track(self, voucher):
        out = self._acs_call('ACS_Trackingsummary', {'Voucher_No': voucher.name})
        rows = self._acs_table(out)
        if not rows:
            return False, voucher.tracking_status or ''
        row = rows[0]
        status = row.get('shipment_status')
        text = row.get('delivery_info') or ''
        if row.get('returned_flag') == 1 or status in ACS_RETURNED:
            return 'returned', text
        if status in ACS_DELIVERED:
            return 'delivered', text
        return False, text

    def _acs_test_connection(self):
        """Two read-only calls. The zip lookup proves the API key and the
        Company/User credentials; the price calculation also proves the
        Billing Code. Neither creates anything at ACS."""
        zip_code = (self.company_id.zip or '').replace(' ', '')
        if not zip_code:
            raise UserError(_('Συμπληρώστε τον Τ.Κ. της εταιρείας: ο έλεγχος '
                              'βρίσκει το κατάστημα ACS της περιοχής σας.'))
        out = self._acs_call('ACS_Area_Find_By_Zip_Code', {
            'Zip_Code': zip_code, 'Show_Only_Inaccessible_Areas': 0, 'Country': 'GR'})
        self._acs_value(out)
        areas = self._acs_table(out)
        if not areas:
            raise UserError(_('Τα στοιχεία σύνδεσης δουλεύουν, αλλά η ACS δεν '
                              'βρήκε περιοχή για τον Τ.Κ. %s.', zip_code))
        station = areas[0].get('Station_ID')
        try:
            price = self._acs_value(self._acs_call('ACS_Price_Calculation', {
                'Billing_Code': self.sudo().acs_billing_code,
                'Billing_Category': 2,
                'Acs_Station_Origin': station,
                'Acs_Station_Destination': station,
                'Weight': '0,5',
                'Pickup_Date': fields.Date.context_today(self).isoformat(),
                'Acs_Delivery_Products': None,
                'Charge_Type': 2,
                'Delivery_Zone': None,
                'Insurance_Ammount': None,
                'Dimension_X_In_Cm': None,
                'Dimension_Y_In_Cm': None,
                'Dimension_Z_In_Cm': None,
            }))
        except UserError as e:
            raise UserError(_('Το API key και τα στοιχεία χρήστη δουλεύουν '
                              '(κατάστημα %(station)s), αλλά ο Κωδικός Χρέωσης '
                              'απορρίφθηκε: %(error)s', station=station, error=e.args[0])) from e
        return _('API key, στοιχεία χρήστη και Κωδικός Χρέωσης: OK. Κατάστημα '
                 'περιοχής: %(station)s (%(area)s). Ενδεικτική τιμή 0,5 kg εντός '
                 'περιοχής: %(total)s € + ΦΠΑ %(vat)s €.',
                 station=station, area=areas[0].get('Area') or '',
                 total=price.get('Total_Ammount'), vat=price.get('Total_Vat_Ammount'))

    def _acs_tracking_url(self, number):
        return f'https://www.acscourier.net/el/track-and-trace?p_p_id=ACSCustomersAreaTrackTrace&generalCode={number}'
