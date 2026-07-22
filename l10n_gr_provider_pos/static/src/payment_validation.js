import { patch } from "@web/core/utils/patch";
import OrderPaymentValidation from "@point_of_sale/app/utils/order_payment_validation";

patch(OrderPaymentValidation.prototype, {
    /**
     * Provider POS: every order is invoiced server-side (the receipt is the
     * legal ΑΛΠ), so the stock "download the invoice PDF" behavior must only
     * fire when the cashier explicitly asked for a Τιμολόγιο.
     */
    shouldDownloadInvoice() {
        if (this.pos.config.l10n_gr_prov_alp_journal_id) {
            return Boolean(this.order.raw?.l10n_gr_prov_timologio)
                && super.shouldDownloadInvoice();
        }
        return super.shouldDownloadInvoice();
    },
});
