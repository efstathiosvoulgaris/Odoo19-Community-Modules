/** Print Agent client: the PC's agent (script_printer/agent) prints the PDF
 * on the printer its settings page assigns — 80mm pages to the thermal, the
 * rest to the laser. Every caller falls back to the browser when this
 * returns false. */
const AGENT = "http://127.0.0.1:8765";
const headers = { "X-Print-Agent": "1" };

async function agentUp() {
    try {
        // Long on purpose: the first call waits on Chrome's «local network
        // access» prompt. A PC without the agent refuses at once anyway.
        const r = await fetch(`${AGENT}/status`, { headers, signal: AbortSignal.timeout(30000) });
        return r.ok;
    } catch (e) {
        console.info("[direct_print] no Print Agent:", e.message); // browser prints instead
        return false;
    }
}

/** Fetch `url` (an Odoo PDF) and hand it to the agent. True when printed. */
export async function agentPrint(url, notification) {
    if (!(await agentUp())) {
        return false;
    }
    try {
        const pdf = await fetch(url, { credentials: "same-origin" });
        if (!pdf.ok) {
            throw new Error(`PDF ${pdf.status}`);
        }
        const r = await fetch(`${AGENT}/print`, {
            method: "POST",
            headers: { ...headers, "Content-Type": "application/pdf" },
            body: await pdf.blob(),
            signal: AbortSignal.timeout(120000),
        });
        if (!r.ok) {
            throw new Error((await r.json().catch(() => ({}))).error || r.status);
        }
        return true;
    } catch (e) {
        notification?.add(`Print Agent: ${e.message} — εκτύπωση από τον browser.`, { type: "warning" });
        return false;
    }
}
