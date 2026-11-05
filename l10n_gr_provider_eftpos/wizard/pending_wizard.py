from datetime import datetime, timezone

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..models.eft_driver import RESPONSE_CODES, MegEftPosDriver, as_user_error


class EftPendingWizard(models.TransientModel):
    """«Τακτοποίηση» (Mellon scenarios 17/19): every payment Odoo still holds
    open on this terminal, asked of the terminal one by one by
    ecrReferenceNumber. Never the whole pending list: ILYDA (2026-11-05) —
    the Mellon certification terminal is shared by every ERP, so a bulk fetch
    returns other ERPs' transactions."""
    _name = 'l10n.gr.prov.eft.pending.wizard'
    _description = 'Εκκρεμείς συναλλαγές τερματικού'

    terminal_id = fields.Many2one('l10n.gr.prov.eft.terminal', required=True, readonly=True)
    line_ids = fields.One2many('l10n.gr.prov.eft.pending.line', 'wizard_id', readonly=True)
    to_apply_count = fields.Integer(compute='_compute_to_apply_count')
    result = fields.Text(readonly=True)

    @api.depends('line_ids.match_state')
    def _compute_to_apply_count(self):
        for wiz in self:
            wiz.to_apply_count = len(wiz.line_ids.filtered(lambda l: l.match_state == 'to_apply'))

    @api.model
    def _open_for(self, terminal, result=False):
        payments = self.env['l10n.gr.prov.eft.payment'].search([
            ('terminal_id', '=', terminal.id), ('ecr_reference', '!=', False),
            '|', ('state', '=', 'charging'),
            '&', ('state', '=', 'signed'), ('preloaded_at', '!=', False),
        ])
        driver = MegEftPosDriver(terminal.company_id, terminal)
        device = terminal._l10n_gr_prov_pos_device()
        lines = []
        for payment in payments:
            with as_user_error():
                found = driver.pending_by_ecr(device, payment.ecr_reference)
            if not found:
                lines.append((0, 0, {'ecr_reference': payment.ecr_reference,
                                     'amount': payment.amount,
                                     'payment_id': payment.id,
                                     'match_state': 'not_found'}))
            for t in found:
                stamp = t.get('transactonTimestamp') or t.get('transactionTimestamp')
                code = t.get('responseCode')
                lines.append((0, 0, {
                    'ecr_reference': t.get('ecrReferenceNumber') or payment.ecr_reference,
                    'nsp_reference': t.get('nspReferenceNumber') or '',
                    'amount': t.get('paidAmount') or t.get('originalAmount') or 0.0,
                    'tip_amount': t.get('tipAmount') or t.get('tpAmount') or 0.0,
                    'response_code': code if code in dict(RESPONSE_CODES) else 'UNKNOWN',
                    'description': t.get('nspResponseCodeDescription') or t.get('nspResponseCodeDescripton'),
                    'txn_time': datetime.fromtimestamp(int(stamp), timezone.utc).replace(tzinfo=None)
                                if stamp else False,
                    'card_number': t.get('cardNumber'),
                    'payment_id': payment.id,
                    'match_state': 'to_apply',
                }))
        wiz = self.create({'terminal_id': terminal.id, 'line_ids': lines, 'result': result})
        return {
            'type': 'ir.actions.act_window',
            'name': _('Εκκρεμείς συναλλαγές — %s', terminal.display_name),
            'res_model': self._name,
            'res_id': wiz.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_apply(self):
        """Complete every Odoo payment the terminal reports, one by one: one
        that fails says why and does not stop the others."""
        self.ensure_one()
        done, problems = [], []
        for line in self.line_ids.filtered(lambda l: l.match_state == 'to_apply'):
            payment = line.payment_id
            try:
                payment.action_recover_pending()
                done.append(payment.display_name)
            except UserError as e:
                problems.append(f'{payment.display_name}: {e.args[0]}')
        result = '\n'.join(
            ([_('Καταχωρήθηκαν: %s', ', '.join(done))] if done else [])
            + ([_('Δεν καταχωρήθηκαν:')] + problems if problems else [])) or _('Τίποτα για καταχώριση.')
        return self._open_for(self.terminal_id, result)

    def action_refresh(self):
        self.ensure_one()
        return self._open_for(self.terminal_id)


class EftPendingLine(models.TransientModel):
    _name = 'l10n.gr.prov.eft.pending.line'
    _description = 'Εκκρεμής συναλλαγή τερματικού'

    wizard_id = fields.Many2one('l10n.gr.prov.eft.pending.wizard', required=True, ondelete='cascade')
    txn_time = fields.Datetime('Ώρα')
    amount = fields.Float('Ποσό', digits=(16, 2))
    tip_amount = fields.Float('Φιλοδώρημα', digits=(16, 2))
    response_code = fields.Selection(RESPONSE_CODES, 'Αποτέλεσμα')
    description = fields.Char('Απάντηση NSP')
    card_number = fields.Char('Κάρτα')
    ecr_reference = fields.Char('ECR ref')
    nsp_reference = fields.Char('NSP ref')
    payment_id = fields.Many2one('l10n.gr.prov.eft.payment', 'Πληρωμή Odoo')
    match_state = fields.Selection([
        ('to_apply', 'Εκκρεμεί στο Odoo'),
        ('not_found', 'Δεν βρέθηκε στο τερματικό'),
    ], 'Κατάσταση')
