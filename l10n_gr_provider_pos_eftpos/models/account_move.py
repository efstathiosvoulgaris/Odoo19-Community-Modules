# -*- coding: utf-8 -*-
from odoo import models


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _l10n_gr_prov_ilyda_build_payload(self):
        """Enrich the type-7 payment methods with the Α.1155 signature captured
        at the POS (stored directly on the myDATA payment line, not via an
        l10n.gr.prov.eft.payment record). Complements the backend eftpos
        enrichment, which reads line.eft_payment_id — for POS lines that link
        is empty, so the two never collide."""
        payload = super()._l10n_gr_prov_ilyda_build_payload()
        methods = payload.get('paymentMethods') or []
        lines = self.l10n_gr_prov_payment_ids
        # the builder emits one method dict per payment line, in order
        if len(methods) == len(lines):
            for line, method in zip(lines, methods):
                if method.get('type') == 7 and line.l10n_gr_prov_eft_signature:
                    method.update({
                        'signature': line.l10n_gr_prov_eft_signature,
                        'signingAuthor': line.l10n_gr_prov_eft_signing_author,
                        'terminalId': line.l10n_gr_prov_eft_terminal_code,
                        'transactionId': line.transaction_id,
                    })
        return payload
