/** @odoo-module **/

import { Component, useState, onMounted, onWillUnmount } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

class DirectPrintSystray extends Component {
    static template = "direct_print.SystrayStatus";

    setup() {
        this.directPrint = useService("direct_print");
        this.state = useState({ open: false });

        onMounted(() => {
            this._pollInterval = setInterval(() => {
                this.directPrint.checkAgent();
            }, 30000);
        });

        onWillUnmount(() => {
            clearInterval(this._pollInterval);
        });
    }

    get agentOnline() {
        return this.directPrint.state.agentOnline;
    }

    get selectedPrinter() {
        return this.directPrint.state.selectedPrinter || "(Windows default)";
    }

    get receiptPrinter() {
        return this.directPrint.state.receiptPrinter || "—";
    }

    toggleDropdown() {
        this.state.open = !this.state.open;
    }

    closeDropdown() {
        this.state.open = false;
    }

    async refresh() {
        await this.directPrint.checkAgent();
        if (this.directPrint.state.agentOnline) {
            await this.directPrint.loadPrinters();
        }
    }
}

registry.category("systray").add("direct_print_status", {
    Component: DirectPrintSystray,
    sequence: 50,
});
