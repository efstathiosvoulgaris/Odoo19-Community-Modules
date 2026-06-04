/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { PartnerList } from "@point_of_sale/app/screens/partner_list/partner_list";

const GR_EXTRA_SEARCH_FIELDS = ["eponymia", "kinito", "doy", "drastiriotita"];

patch(PartnerList.prototype, {
    async getNewPartners() {
        // Προεκτείνουμε το search domain ώστε ο server να ψάχνει και
        // στα ελληνικά πεδία. Χρησιμοποιούμε το ίδιο pattern με το
        // base (ilike "%query%").
        let domain = [];
        const offset = this.globalState.offsetBySearch[this.state.query] || 0;
        if (offset > this.loadedPartnerIds.size) {
            return [];
        }
        if (this.state.query) {
            const search_fields = [
                "name",
                "parent_name",
                "phone_mobile_search",
                "email",
                "barcode",
                "street",
                "zip",
                "city",
                "state_id",
                "country_id",
                "vat",
                ...GR_EXTRA_SEARCH_FIELDS,
            ];
            domain = [
                ...Array(search_fields.length - 1).fill("|"),
                ...search_fields.map((field) => [field, "ilike", this.state.query + "%"]),
            ];
        }

        try {
            this.state.loading = true;
            const result = await this.pos.data.callRelated("res.partner", "get_new_partner", [
                this.pos.config.id,
                domain,
                offset,
            ]);
            this.globalState.offsetBySearch[this.state.query] =
                offset + (result["res.partner"].length || 100);
            for (const partner of result["res.partner"]) {
                if (!this.loadedPartnerIds.has(partner.id)) {
                    this.loadedPartnerIds.add(partner.id);
                    this.state.loadedPartners.push(partner);
                }
            }
            return result["res.partner"];
        } catch {
            return [];
        } finally {
            this.state.loading = false;
        }
    },
});
