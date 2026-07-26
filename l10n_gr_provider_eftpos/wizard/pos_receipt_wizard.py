# -*- coding: utf-8 -*-
"""8.4 / 8.5 — Απόδειξη Είσπραξης / Επιστροφής POS.

Card money taken (or given back) when no sales document is issued at that
moment: a deposit, an advance, or settling an older invoice at the counter.
Α.1155 requires these documents to carry exactly ONE payment method of type 7
with its provider signature, so the wizard builds the document with that single
payment line already in place and then hands over to the normal EFT dialog
(signature → charge → transaction id → transmit).
"""
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class L10nGrProvPosReceiptWizard(models.TransientModel):
    _name = 'l10n.gr.prov.pos.receipt.wizard'
    _description = 'Είσπραξη / Επιστροφή με Κάρτα (8.4 / 8.5)'

    doc_type = fields.Selection(
        selection=[
            ('8.4', '8.4 - Απόδειξη Είσπραξης POS'),
            ('8.5', '8.5 - Απόδειξη Επιστροφής POS'),
        ],
        string='Τύπος Παραστατικού', required=True, default='8.4')
    partner_id = fields.Many2one(
        'res.partner', string='Πελάτης', required=True,
        help='Δεν διαβιβάζεται στην ΑΑΔΕ (τα 8.4/8.5 δεν φέρουν '
             'αντισυμβαλλόμενο) — χρησιμεύει για τη λογιστική εγγραφή.')
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    amount = fields.Monetary(
        string='Ποσό', required=True, currency_field='currency_id')
    reason = fields.Char(
        string='Αιτιολογία', required=True, default='Είσπραξη μέσω POS')
    terminal_id = fields.Many2one(
        'l10n.gr.prov.eft.terminal', string='Τερματικό', required=True,
        domain="[('company_id', '=', company_id)]")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if 'terminal_id' in fields_list and not res.get('terminal_id'):
            terminal = self.env['l10n.gr.prov.eft.terminal'].search(
                [('company_id', '=', self.env.company.id)], limit=1)
            res['terminal_id'] = terminal.id
        return res

    def action_create_and_charge(self):
        """Build the 8.4/8.5, post it, and open the card-payment dialog."""
        self.ensure_one()
        if self.amount <= 0:
            raise UserError(_('Το ποσό πρέπει να είναι θετικό.'))
        journal = self.env['account.journal'].search([
            ('company_id', '=', self.company_id.id),
            ('type', '=', 'sale'),
            ('l10n_gr_edi_inv_type_default', '=', self.doc_type),
        ], limit=1)
        if not journal:
            raise UserError(_(
                'Δεν βρέθηκε ημερολόγιο πωλήσεων με Προεπιλογή Τύπου myDATA %s.',
                self.doc_type))
        move = self.env['account.move'].create({
            'move_type': 'out_invoice' if self.doc_type == '8.4' else 'out_refund',
            'journal_id': journal.id,
            'partner_id': self.partner_id.id,
            'invoice_date': fields.Date.context_today(self),
            'invoice_line_ids': [(0, 0, {
                'name': self.reason,
                'quantity': 1,
                'price_unit': self.amount,
                'tax_ids': [(5, 0, 0)],
                # 8.4/8.5 take the informational category only, no E3 code
                'l10n_gr_prov_cls_category': 'category1_95',
            })],
            # The single type-7 payment Α.1155 demands. Creating it up front
            # also stops _post from seeding a default payment line.
            'l10n_gr_prov_payment_ids': [(0, 0, {
                'payment_type': '7',
                'amount': self.amount,
            })],
        })
        move.action_post()
        payment = self.env['l10n.gr.prov.eft.payment'].create({
            'move_id': move.id,
            'terminal_id': self.terminal_id.id,
            'amount': self.amount,
        })
        return payment._reopen()
