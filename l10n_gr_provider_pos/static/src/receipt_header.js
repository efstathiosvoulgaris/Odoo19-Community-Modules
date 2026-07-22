import { patch } from "@web/core/utils/patch";
import { ReceiptHeader } from "@point_of_sale/app/screens/receipt_screen/receipt/receipt_header/receipt_header";

const GR_DOC_TITLES = {
    "11.1": "ΑΠΟΔΕΙΞΗ ΛΙΑΝΙΚΗΣ ΠΩΛΗΣΗΣ",
    "11.2": "ΑΠΟΔΕΙΞΗ ΠΑΡΟΧΗΣ ΥΠΗΡΕΣΙΩΝ",
    "11.3": "ΑΠΛΟΠΟΙΗΜΕΝΟ ΤΙΜΟΛΟΓΙΟ",
    "11.4": "ΠΙΣΤΩΤΙΚΟ ΣΤΟΙΧΕΙΟ ΛΙΑΝΙΚΗΣ",
    "11.5": "ΑΠΟΔΕΙΞΗ ΛΙΑΝΙΚΗΣ ΠΩΛΗΣΗΣ ΓΙΑ ΛΟΓ/ΣΜΟ ΤΡΙΤΩΝ",
    "1.1": "ΤΙΜΟΛΟΓΙΟ ΠΩΛΗΣΗΣ",
    "5.1": "ΠΙΣΤΩΤΙΚΟ ΤΙΜΟΛΟΓΙΟ",
    "5.2": "ΠΙΣΤΩΤΙΚΟ ΤΙΜΟΛΟΓΙΟ",
};

patch(ReceiptHeader.prototype, {
    get grDocTitle() {
        return GR_DOC_TITLES[this.order.l10n_gr_prov_inv_type] || "";
    },
});
