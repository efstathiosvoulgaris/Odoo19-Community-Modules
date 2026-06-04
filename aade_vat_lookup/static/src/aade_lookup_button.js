/** @odoo-module **/

import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";
import { _t } from "@web/core/l10n/translation";

export class AadeLookupButton extends Component {
    static template = "aade_vat_lookup.AadeLookupButton";
    static props = { ...standardWidgetProps };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
    }

    get isVisible() {
        const country = this.props.record.data.country_id;
        if (!country) return true;
        // Συμβατότητα με διάφορα formats many2one:
        // [id, display_name] | {id, display_name} | record-like με .display_name
        let label = "";
        if (Array.isArray(country)) {
            label = country[1] || "";
        } else if (typeof country === "object") {
            label = country.display_name || country.name || "";
        }
        label = label.toLowerCase();
        if (!label) return true;
        return label.includes("ελλά") || label.includes("greece");
    }

    async onClick() {
        // Αναγκάζουμε το ενεργό input να κάνει commit και περιμένουμε ένα tick
        if (document.activeElement && typeof document.activeElement.blur === "function") {
            document.activeElement.blur();
        }
        await new Promise((r) => setTimeout(r, 50));

        // Fallback: αν το record state δεν ενημερώθηκε ακόμα, διαβάζουμε
        // απευθείας το input από το DOM.
        let vat = this.props.record.data.vat || "";
        if (!vat) {
            const domInput = document.querySelector(
                'input[id*="vat"], input[name="vat"]'
            );
            if (domInput && domInput.value) {
                vat = domInput.value;
            }
        }
        const existing = {
            name: this.props.record.data.name,
            eponymia: this.props.record.data.eponymia,
            doy: this.props.record.data.doy,
            street: this.props.record.data.street,
            arithmos_odou: this.props.record.data.arithmos_odou,
            zip: this.props.record.data.zip,
            city: this.props.record.data.city,
            drastiriotita: this.props.record.data.drastiriotita,
            country_id: this.props.record.data.country_id && this.props.record.data.country_id[0],
            is_company: this.props.record.data.is_company,
        };
        try {
            const result = await this.orm.call(
                "res.partner",
                "aade_lookup_vals",
                [vat, existing],
            );
            const vals = result.vals || {};
            const updateVals = {};
            for (const [key, value] of Object.entries(vals)) {
                if (value === false || value === null || value === undefined) continue;
                updateVals[key] = value;
            }
            await this.props.record.update(updateVals);
            this.notification.add(result.message || _t("Ενημερώθηκε"), {
                type: result.type || "success",
            });
        } catch (e) {
            const msg = (e && e.data && e.data.message) || e.message || String(e);
            this.notification.add(msg, { type: "danger", sticky: true });
        }
    }
}

registry.category("view_widgets").add("aade_lookup_button", {
    component: AadeLookupButton,
});
