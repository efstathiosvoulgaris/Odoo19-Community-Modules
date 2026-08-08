import { patch } from "@web/core/utils/patch";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";

/**
 * «Τιμολόγιο» on a refund follows the ORIGINAL document, not `to_invoice`.
 *
 * Core switches the flag on for a refund whose refunded order was invoiced, and
 * disables the button so the cashier cannot undo it — sound in stock Odoo,
 * where only an invoiced sale can be credited by an invoice. On a provider till
 * every order is invoiced (the provider needs an account.move for each one), so
 * the rule fired on every refund: ΤΙΜ ticked, button locked, and a refund of a
 * plain retail receipt demanded a customer with ΑΦΜ.
 *
 * What actually decides is whether the original was a ΤΙΜ. The server is the
 * authority (_l10n_gr_prov_wants_timologio); this only stops the button from
 * showing the opposite of what will be issued.
 */
patch(PaymentScreen.prototype, {
    setup() {
        super.setup(...arguments);
        const order = this.currentOrder;
        if (!this.pos.config.l10n_gr_prov_enabled || !order?.isRefund) {
            return;
        }
        const origin = order.lines[0]?.refunded_orderline_id?.order_id;
        order.setToInvoice(Boolean(origin?.l10n_gr_prov_timologio));
    },
});
