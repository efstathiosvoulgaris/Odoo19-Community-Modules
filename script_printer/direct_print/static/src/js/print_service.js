/** @odoo-module **/

import { registry } from "@web/core/registry";
import { reactive } from "@odoo/owl";

const DEFAULT_AGENT_URL = "http://127.0.0.1:5000";
const RETRY_INTERVAL_MS = 10000;
const MAX_RETRIES = 12; // ~2 minutes total

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

async function _detectAgentUrl(preferredUrl) {
    // Try the preferred URL first, then scan nearby ports as fallback
    const urls = [preferredUrl];
    for (const port of [5000, 5001, 5002, 5003, 5004]) {
        const candidate = `http://127.0.0.1:${port}`;
        if (candidate !== preferredUrl) urls.push(candidate);
    }

    const results = await Promise.allSettled(
        urls.map(async (url) => {
            const controller = new AbortController();
            const t = setTimeout(() => controller.abort(), 2000);
            try {
                const resp = await fetch(`${url}/status`, { signal: controller.signal });
                if (resp.ok) {
                    const data = await resp.json();
                    if (data.status === "running") return url;
                }
                throw new Error("not running");
            } finally {
                clearTimeout(t);
            }
        })
    );

    for (const r of results) {
        if (r.status === "fulfilled") return r.value;
    }
    return preferredUrl; // keep preferred even if offline
}

