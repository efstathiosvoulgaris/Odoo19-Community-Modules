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
 *
 * This has to hook onMounted, not setup: core applies its own rule in
 * onMounted (registered from setup, so it always runs after ours would), and
 * would flip the flag straight back on for every provider refund.
 */
patch(PaymentScreen.prototype, {
    onMounted() {
        super.onMounted(...arguments);
        const order = this.currentOrder;
        if (!this.pos.config.l10n_gr_prov_enabled || !order?.isRefund) {
            return;
        }
        // Any refunded line identifies the original — lines[0] does not: a
        // product, tip or rounding line added to the refund can sort first,
        // and the server derives its answer from refunded_order_id the same
        // way. Nothing found = nothing to correct; leave core's decision.
        const origin = order.lines.find((l) => l.refunded_orderline_id)
            ?.refunded_orderline_id?.order_id;
        if (origin) {
            order.setToInvoice(Boolean(origin.l10n_gr_prov_timologio));
        }
    },
});
