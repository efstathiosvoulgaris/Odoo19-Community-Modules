import { Component, onWillUnmount, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const POLL_MS = 1500;

// «Αναμονή υπογραφής»: waits on the PC while the customer signs on the phone.
// The ticket itself moves to «Παραλήφθηκε» on the server when the signature
// arrives; this only watches the request and reloads the form.
export class SignatureWaitDialog extends Component {
    static template = "repair_shop_tickets.SignatureWaitDialog";
    static components = { Dialog };
    static props = ["close", "requestId", "ticket", "onDone"];

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({ cancelling: false });
        this.timer = setInterval(() => this.poll(), POLL_MS);
        onWillUnmount(() => clearInterval(this.timer));
    }

    async poll() {
        let status;
        try {
            status = await this.orm.call("service.signature.request", "read_status",
                                         [[this.props.requestId]]);
        } catch {
            return; // network hiccup: try again on the next tick
        }
        const messages = {
            signed: ["Ο πελάτης υπέγραψε· το δελτίο παραλήφθηκε.", "success"],
            declined: ["Ο πελάτης πάτησε «Άκυρο». Το δελτίο μένει «Επιλύθηκε».", "warning"],
            expired: ["Το αίτημα υπογραφής έληξε.", "info"],
            cancelled: ["Το αίτημα υπογραφής ακυρώθηκε.", "info"],
        };
        if (status.state in messages) {
            const [text, type] = messages[status.state];
            this.notification.add(text, { type });
            this.finish();
        }
    }

    async cancel() {
        this.state.cancelling = true;
        await this.orm.call("service.signature.request", "action_cancel", [[this.props.requestId]]);
        this.finish();
    }

    finish() {
        clearInterval(this.timer);
        this.props.close();
        this.props.onDone();
    }
}

registry.category("actions").add("repair_shop_tickets.signature_wait", async (env, action) => {
    const { request_id, ticket } = action.params;
    env.services.dialog.add(SignatureWaitDialog, {
        requestId: request_id,
        ticket,
        onDone: () => env.services.action.doAction({ type: "ir.actions.client", tag: "soft_reload" }),
    }, {
        // Closing with the X or Esc must not leave a request waiting on the phone.
        onClose: () => env.services.orm.call("service.signature.request", "action_cancel",
                                             [[request_id]]).catch(() => {}),
    });
});
