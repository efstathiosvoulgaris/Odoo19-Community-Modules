import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { agentPrint } from "./agent";

// The till's legal document (l10n_gr_provider_pos) goes to the agent first;
// the browser print dialog stays as the fallback.
patch(PosStore.prototype, {
    async _grPrintLegalDocument(moveId) {
        const printed = await agentPrint(
            `/report/pdf/account.report_invoice/${moveId}`, this.env.services.notification);
        return printed || super._grPrintLegalDocument(moveId);
    },
});
