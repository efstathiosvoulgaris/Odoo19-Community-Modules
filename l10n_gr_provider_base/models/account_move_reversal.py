# -*- coding: utf-8 -*-
from odoo import api, models

# Retail documents whose credit is the Πιστωτικό Στοιχείο Λιανικής (11.4).
RETAIL_CREDITED_BY_11_4 = frozenset({'11.1', '11.2'})


class AccountMoveReversal(models.TransientModel):
    _inherit = 'account.move.reversal'

    @api.depends('move_ids')
    def _compute_journal_id(self):
        """Propose ΠΛΠ (11.4) when reversing an ΑΛΠ.

        Core proposes the reversed document's own journal. For an ΑΛΠ that
        means a credit note in the ΑΛΠ series, which the payload then sends as
        5.1 — and 5.1 requires the customer's ΑΦΜ, so a retail credit note was
        refused (2026-10-06, ΑΛΠ/00016). The POS already routes its returns to
        ΠΛΠ; this does the same for the back-office «Πιστωτικό Τιμολόγιο».
        Only the proposal changes: a journal the user picks stays.
        """
        super()._compute_journal_id()
        for wizard in self:
            moves = wizard.move_ids
            if (not moves or wizard.country_code != 'GR'
                    or wizard.journal_id not in moves.journal_id
                    or any(m.move_type != 'out_invoice' for m in moves)
                    or not set(moves.journal_id.mapped('l10n_gr_edi_inv_type_default'))
                    <= RETAIL_CREDITED_BY_11_4):
                continue
            credit_journal = self.env['account.journal'].search([
                *self.env['account.journal']._check_company_domain(wizard.company_id),
                ('type', '=', 'sale'),
                ('l10n_gr_edi_inv_type_default', '=', '11.4'),
                ('l10n_gr_prov_delivery_note', '=', False),
            ], limit=1)
            if credit_journal:
                wizard.journal_id = credit_journal
