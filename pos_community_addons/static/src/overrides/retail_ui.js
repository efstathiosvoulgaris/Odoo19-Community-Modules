import { patch } from "@web/core/utils/patch";
import { normalize } from "@web/core/l10n/utils";
import { ProductTemplate } from "@point_of_sale/app/models/product_template";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";

/**
 * Search: core matches name, default_code and barcode only. Add the MPN and
 * the supplier's code/name (pos_search_extra) — "TK-18" finds the toner even
 * when our name says "Toner KYOCERA MITA Συμβατό TK-18".
 */
patch(ProductTemplate.prototype, {
    get searchString() {
        const base = super.searchString;
        const extra = this.pos_search_extra;
        return extra ? `${base} ${normalize(extra)}` : base;
    },
});

/**
 * «Τιμολόγιο» without a customer is always followed by picking one — so open
 * the picker right away instead of letting Επικύρωση fail on it later.
 */
patch(PaymentScreen.prototype, {
    async toggleIsToInvoice() {
        await super.toggleIsToInvoice(...arguments);
        if (this.currentOrder.isToInvoice() && !this.currentOrder.getPartner()) {
            await this.pos.selectPartner();
        }
    },
});
