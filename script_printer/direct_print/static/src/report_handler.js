import { registry } from "@web/core/registry";
import { agentPrint } from "./agent";

registry.category("ir.actions.report handlers").add("direct_print", async (action, options, env) => {
    if (
        (action.report_type && action.report_type !== "qweb-pdf") ||
        // Reports built from `data` are POSTed by Odoo's own download; a GET
        // URL would drop it (e.g. a quick-login card's QR) or log it.
        (action.data && Object.keys(action.data).length)
    ) {
        return false;
    }
    const ids = action.context?.active_ids || action.context?.active_id;
    let url = `/report/pdf/${action.report_name}`;
    if (ids) {
        url += `/${[].concat(ids).join(",")}`;
    }
    if (action.context && Object.keys(action.context).length) {
        url += `?context=${encodeURIComponent(JSON.stringify(action.context))}`;
    }
    return agentPrint(url, env.services.notification);
});
