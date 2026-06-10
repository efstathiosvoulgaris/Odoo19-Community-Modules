# -*- coding: utf-8 -*-
import base64
import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

PROVIDER_STATES = [
    ('to_send', 'To Send'),
    ('sent', 'Issued (Marked)'),
    ('error', 'Error'),
]


class AccountMove(models.Model):
    _inherit = 'account.move'

    # ── Provider transmission state ───────────────────────────────────────────
    l10n_gr_prov_state = fields.Selection(
        PROVIDER_STATES, string='Provider Status', copy=False, tracking=True)
    l10n_gr_prov_error = fields.Text(string='Provider Error', copy=False)
    l10n_gr_prov_send_datetime = fields.Datetime(string='Provider Sent At', copy=False)

    # ── Legal markings returned by the provider (A.1035/2020) ────────────────
    l10n_gr_prov_mark = fields.Char(string='MARK (Provider)', copy=False)
    l10n_gr_prov_invoice_id = fields.Char(string='Provider Invoice ID', copy=False)
    l10n_gr_prov_verification_hash = fields.Char(
        string='Authentication String', copy=False,
        help='SHA-1 verification hash (Συμβολοσειρά Αυθεντικοποίησης), Appendix B1 of A.1035/2020.')
    l10n_gr_prov_invoice_identifier = fields.Char(
        string='Invoice Identifier', copy=False,
        help='SHA-1 invoice identifier (Αναγνωριστικό Παραστατικού), Appendix B2 of A.1035/2020.')
    l10n_gr_prov_qr_url = fields.Char(string='Provider QR URL', copy=False)
    l10n_gr_prov_provider_url = fields.Char(string='Provider Site', copy=False)
    l10n_gr_prov_previously_submitted = fields.Boolean(
        string='Previously Submitted', copy=False,
        help='Set when the provider recovered the marking from a prior submission '
             '(AADE error 228 handling).')
    l10n_gr_prov_pdf_uploaded = fields.Boolean(string='PDF Uploaded to Provider', copy=False)

    # ── B2G (Peppol) ──────────────────────────────────────────────────────────
    l10n_gr_prov_b2g = fields.Boolean(
        string='B2G (Public Sector)', copy=False,
        help='Route this document through the Peppol network (public contracts).')
    l10n_gr_prov_contract_ref = fields.Char(
        string='Contract Reference (BT-12, ΑΔΑΜ)', copy=False,
        help='Public contract reference (ΑΔΑΜ), e.g. 20SYMV006467658.')
    l10n_gr_prov_budget_type = fields.Selection(
        selection=[
            ('1', '1 - Τακτικός Προϋπολογισμός (ΑΔΑ Ανάληψης)'),
            ('2', '2 - Πρόγραμμα Δημοσίων Επενδύσεων (Ενάριθμος έργου)'),
            ('3', '3 - Λοιποί Προϋπολογισμοί (ΑΔΑ Ανάληψης)'),
        ],
        string='Budget Type (BT-11)', copy=False, default='1')
    l10n_gr_prov_budget_ref = fields.Char(
        string='Budget Identifier (BT-11)', copy=False,
        help='ΑΔΑ Ανάληψης (budget types 1/3) or Ενάριθμος έργου ΠΔΕ (type 2). '
             'Sent as "<type>|<identifier>".')
    l10n_gr_prov_purchase_order_ref = fields.Char(
        string='Purchase Order (BT-13)', copy=False,
        help='Purchase order reference issued by the buyer (Αναγνωριστικό Εντολής Αγοράς).')
    l10n_gr_prov_buyer_ref = fields.Char(
        string='Buyer Reference (BT-10)', copy=False,
        compute='_compute_l10n_gr_prov_buyer_ref', store=True, readonly=False,
        help='Routing reference: "<Περιγραφή Α.Α>|<ΑΑΗΤ or internal unit code>", '
             'e.g. "Νοσοκ ΕΥΑΓΓΕΛΙΣΜΟΣ|XYZ123ABC". Defaults from the customer '
             'name and its ΑΑΗΤ code; adjust if the contracting authority differs.')
    l10n_gr_prov_b2g_status = fields.Char(string='B2G Status', copy=False)

    @api.depends('partner_id', 'l10n_gr_prov_b2g')
    def _compute_l10n_gr_prov_buyer_ref(self):
        for move in self:
            if move.l10n_gr_prov_buyer_ref or not move.l10n_gr_prov_b2g:
                continue
            partner = move.commercial_partner_id
            if partner.l10n_gr_prov_aaht:
                move.l10n_gr_prov_buyer_ref = f'{partner.name}|{partner.l10n_gr_prov_aaht}'
            elif partner:
                move.l10n_gr_prov_buyer_ref = partner.name or False

    l10n_gr_prov_applicable = fields.Boolean(
        compute='_compute_l10n_gr_prov_applicable')

    @api.depends('move_type', 'company_id.l10n_gr_prov_provider', 'country_code')
    def _compute_l10n_gr_prov_applicable(self):
        for move in self:
            move.l10n_gr_prov_applicable = (
                move.is_sale_document(include_receipts=True)
                and move.country_code == 'GR'
                and move.company_id._l10n_gr_prov_active()
            )

    # ── Posting hook: queue, never call the network inside the posting tx ────
    def _post(self, soft=True):
        posted = super()._post(soft)
        queue = posted.filtered(
            lambda m: m.l10n_gr_prov_applicable and not m.l10n_gr_prov_mark
            and not m.l10n_gr_prov_state
        )
        if queue:
            queue.write({'l10n_gr_prov_state': 'to_send'})
        return posted

    # ── Actions ───────────────────────────────────────────────────────────────
    def action_l10n_gr_prov_send(self):
        """Manual send button."""
        for move in self:
            if not move.l10n_gr_prov_applicable:
                raise UserError(_('No e-invoicing provider is configured for this document.'))
            if move.state != 'posted':
                raise UserError(_('Only posted documents can be sent to the provider.'))
            if move.l10n_gr_prov_mark:
                raise UserError(_('This document already has a MARK from the provider.'))
            move._l10n_gr_prov_try_send(raise_on_error=True)

    def action_l10n_gr_prov_refresh_b2g_status(self):
        for move in self:
            if move.l10n_gr_prov_b2g and move.l10n_gr_prov_invoice_id:
                move._l10n_gr_prov_dispatch('poll_b2g_status')

    # ── Core dispatch to the configured driver ────────────────────────────────
    def _l10n_gr_prov_dispatch(self, operation):
        """Call the driver implementation for `operation`.

        Drivers implement methods named _l10n_gr_prov_<operation>_<provider>,
        e.g. _l10n_gr_prov_send_ilyda, _l10n_gr_prov_upload_pdf_ilyda.
        """
        self.ensure_one()
        provider = self.company_id.l10n_gr_prov_provider
        handler = getattr(self, f'_l10n_gr_prov_{operation}_{provider}', None)
        if handler is None:
            raise UserError(_(
                'The configured provider "%s" does not implement "%s". '
                'Is the driver module installed?', provider, operation))
        return handler()

    def _l10n_gr_prov_try_send(self, raise_on_error=False):
        """Send one document; on failure store the error instead of crashing."""
        self.ensure_one()
        try:
            self._l10n_gr_prov_dispatch('send')
            self.write({
                'l10n_gr_prov_state': 'sent',
                'l10n_gr_prov_error': False,
                'l10n_gr_prov_send_datetime': fields.Datetime.now(),
            })
            self.message_post(body=_(
                'Issued through the e-invoicing provider. MARK: %s', self.l10n_gr_prov_mark))
        except Exception as e:
            msg = str(e)
            self.write({'l10n_gr_prov_state': 'error', 'l10n_gr_prov_error': msg})
            self.message_post(body=_('Provider submission failed: %s', msg))
            if raise_on_error:
                raise

    # ── PDF upload (after marking, once the legal PDF exists) ────────────────
    def _l10n_gr_prov_get_pdf(self):
        """Return (filename, bytes) of the invoice PDF, rendering it if needed."""
        self.ensure_one()
        attachment = self.invoice_pdf_report_id
        if attachment:
            return attachment.name, base64.b64decode(attachment.datas)
        report = self.env.ref('account.account_invoices')
        content, _type = self.env['ir.actions.report']._render_qweb_pdf(
            report, res_ids=self.ids)
        return f'{(self.name or "invoice").replace("/", "_")}.pdf', content

    def _l10n_gr_prov_try_upload_pdf(self):
        self.ensure_one()
        try:
            self._l10n_gr_prov_dispatch('upload_pdf')
            self.l10n_gr_prov_pdf_uploaded = True
        except Exception as e:
            _logger.warning('Provider PDF upload failed for %s: %s', self.name, e)

    # ── Cron: retry queue ─────────────────────────────────────────────────────
    @api.model
    def _l10n_gr_prov_cron_process(self):
        """Send queued documents, upload pending PDFs, poll B2G statuses."""
        # 1. Pending sends (auto-send companies) and previous errors (all companies)
        domain = [
            ('state', '=', 'posted'),
            ('l10n_gr_prov_state', 'in', ('to_send', 'error')),
            ('l10n_gr_prov_mark', '=', False),
        ]
        for move in self.search(domain, limit=50):
            if not move.l10n_gr_prov_applicable:
                continue
            if move.l10n_gr_prov_state == 'to_send' and not move.company_id.l10n_gr_prov_auto_send:
                continue  # manual mode: only retry documents that were attempted (error)
            move._l10n_gr_prov_try_send()
            self.env.cr.commit()  # persist each marking immediately; it exists at AADE

        # 2. Upload PDFs for marked documents
        for move in self.search([
            ('l10n_gr_prov_state', '=', 'sent'),
            ('l10n_gr_prov_pdf_uploaded', '=', False),
            ('l10n_gr_prov_invoice_id', '!=', False),
        ], limit=50):
            move._l10n_gr_prov_try_upload_pdf()
            self.env.cr.commit()

        # 3. Poll B2G statuses
        for move in self.search([
            ('l10n_gr_prov_b2g', '=', True),
            ('l10n_gr_prov_state', '=', 'sent'),
            ('l10n_gr_prov_invoice_id', '!=', False),
        ], limit=50):
            try:
                move._l10n_gr_prov_dispatch('poll_b2g_status')
            except Exception as e:
                _logger.warning('B2G status poll failed for %s: %s', move.name, e)

    # ── Report helper: QR image as base64 PNG ─────────────────────────────────
    def _l10n_gr_prov_qr_image(self):
        self.ensure_one()
        if not self.l10n_gr_prov_qr_url:
            return False
        barcode = self.env['ir.actions.report'].barcode(
            'QR', self.l10n_gr_prov_qr_url, width=120, height=120)
        return base64.b64encode(barcode).decode()
