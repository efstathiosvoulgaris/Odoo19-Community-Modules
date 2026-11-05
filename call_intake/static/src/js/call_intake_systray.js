/** @odoo-module **/

import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

/** Phone icon in the top bar: «Νέο Τηλεφώνημα» from any screen. */
class CallIntakeSystray extends Component {
    static template = "call_intake.Systray";
    static props = {};

    setup() {
        this.action = useService("action");
    }

    openWizard() {
        this.action.doAction("call_intake.action_call_intake_wizard");
    }
}

registry.category("systray").add("call_intake", {
    Component: CallIntakeSystray,
    sequence: 25,
});
