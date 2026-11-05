/** @odoo-module **/

import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { session } from "@web/session";

/** «Αποχώρηση» in the top bar, only while the employee is «inside». */
class ErganiCheckoutSystray extends Component {
    static template = "l10n_gr_ergani_card.CheckoutSystray";
    static props = {};

    checkout() {
        window.location = "/ergani/gate?mode=out";
    }
}

if (session.ergani_in) {
    registry.category("systray").add("ergani_checkout", {
        Component: ErganiCheckoutSystray,
        sequence: 26,
    });
}
