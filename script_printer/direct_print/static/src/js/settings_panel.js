/** @odoo-module **/

import { Component, useState, onMounted } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

async function _odooJson(route, params = {}) {
    try {
        const resp = await fetch(route, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            credentials: "same-origin",
            body: JSON.stringify({ jsonrpc: "2.0", method: "call", id: 1, params }),
        });
        const data = await resp.json();
        return data.result ?? null;
    } catch {
        return null;
    }
}

class DirectPrintSettings extends Component {
    static template = "direct_print.SettingsPanel";

    setup() {
        this.directPrint = useService("direct_print");
        this.notification = useService("notification");

        this.state = useState({
            loading: true,
            saving: false,
            agentOnline: false,
            agentUrl: DEFAULT_AGENT_URL,
            printers: [],
            selectedPrinter: this.directPrint.state.selectedPrinter,
            receiptPrinter: this.directPrint.state.receiptPrinter,
        });

        onMounted(() => this._load());
    }

    async _load() {
        const config = await _odooJson("/direct_print/config");
        this.state.agentUrl = config?.agent_url || DEFAULT_AGENT_URL;

        const online = await this.directPrint.checkAgent();
        this.state.agentOnline = online;
        if (online) {
            this.state.printers = await this.directPrint.loadPrinters();
        }
        this.state.loading = false;
    }

    async refresh() {
        this.state.loading = true;
        await this._load();
    }

    async save() {
        this.state.saving = true;
        try {
            // Save agent URL via Odoo settings (admin only — server enforces access)
            await _odooJson("/web/dataset/call_kw", {
                model: "ir.config_parameter",
                method: "set_param",
                args: ["direct_print.agent_url", this.state.agentUrl],
                kwargs: {},
            });

            this.directPrint.setSelectedPrinter(this.state.selectedPrinter);
            this.directPrint.setReceiptPrinter(this.state.receiptPrinter);

            this.notification.add("Settings saved", { type: "success" });
        } finally {
            this.state.saving = false;
        }
    }
}

const DEFAULT_AGENT_URL = "http://127.0.0.1:5000";

registry.category("actions").add("direct_print.settings", DirectPrintSettings);
