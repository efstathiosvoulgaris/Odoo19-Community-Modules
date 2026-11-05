import base64
import logging

from odoo import _, api, fields, models

from ..lib import rf

_logger = logging.getLogger(__name__)


def _org(company):
    return company.sudo().dias_org_code or False


class AccountMove(models.Model):
    _inherit = 'account.move'

    dias_rf_code = fields.Char('Κωδικός RF (καθαρός)', readonly=True, copy=False, index=True,
                               help='Ορίζεται στην επικύρωση, με το σύνολο του τιμολογίου.')
    dias_rf_code_fmt = fields.Char('Κωδικός RF', compute='_compute_dias_rf_code_fmt')

    @api.depends('dias_rf_code')
    def _compute_dias_rf_code_fmt(self):
        for move in self:
            move.dias_rf_code_fmt = rf.format_rf(move.dias_rf_code) if move.dias_rf_code else False

    def _dias_rf_eligible(self):
        self.ensure_one()
        return (self.move_type == 'out_invoice' and self.state == 'posted'
                and self.currency_id == self.company_id.currency_id
                and self.currency_id.name == 'EUR'
                and self.amount_total > 0 and _org(self.company_id))

    def _post(self, soft=True):
        posted = super()._post(soft=soft)
        # Το RF δεν μπλοκάρει ποτέ την επικύρωση: κάθε αποτυχία εδώ καταγράφεται και προσπερνιέται.
        # Οι αποδείξεις του ταμείου εξοφλούνται επί τόπου, οπότε δεν παίρνουν κωδικό.
        candidates = posted.filtered(lambda m: m.move_type == 'out_invoice' and not (
            'pos_order_ids' in m._fields and m.pos_order_ids))
        for move in candidates:
            try:
                with self.env.cr.savepoint():
                    move._dias_set_code()
            except Exception:  # noqa: BLE001
                _logger.exception('ΔΙΑΣ: κωδικός RF για %s', move.name)
        for move in candidates:
            try:
                with self.env.cr.savepoint():
                    move._dias_assign_order_credits()
            except Exception:  # noqa: BLE001
                _logger.exception('ΔΙΑΣ: συμψηφισμός πίστωσης παραγγελίας για %s', move.name)
                move.company_id._dias_notify_manager(
                    _('ΔΙΑΣ: πίστωση παραγγελίας δεν συμψηφίστηκε'),
                    _('Το τιμολόγιο %s έχει παραγγελία πληρωμένη μέσω ΔΙΑΣ· συμψηφίστε με το χέρι.',
                      move.name))
        return posted

    def _dias_set_code(self):
        self.ensure_one()
        if not self._dias_rf_eligible():
            return
        partner = self.commercial_partner_id
        try:
            code = rf.make_rf(_org(self.company_id), partner.id, rf.KIND_INVOICE,
                              self.id, self.amount_total)
        except ValueError:
            return
        if self.dias_rf_code != code:
            self.sudo().write({'dias_rf_code': code})
        Code = self.env['dias.rf.code'].sudo()
        if not Code.search_count([('code', '=', code), ('company_id', '=', self.company_id.id)]):
            Code.create({'code': code, 'company_id': self.company_id.id, 'move_id': self.id,
                         'partner_id': partner.id, 'amount': self.amount_total})

    def _dias_assign_order_credits(self):
        """Παραγγελία που πληρώθηκε με RF πριν τιμολογηθεί: η πίστωση (ή ό,τι περίσσεψε) συμψηφίζεται
        μόλις επικυρωθεί το τιμολόγιό της."""
        self.ensure_one()
        if self.amount_residual <= 0:
            return
        orders = self.invoice_line_ids.sale_line_ids.order_id
        if not orders:
            return
        payments = self.env['dias.payment'].sudo().search([
            ('order_id', 'in', orders.ids), ('state', 'in', ('credit', 'matched')),
            ('payment_id', '!=', False)])
        for line in payments.payment_id.move_id.line_ids.filtered(
                lambda l: l.account_id.account_type == 'asset_receivable' and not l.reconciled
                and l.partner_id.commercial_partner_id == self.commercial_partner_id):
            if self.amount_residual <= 0:
                break
            self.js_assign_outstanding_line(line.id)

    # ── Εκτύπωση ─────────────────────────────────────────────────────────────

    def _dias_rf_print(self):
        """Τι τυπώνεται στο έντυπο, ή False. Χωρίς ανοιχτό υπόλοιπο, τίποτα. Με μερική εξόφληση
        τυπώνεται ο πάγιος κωδικός (χωρίς έλεγχο ποσού), αλλιώς το υπόλοιπο δεν πληρώνεται."""
        self.ensure_one()
        if not (self.dias_rf_code and self.move_type == 'out_invoice' and self.state == 'posted'
                and self.amount_residual > 0):
            return False
        partial = self.currency_id.compare_amounts(self.amount_residual, self.amount_total) != 0
        if partial:
            code = self.commercial_partner_id._dias_rf_partner_code()
            qr = rf.qr_value(code) if code else False
        else:
            code = self.dias_rf_code
            qr = rf.qr_value(code, self.amount_total)
        if not code:
            return False
        png = self.env['ir.actions.report'].barcode('QR', qr, width=240, height=240)
        return {
            'code': rf.format_rf(code),
            'qr': 'data:image/png;base64,' + base64.b64encode(png).decode(),
            'fixed': partial,
            'test': self.company_id.sudo().dias_env != 'P',
        }

    # ── ΙΛΥΔΑ: RF στο paymentInstruction (BG-16) ─────────────────────────────

    def _l10n_gr_prov_ilyda_build_payload(self):
        payload = super()._l10n_gr_prov_ilyda_build_payload()
        if self.dias_rf_code and self.company_id.sudo().dias_send_ilyda \
                and self.company_id.sudo().dias_env == 'P':
            instruction = payload.setdefault('paymentInstruction', {})
            instruction['remittanceInfo'] = rf.clean(self.dias_rf_code)
            instruction.setdefault('paymentMeansTypeCode', '30')
        return payload
