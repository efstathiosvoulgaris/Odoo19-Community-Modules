/** @odoo-module **/

import { registry } from "@web/core/registry";

async function directPrintReportHandler(action, options, env) {
    const directPrint = env.services.direct_print;

    if (
        !directPrint ||
        !directPrint.state.agentOnline ||
        (action.report_type && action.report_type !== "qweb-pdf")
    ) {
        return false;
    }

    try {
        // Check for a per-report route override
        const route = directPrint.getRoute(action.report_name);
        const printerName = route?.printer_name || null;
        const copies = route?.copies || 1;

        // Build the report URL the same way Odoo would
        const reportName = action.report_name;
        const activeIds = action.context?.active_ids || action.context?.active_id;
        let url = `/report/pdf/${reportName}`;
        if (activeIds) {
            const ids = Array.isArray(activeIds) ? activeIds.join(",") : activeIds;
            url += `/${ids}`;
        }
        const context = action.context || {};
        if (Object.keys(context).length) {
            url += `?context=${encodeURIComponent(JSON.stringify(context))}`;
        }

        // Fetch the PDF from Odoo using the browser session
        const resp = await fetch(url, { method: "GET", credentials: "same-origin" });
        if (!resp.ok) throw new Error(`Failed to fetch report: ${resp.status}`);

        // Convert blob → base64
        const blob = await resp.blob();
        const base64 = await new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onloadend = () => resolve(reader.result.replace(/^data:[^,]+,/, ""));
            reader.onerror = reject;
            reader.readAsDataURL(blob);
        });

        const filename = `${reportName}.pdf`;
        const printed = await directPrint.printPDF(base64, printerName, filename, copies);
        if (printed) return true;
    } catch (e) {
        console.warn("[DirectPrint] Failed to direct-print, falling back:", e);
    }

    return false;
}

registry.category("ir.actions.report handlers").add("direct_print_handler", directPrintReportHandler);
