import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { PosStore } from "@point_of_sale/app/services/pos_store";

/**
 * What the till prints is the legal document, not an Odoo receipt.
 *
 * Every provider order already exists as a posted, transmitted account.move,
 * and the base module renders it on the journal's Greek form (80mm for ΑΛΠ,
 * A4 for ΤΙΜ) carrying ΜΑΡΚ, provider QR and the authentication code. So the
 * till prints THAT PDF — the customer and an auditor get the same paper the
 * back office would hand out, and there is a single source of truth for the
 * legal layout.
 *
 * The thermal OrderReceipt survives as the offline fallback only: with no
 * account.move there is no document to print, and the receipt carries the
 * TF-1/TF-2 notice instead.
 *
 * ponytail: printed through the browser (hidden iframe → print dialog), which
 * is what this deployment uses. An ePOS/IoT thermal printer configured in
 * Odoo would NOT receive it — that path rasterizes an OWL component, so it
 * would need the report rendered as HTML into the printer container instead.
 */
patch(PosStore.prototype, {
    _grLegalMoveId(order) {
        if (!this.config.l10n_gr_prov_enabled
            || this.config.l10n_gr_prov_print_mode === "receipt") {
            return false;
        }
        // raw: account_move is a plain id on the client, not a loaded relation.
        return order?.raw?.account_move || false;
    },

    async printReceipt({ order = this.getOrder(), ...rest } = {}) {
        const moveId = this._grLegalMoveId(order);
        if (!moveId || rest.printBillActionTriggered) {
            return super.printReceipt({ order, ...rest });
        }
        const printed = await this._grPrintLegalDocument(moveId);
        if (this.config.l10n_gr_prov_print_mode === "both") {
            await super.printReceipt({ order, ...rest });
        }
        return printed;
    },

    /**
     * Print the rendered document. `account.report_invoice` is the routed
     * entry point: the base module's inherit swaps in the Greek 80mm/A4 body
     * for provider documents, so this one URL is right for ΑΛΠ and ΤΙΜ alike.
     */
    async _grPrintLegalDocument(moveId) {
        const url = `/report/pdf/account.report_invoice/${moveId}`;
        return new Promise((resolve) => {
            const frame = document.createElement("iframe");
            frame.style.display = "none";
            frame.src = url;
            let done = false;
            const finish = (ok) => {
                if (done) {
                    return;
                }
                done = true;
                if (!ok) {
                    this.env.services.notification.add(
                        _t("Το νόμιμο παραστατικό δεν εκτυπώθηκε — εκτυπώστε το από τις παραγγελίες."),
                        { type: "danger" }
                    );
                }
                // Keep the frame alive long enough for the print job to be
                // handed over; removing it immediately cancels the dialog.
                setTimeout(() => frame.remove(), 60000);
                resolve(ok);
            };
            frame.onload = () => {
                try {
                    frame.contentWindow.focus();
                    frame.contentWindow.print();
                    finish(true);
                } catch (e) {
                    console.warn("[GR] legal document print failed", e);
                    finish(false);
                }
            };
            frame.onerror = () => finish(false);
            document.body.appendChild(frame);
        });
    },
});
