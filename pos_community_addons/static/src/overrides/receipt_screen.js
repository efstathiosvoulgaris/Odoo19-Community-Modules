/** @odoo-module **/

import { ReceiptScreen } from "@point_of_sale/app/screens/receipt_screen/receipt_screen";
import { OrderReceipt } from "@point_of_sale/app/screens/receipt_screen/receipt/order_receipt";
import { patch } from "@web/core/utils/patch";
import { onMounted } from "@odoo/owl";

// After payment is validated: print to Epson, then go straight back to floor plan
patch(ReceiptScreen.prototype, {
    setup() {
        super.setup();
        onMounted(async () => {
            if (this.pos.config.iface_print_auto) {
                try {
                    await this.pos.printReceipt({ order: this.currentOrder });
                } catch (e) {
                    console.error("Barista ticket print failed:", e);
                }
            }
            this.pos.orderDone(this.currentOrder);
        });
    },
});

// Replace the customer receipt template with a minimal barista ticket
OrderReceipt.template = "pos_community_addons.BaristaTicket";
