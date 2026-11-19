import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useBus, useService } from "@web/core/utils/hooks";

function beep() {
    try {
        const ctx = new AudioContext();
        const osc = ctx.createOscillator();
        osc.frequency.value = 330;
        osc.connect(ctx.destination);
        osc.start();
        osc.stop(ctx.currentTime + 0.4);
        osc.onended = () => ctx.close();
    } catch {
        // no audio device: the red screen still shows the error
    }
}

// «Σκανάρισμα απογραφής»: every barcode from the gun is one RPC that adds 1 on the
// server, so several PCs can count the same session and nothing lives only in the browser.
export class CountScan extends Component {
    static template = "stock_count_scan.CountScan";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.sessionId = this.props.action.params.session_id;
        this.state = useState({ code: "", minus: false, last: null, error: null, status: null });
        // The gun types into the page; Odoo's barcode service turns it into this event
        // (it skips keys typed into an input, which go through the form below instead).
        useBus(useService("barcode").bus, "barcode_scanned", (ev) => this.scan(ev.detail.barcode));
        onWillStart(() => this.refresh());
    }

    async refresh() {
        this.state.status = await this.orm.call("stock.count.session", "scan_status", [[this.sessionId]]);
    }

    async scan(code) {
        code = (code || "").trim();
        if (!code) {
            return;
        }
        const res = await this.orm.call("stock.count.session", "scan", [[this.sessionId], code],
                                        { qty: this.state.minus ? -1 : 1 });
        this.state.minus = false;
        if (res.error) {
            beep(); // the operator looks at the shelf, not the screen
            this.state.error = res.error;
            this.state.last = null;
            return;
        }
        this.state.error = null;
        this.state.last = res;
        this.state.status = res;
    }

    onSubmit(ev) {
        ev.preventDefault();
        const code = this.state.code;
        this.state.code = "";
        this.scan(code);
    }

    back() {
        this.action.doAction({
            type: "ir.actions.act_window", res_model: "stock.count.session",
            res_id: this.sessionId, views: [[false, "form"]],
        }, { clearBreadcrumbs: false });
    }
}

registry.category("actions").add("stock_count_scan.scan", CountScan);
