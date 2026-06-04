/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ResPartner } from "@point_of_sale/app/models/res_partner";

patch(ResPartner.prototype, {
    get searchString() {
        const base = super.searchString;
        const extras = ["eponymia", "kinito", "doy", "drastiriotita"]
            .map((f) => {
                const v = this[f];
                if (!v) return "";
                if (f === "kinito") {
                    return v.replace(/[+\s()-]/g, "");
                }
                return v;
            })
            .filter(Boolean)
            .join(" ");
        return extras ? `${base} ${extras}` : base;
    },
});
