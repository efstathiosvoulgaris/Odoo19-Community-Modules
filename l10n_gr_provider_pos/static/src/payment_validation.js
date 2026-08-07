import { patch } from "@web/core/utils/patch";
import OrderPaymentValidation from "@point_of_sale/app/utils/order_payment_validation";

patch(OrderPaymentValidation.prototype, {
    /**
     * Provider POS: every order is invoiced server-side, and the till PRINTS
     * that document (legal_print.js). Downloading a PDF file per sale on top
     * of it is just clutter on the cashier's machine.
     */
    shouldDownloadInvoice() {
        if (this.pos.config.l10n_gr_prov_enabled) {
            return false;
        }
        return super.shouldDownloadInvoice();
    },
});
