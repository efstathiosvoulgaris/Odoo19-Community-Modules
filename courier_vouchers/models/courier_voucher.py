# -*- coding: utf-8 -*-
import base64
import logging
import re
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Same rule as l10n_gr_provider_base res_partner (copied to avoid the
# dependency): trailing house number, anchored at the end.
STREET_NUMBER_RE = re.compile(r'^(.*?)[\s,]+(\d[\w\-/]*)$', re.UNICODE)

STATES = [
    ('draft', 'Πρόχειρο'),
    ('created', 'Δημιουργήθηκε'),
    ('printed', 'Τυπώθηκε'),
    ('manifested', 'Σε Λίστα Παραλαβής'),
    ('cancelled', 'Ακυρώθηκε'),
    ('delivered', 'Παραδόθηκε'),
    ('returned', 'Επιστράφηκε'),
]


def _split_street(partner):
    street = (partner.street or '').strip()
    explicit = (getattr(partner, 'arithmos_odou', '') or partner.street2 or '').strip()
    match = STREET_NUMBER_RE.match(street)
    trailing = match.group(2) if match else ''
    number = explicit or trailing
    if trailing and number == trailing:
        street = match.group(1).strip()
    return street, number


class CourierVoucher(models.Model):
    _name = 'courier.voucher'
    _description = 'Voucher Courier'
    _inherit = ['mail.thread']
    _order = 'id desc'

    name = fields.Char(string='Αριθμός Voucher', readonly=True, copy=False, tracking=True)
    account_id = fields.Many2one(
        'courier.account', string='Λογαριασμός', required=True,
        default=lambda self: self._default_account())
    courier = fields.Selection(related='account_id.courier')
    courier_has_pickup_list = fields.Boolean(related='account_id.courier_has_pickup_list')
    company_id = fields.Many2one(related='account_id.company_id', store=True)
    picking_id = fields.Many2one('stock.picking', string='Παράδοση', index=True, copy=False)
    sale_order_id = fields.Many2one(related='picking_id.sale_id', store=True, string='Παραγγελία')
    partner_id = fields.Many2one('res.partner', string='Παραλήπτης', required=True)

    recipient_name = fields.Char(string='Όνομα Παραλήπτη', required=True)
    recipient_company = fields.Char(string='Επωνυμία')
    street = fields.Char(string='Οδός')
    street_number = fields.Char(string='Αριθμός')
    zip = fields.Char(string='Τ.Κ.')
    city = fields.Char(string='Περιοχή')
    phone = fields.Char(string='Τηλέφωνο')
    mobile = fields.Char(string='Κινητό')
    email = fields.Char(string='Email')
    country_code = fields.Char(string='Χώρα', default='GR', readonly=True)

    weight = fields.Float(string='Βάρος (kg)', default=0.5)
    item_quantity = fields.Integer(string='Τεμάχια', default=1)
    charge_type = fields.Selection(
        [('sender', 'Χρέωση Αποστολέα'), ('recipient', 'Χρέωση Παραλήπτη')],
        string='Χρέωση Μεταφορικών', required=True,
        default=lambda self: self._default_account().default_charge_type or 'sender')
    cod_amount = fields.Monetary(string='Αντικαταβολή', currency_field='currency_id')
    currency_id = fields.Many2one(related='company_id.currency_id')
    notes = fields.Char(string='Σημειώσεις Παράδοσης')
    reference = fields.Char(string='Αναφορά')
    pickup_date = fields.Date(string='Ημ. Παραλαβής', required=True,
                              default=lambda self: self._pickup_date_default())

    state = fields.Selection(STATES, string='Κατάσταση', default='draft',
                             required=True, readonly=True, copy=False, tracking=True)
    label_attachment_id = fields.Many2one('ir.attachment', string='Ετικέτα', readonly=True, copy=False)
    pickup_list_ref = fields.Char(string='Λίστα Παραλαβής', readonly=True, copy=False)
    tracking_status = fields.Char(string='Τελευταία Κατάσταση', readonly=True, copy=False)
    tracking_url = fields.Char(string='Σύνδεσμος Παρακολούθησης', compute='_compute_tracking_url')

    @api.model
    def _default_account(self):
        return (self.env.company.courier_default_account_id
                or self.env['courier.account'].search(
                    [('company_id', '=', self.env.company.id)], limit=1))

    @api.model
    def _pickup_date_default(self):
        day = fields.Date.context_today(self)
        if day.weekday() == 6:  # Sunday — ACS refuses it
            day += timedelta(days=1)
        return day

    @api.depends('name', 'courier')
    def _compute_tracking_url(self):
        for voucher in self:
            impl = getattr(voucher.account_id, f'_{voucher.courier}_tracking_url', None)
            voucher.tracking_url = impl(voucher.name) if impl and voucher.name else False

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        p = self.partner_id
        if not p:
            return
        street, number = _split_street(p)
        self.update({
            'recipient_name': p.name,
            'recipient_company': p.parent_id.name if p.parent_id else False,
            'street': street, 'street_number': number,
            'zip': p.zip, 'city': p.city,
            'phone': p.phone, 'mobile': getattr(p, 'mobile', False) or p.phone,
            'email': p.email,
        })

    @api.onchange('account_id')
    def _onchange_account_id(self):
        if self.account_id:
            self.charge_type = self.account_id.default_charge_type
            if not self.weight:
                self.weight = self.account_id.default_weight

    def write(self, vals):
        res = super().write(vals)
        if 'state' in vals:
            # The delivery's standard tracking field follows the live voucher.
            for voucher in self.filtered('picking_id'):
                picking = voucher.picking_id
                if voucher.state in ('created', 'printed', 'manifested'):
                    picking.carrier_tracking_ref = voucher.name
                elif voucher.state == 'cancelled' and picking.carrier_tracking_ref == voucher.name:
                    picking.carrier_tracking_ref = False
        return res

    def _check_missing(self, fields_labels):
        """Raise listing the empty fields among (field, label) pairs."""
        missing = [label for field, label in fields_labels if not self[field]]
        if missing:
            raise UserError(_('Λείπουν στοιχεία παραλήπτη: %s', ', '.join(missing)))

    def _check_ready(self):
        """Common checks, then the courier's own (_<courier>_check_ready):
        ACS needs a street address, BOX NOW a locker and an email."""
        self.ensure_one()
        own = getattr(self.account_id, f'_{self.courier}_check_ready', None)
        if own:
            own(self)
        if self.weight < 0.5:
            raise UserError(_('Το ελάχιστο βάρος είναι 0,5 kg.'))
        if self.item_quantity < 1:
            raise UserError(_('Τα τεμάχια πρέπει να είναι τουλάχιστον 1.'))

    def action_send(self):
        """Create at the courier, then print in the same click: ACS refuses
        the pickup list while any voucher is unprinted."""
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_('Το voucher έχει ήδη σταλεί.'))
        self._check_ready()
        number = self.account_id._courier_create(self)
        self.write({'name': number, 'state': 'created'})
        self.message_post(body=_('Δημιουργήθηκε voucher %s.', number))
        # The voucher exists at the courier now: keep it even if printing fails.
        self.env.cr.commit()
        return self.action_print()

    def action_print(self):
        self.ensure_one()
        if self.state not in ('created', 'printed'):
            raise UserError(_('Εκτύπωση γίνεται μόνο πριν τη λίστα παραλαβής.'))
        pdf = self.account_id._courier_print(self)
        if self.label_attachment_id:
            self.label_attachment_id.datas = base64.b64encode(pdf)
        else:
            self.label_attachment_id = self.env['ir.attachment'].create({
                'name': f'Voucher {self.name}.pdf',
                'datas': base64.b64encode(pdf),
                'mimetype': 'application/pdf',
                'res_model': self._name, 'res_id': self.id,
            })
        self.state = 'printed'
        return {'type': 'ir.actions.act_url',
                'url': f'/web/content/{self.label_attachment_id.id}', 'target': 'new'}

    def action_cancel(self):
        self.ensure_one()
        if self.state == 'draft':
            self.state = 'cancelled'
            return
        if self.state not in ('created', 'printed'):
            raise UserError(_('Το voucher είναι σε λίστα παραλαβής: ακύρωση μόνο '
                              'από τον courier, κατόπιν αιτήματος.'))
        self.account_id._courier_cancel(self)
        self.state = 'cancelled'
        self.message_post(body=_('Το voucher %s ακυρώθηκε στον courier.', self.name))

    def _is_trackable(self):
        """In the courier's hands: after the pickup list, or — for a courier
        without one (BOX NOW) — once printed."""
        self.ensure_one()
        return (self.state == 'manifested'
                or (self.state == 'printed' and not self.courier_has_pickup_list))

    def action_refresh_status(self):
        for voucher in self.filtered(lambda v: v._is_trackable()):
            new_state, text = voucher.account_id._courier_track(voucher)
            vals = {'tracking_status': text}
            if new_state:
                vals['state'] = new_state
            voucher.write(vals)

    @api.model
    def _cron_track(self):
        candidates = self.search([('state', 'in', ('printed', 'manifested'))])
        for voucher in candidates.filtered(lambda v: v._is_trackable()):
            try:
                with self.env.cr.savepoint():
                    voucher.action_refresh_status()
            except Exception:
                _logger.exception('Courier tracking failed for %s', voucher.name)
