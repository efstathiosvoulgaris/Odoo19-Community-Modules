# -*- coding: utf-8 -*-
import base64

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class CourierAccount(models.Model):
    _name = 'courier.account'
    _description = 'Λογαριασμός Courier'

    name = fields.Char(string='Όνομα', required=True)
    courier = fields.Selection([], string='Courier', required=True)
    company_id = fields.Many2one(
        'res.company', string='Εταιρεία', required=True,
        default=lambda self: self.env.company)
    active = fields.Boolean(default=True)
    sender_name = fields.Char(
        string='Αποστολέας', required=True,
        help='Το όνομα αποστολέα που τυπώνεται στο voucher.')
    default_weight = fields.Float(string='Προεπιλεγμένο Βάρος (kg)', default=0.5)
    default_charge_type = fields.Selection(
        [('sender', 'Χρέωση Αποστολέα'), ('recipient', 'Χρέωση Παραλήπτη')],
        string='Προεπιλεγμένη Χρέωση Μεταφορικών', required=True, default='sender',
        help='Προτείνεται σε κάθε νέο voucher· αλλάζει ανά voucher.')
    pickup_list_attachment_id = fields.Many2one(
        'ir.attachment', string='Τελευταία Λίστα Παραλαβής', readonly=True, copy=False)
    courier_has_pickup_list = fields.Boolean(compute='_compute_courier_has_pickup_list')

    @api.depends('courier')
    def _compute_courier_has_pickup_list(self):
        """ACS needs a daily pickup list; BOX NOW collects without one."""
        for account in self:
            account.courier_has_pickup_list = bool(
                account.courier and hasattr(account, f'_{account.courier}_close_day'))

    # ── Dispatch: each courier file implements _<x>_create, _<x>_print, … ──
    def _courier_impl(self, method):
        self.ensure_one()
        impl = getattr(self, f'_{self.courier}_{method}', None)
        if not impl:
            raise UserError(_('Η λειτουργία «%(method)s» δεν υποστηρίζεται για '
                              'τον courier %(courier)s.', method=method, courier=self.courier))
        return impl

    def _courier_create(self, voucher):
        return self._courier_impl('create')(voucher)

    def _courier_print(self, vouchers):
        return self._courier_impl('print')(vouchers)

    def _courier_cancel(self, voucher):
        return self._courier_impl('cancel')(voucher)

    def _courier_close_day(self, date, vouchers):
        """→ (reference, pdf bytes or None, the vouchers actually closed)."""
        return self._courier_impl('close_day')(date, vouchers)

    def _courier_track(self, voucher):
        return self._courier_impl('track')(voucher)

    def action_test_connection(self):
        """Έλεγχος Σύνδεσης: read-only calls only — nothing is created at
        the courier. Raises with the courier's message on failure."""
        self.ensure_one()
        message = self._courier_impl('test_connection')()
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {'title': _('Η σύνδεση λειτουργεί'), 'message': message,
                       'type': 'success', 'sticky': True},
        }

    def action_close_day(self):
        """Λίστα Παραλαβής Ημέρας: finalise today's printed vouchers.

        After this the vouchers can no longer be cancelled or reprinted —
        ACS refuses both. Never run it while testing.
        """
        self.ensure_one()
        today = fields.Date.context_today(self)
        vouchers = self.env['courier.voucher'].search([
            ('account_id', '=', self.id), ('state', '=', 'printed'),
            ('pickup_date', '<=', today)])
        if not vouchers:
            raise UserError(_('Δεν υπάρχουν τυπωμένα vouchers προς οριστικοποίηση.'))
        list_no, pdf, closed = self._courier_close_day(today, vouchers)
        closed.write({'state': 'manifested', 'pickup_list_ref': list_no})
        if not pdf:
            # Geniki finalises without a document to print.
            return {
                'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'title': _('Οριστικοποίηση'), 'type': 'success', 'next': {
                               'type': 'ir.actions.client', 'tag': 'soft_reload'},
                           'message': _('%s vouchers οριστικοποιήθηκαν.', len(closed))},
            }
        attachment = self.env['ir.attachment'].create({
            'name': f'Λίστα Παραλαβής {list_no}.pdf',
            'datas': base64.b64encode(pdf),
            'mimetype': 'application/pdf',
            'res_model': self._name, 'res_id': self.id,
        })
        self.pickup_list_attachment_id = attachment
        return {'type': 'ir.actions.act_url',
                'url': f'/web/content/{attachment.id}', 'target': 'new'}