export const directPrintService = {
    dependencies: ["notification"],

    start(env, { notification }) {
        const state = reactive({
            agentOnline: false,
            agentUrl: DEFAULT_AGENT_URL,
            printers: [],
            routes: [],
            selectedPrinter: localStorage.getItem("direct_print_printer") || "",
            receiptPrinter: localStorage.getItem("direct_print_receipt_printer") || "",
        });

        const printQueue = [];
        let retryTimer = null;

        // ---- Internal helpers ----

        function _resolvePrinter(name) {
            return name || state.selectedPrinter || "";
        }

        function _notifyAgentUnreachable() {
            notification.add(
                "Print Agent not reachable. Is start_print_agent.bat running?",
                { type: "danger", sticky: true }
            );
            return false;
        }

        async function _fetch(path, options = {}) {
            const controller = new AbortController();
            const timeout = setTimeout(() => controller.abort(), 5000);
            try {
                return await fetch(`${state.agentUrl}${path}`, {
                    ...options,
                    signal: controller.signal,
                });
            } finally {
                clearTimeout(timeout);
            }
        }

        async function _logPrint(document_name, job_type, printer_name, status, copies = 1, error_message = null) {
            await _odooJson("/direct_print/log", {
                document_name,
                job_type,
                printer_name,
                status,
                copies,
                error_message,
            });
        }

        function _enqueueJob(jobFn, label) {
            if (printQueue.length >= 20) {
                notification.add("Print queue full — check that start_print_agent.bat is running.", {
                    type: "warning",
                });
                return;
            }
            printQueue.push(jobFn);
            notification.add(`${label} queued — Print Agent offline, retrying every 10 s…`, {
                type: "warning",
            });
            if (!retryTimer) {
                let attempts = 0;
                retryTimer = setInterval(async () => {
                    attempts++;
                    if (printQueue.length > 0) {
                        const online = await checkAgent();
                        if (online) {
                            const jobs = printQueue.splice(0);
                            for (const job of jobs) await job();
                        }
                    }
                    if (printQueue.length === 0 || attempts >= MAX_RETRIES) {
                        clearInterval(retryTimer);
                        retryTimer = null;
                    }
                }, RETRY_INTERVAL_MS);
            }
        }

        // ---- Public API ----

        async function checkAgent() {
            let online = false;
            try {
                const resp = await _fetch("/status");
                if (resp.ok) online = true;
            } catch {}
            if (state.agentOnline !== online) state.agentOnline = online;
            return online;
        }

        async function loadPrinters() {
            try {
                const resp = await _fetch("/get_printers");
                if (resp.ok) {
                    const data = await resp.json();
                    state.printers = data.printers || [];
                    if (!state.selectedPrinter) {
                        const def = state.printers.find((p) => p.is_default);
                        if (def) state.selectedPrinter = def.name;
                    }
                    return state.printers;
                }
            } catch {
                // ignore
            }
            return [];
        }

        async function loadRoutes() {
            const routes = await _odooJson("/direct_print/routes");
            state.routes = routes || [];
            return state.routes;
        }

        function getRoute(reportName) {
            return state.routes.find((r) => r.report_name === reportName) || null;
        }

        async function printPDF(base64Data, printerName, filename, copies = 1) {
            const printer = _resolvePrinter(printerName);

            const doprint = async () => {
                try {
                    const resp = await _fetch("/print_pdf", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({
                            data: base64Data,
                            printer_name: printer || undefined,
                            filename: filename || "report.pdf",
                            copies,
                        }),
                    });
                    const result = await resp.json();
                    if (resp.ok) {
                        const label = copies > 1 ? `${copies}× ` : "";
                        notification.add(`Printed ${label}to ${result.printer}`, {
                            type: "success",
                            sticky: false,
                        });
                        await _logPrint(filename || "report.pdf", "pdf", result.printer, "success", copies);
                        return true;
                    } else {
                        notification.add(`Print failed: ${result.error}`, { type: "danger", sticky: true });
                        await _logPrint(filename || "report.pdf", "pdf", printer || "(default)", "error", copies, result.error);
                        return false;
                    }
                } catch {
                    return _notifyAgentUnreachable();
                }
            };

            if (!state.agentOnline) {
                _enqueueJob(doprint, filename || "PDF report");
                return false;
            }
            return doprint();
        }

        async function printReceipt(content, printerName) {
            const printer = printerName || state.receiptPrinter || state.selectedPrinter;
            if (!printer) {
                notification.add(
                    "No receipt printer configured. Set one in Direct Print → Settings.",
                    { type: "warning", sticky: true }
                );
                return false;
            }
            try {
                const resp = await _fetch("/print_receipt", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ content, printer_name: printer }),
                });
                const result = await resp.json();
                if (resp.ok) {
                    await _logPrint("POS Receipt", "receipt", printer, "success");
                    return true;
                } else {
                    notification.add(`Receipt print failed: ${result.error}`, { type: "danger" });
                    await _logPrint("POS Receipt", "receipt", printer, "error", 1, result.error);
                    return false;
                }
            } catch {
                return _notifyAgentUnreachable();
            }
        }

        async function printHTML(html, printerName) {
            const printer = _resolvePrinter(printerName);
            try {
                const resp = await _fetch("/print_html", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ html, printer_name: printer || undefined }),
                });
                const result = await resp.json();
                if (resp.ok) {
                    await _logPrint("HTML Receipt", "html", printer || "(default)", "success");
                    return true;
                } else {
                    notification.add(`HTML print failed: ${result.error}`, { type: "danger" });
                    await _logPrint("HTML Receipt", "html", printer || "(default)", "error", 1, result.error);
                    return false;
                }
            } catch {
                return _notifyAgentUnreachable();
            }
        }

        async function printLabel(base64Data, printerName, filename) {
            const printer = _resolvePrinter(printerName);
            try {
                const resp = await _fetch("/print_label", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        data: base64Data,
                        printer_name: printer || undefined,
                        filename: filename || "label.pdf",
                    }),
                });
                const result = await resp.json();
                if (resp.ok) {
                    notification.add(`Label printed to ${result.printer}`, { type: "success" });
                    await _logPrint(filename || "label.pdf", "label", result.printer, "success");
                    return true;
                } else {
                    notification.add(`Label print failed: ${result.error}`, { type: "danger" });
                    await _logPrint(filename || "label.pdf", "label", printer || "(default)", "error", 1, result.error);
                    return false;
                }
            } catch {
                return _notifyAgentUnreachable();
            }
        }

        function setSelectedPrinter(name) {
            state.selectedPrinter = name;
            localStorage.setItem("direct_print_printer", name);
        }

        function setReceiptPrinter(name) {
            state.receiptPrinter = name;
            localStorage.setItem("direct_print_receipt_printer", name);
        }

        // Async startup: load config → detect agent URL → check online → load printers + routes
        (async () => {
            const config = await _odooJson("/direct_print/config");
            const preferredUrl = config?.agent_url || DEFAULT_AGENT_URL;
            state.agentUrl = await _detectAgentUrl(preferredUrl);

            const online = await checkAgent();
            if (online) {
                await Promise.all([loadPrinters(), loadRoutes()]);
            } else {
                loadRoutes().catch(() => {}); // routes come from Odoo, available even if agent is down
            }
        })();

        return {
            state,
            checkAgent,
            loadPrinters,
            loadRoutes,
            getRoute,
            printPDF,
            printReceipt,
            printHTML,
            printLabel,
            setSelectedPrinter,
            setReceiptPrinter,
        };
    },
};

registry.category("services").add("direct_print", directPrintService);
