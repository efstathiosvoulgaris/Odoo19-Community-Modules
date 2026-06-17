/** @odoo-module **/

import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";
import { patch } from "@web/core/utils/patch";

/**
 * In Odoo 19, swapButton requires preparationCategories.size > 0 (kitchen printers).
 * Without printers the entire Send/New area is hidden. We restore the pre-19 behaviour
 * so the Send button always appears for restaurant orders regardless of printer setup.
 */
patch(ProductScreen.prototype, {
    get swapButton() {
        return Boolean(this.pos.config.module_pos_restaurant);
    },
});
