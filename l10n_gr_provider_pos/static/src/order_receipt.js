import { patch } from "@web/core/utils/patch";
import { OrderReceipt } from "@point_of_sale/app/screens/receipt_screen/receipt/order_receipt";
import { generateQRCodeDataUrl } from "@point_of_sale/utils";

patch(OrderReceipt.prototype, {
    grProvQr(url) {
        return generateQRCodeDataUrl(url);
    },
});
