import { Component, xml } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";

/**
 * «Σε ποιο τερματικό;» — one big button per terminal, the last one used on
 * this till highlighted. Resolves (through makeAwaitable) with the terminal
 * id, or undefined when the cashier closes it.
 */
export class GrTerminalDialog extends Component {
    static components = { Dialog };
    static props = {
        title: String,
        terminals: Array,
        preselected: { type: Number, optional: true },
        getPayload: Function,
        close: Function,
    };
    static template = xml`
        <Dialog title="props.title" size="'sm'">
            <div class="d-grid gap-2">
                <t t-foreach="props.terminals" t-as="terminal" t-key="terminal.id">
                    <button type="button" class="btn btn-lg"
                            t-att-class="terminal.id === props.preselected ? 'btn-primary' : 'btn-secondary'"
                            t-on-click="() => this.pick(terminal)">
                        <t t-esc="terminal.name"/>
                    </button>
                </t>
            </div>
            <t t-set-slot="footer">
                <button type="button" class="btn btn-link" t-on-click="() => this.props.close()">Άκυρο</button>
            </t>
        </Dialog>`;

    pick(terminal) {
        this.props.getPayload(terminal.id);
        this.props.close();
    }
}
