/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/services/pos_store";

patch(PosStore.prototype, {
    // Inject company_name and customer_count so both the XML template
    // and the Epson JS builder can use them without separate lookups.
    getOrderData(order, reprint) {
        const result = super.getOrderData(order, reprint);
        result.company_name = this.company?.name || this.config?.name || "";
        result.customer_count = order.getCustomerCount?.() ?? 0;
        return result;
    },

    async printOrderChanges(data, printer) {
        const el = buildKitchenReceipt(data, {
            companyName: data.company_name || this.company?.name || this.config?.name || "",
        });
        const result = await printer.printReceipt(el);
        if (!result?.successful) {
            // Printer unavailable — open browser print dialog so the ticket
            // is never lost. Return successful:true to suppress RetryPrintPopup.
            openBrowserPrintFallback(el, data);
            return { successful: true };
        }
        return result;
    },
});

function buildKitchenReceipt(data, { companyName = "" } = {}) {
    const hasChanges =
        data.changes?.data?.length || data.changes?.groupedData || data.changes?.title;

    let linesHtml = "";

    if (hasChanges) {
        const titleHtml = data.changes.title
            ? `<div style="text-align:center;font-size:140%;font-weight:900;margin-bottom:10px;letter-spacing:2px;">${esc(data.changes.title)}</div>`
            : "";

        if (data.changes.groupedData) {
            for (const group of data.changes.groupedData) {
                linesHtml += `<div style="font-size:120%;font-weight:900;border-bottom:3px solid black;padding-bottom:2px;margin:12px 0 6px 0;">${esc(group.name)}</div>`;
                for (const line of group.data) {
                    linesHtml += renderLine(line);
                }
            }
        } else {
            for (const line of data.changes.data || []) {
                linesHtml += renderLine(line);
            }
        }
        linesHtml = titleHtml + linesHtml;
    } else if (data.internal_note) {
        linesHtml = `
            <div style="text-align:center;font-size:130%;font-weight:900;margin-bottom:6px;">ΕΣΩΤΕΡΙΚΗ ΣΗΜΕΙΩΣΗ</div>
            <div style="text-align:center;font-size:150%;font-weight:700;">${esc(data.internal_note)}</div>`;
    } else if (data.general_customer_note) {
        linesHtml = `
            <div style="text-align:center;font-size:130%;font-weight:900;margin-bottom:6px;">ΣΗΜΕΙΩΣΗ ΠΕΛΑΤΗ</div>
            <div style="text-align:center;font-size:150%;font-weight:700;">${esc(data.general_customer_note)}</div>`;
    }

    const guestHtml = data.customer_count
        ? `<div style="font-size:130%;font-weight:600;margin-bottom:4px;">ΕΠΙΣΚΕΠΤΕΣ: ${esc(String(data.customer_count))}</div>`
        : "";

    const reprintHtml = data.reprint
        ? `<div style="font-size:130%;font-weight:900;margin-top:8px;border:3px solid black;display:inline-block;padding:2px 12px;">*** ΑΝΤΙΓΡΑΦΟ ***</div>`
        : "";

    const html = `
        <div style="font-family:Arial,sans-serif;width:560px;background:#fff;padding:0;margin:0;">
            <div style="text-align:center;padding:14px 8px 8px 8px;">
                <div style="font-size:190%;font-weight:900;letter-spacing:1px;line-height:1.2;">${esc(companyName)}</div>
                <div style="font-size:140%;font-weight:700;letter-spacing:2px;margin-top:4px;">ΠΑΡΑΓΓΕΛΙΟΛΗΨΙΑ</div>
            </div>
            <hr style="border:none;border-top:5px solid black;margin:4px 0;"/>
            <div style="text-align:center;padding:8px 4px;">
                <div style="font-size:280%;font-weight:900;letter-spacing:3px;line-height:1;margin-bottom:6px;">${esc(data.pos_reference)}</div>
                ${guestHtml}
                <div style="font-size:120%;margin-top:4px;">
                    <strong>${esc(data.employee_name || "")}</strong>
                    <span style="margin:0 10px;">|</span>
                    ${esc(data.time || "")}
                </div>
                ${reprintHtml}
            </div>
            <hr style="border:none;border-top:5px dashed black;margin:4px 0;"/>
            <div style="padding:6px 8px 16px 8px;">
                ${linesHtml}
            </div>
            <hr style="border:none;border-top:3px solid black;margin:4px 0 20px 0;"/>
        </div>`;

    const wrapper = document.createElement("div");
    wrapper.innerHTML = html.trim();
    return wrapper.firstElementChild;
}

function renderLine(line) {
    const attrs = (line.attribute_value_names || [])
        .map((a) => `<div style="font-size:150%;font-weight:600;color:#333;">+ ${esc(a)}</div>`)
        .join("");
    const attrBlock = attrs
        ? `<div style="margin-left:50px;margin-top:4px;">${attrs}</div>`
        : "";

    const note = line.note
        ? `<div style="margin-left:50px;margin-top:6px;font-size:150%;font-weight:700;font-style:italic;background:#eee;padding:3px 8px;border-left:5px solid #333;">${esc(line.note)}</div>`
        : "";
    const custNote = line.customer_note
        ? `<div style="margin-left:50px;margin-top:6px;font-size:150%;font-weight:700;font-style:italic;background:#eee;padding:3px 8px;border-left:5px solid #333;">${esc(line.customer_note)}</div>`
        : "";
    const indent = line.combo_parent_uuid ? "margin-left:24px;" : "";

    return `
        <div style="margin-bottom:12px;padding-bottom:8px;border-bottom:1px dashed #666;${indent}">
            <div>
                <span style="font-size:240%;font-weight:900;margin-right:12px;">${esc(String(line.quantity))}</span>
                <span style="font-size:200%;font-weight:700;">${esc(line.basic_name)}</span>
            </div>
            ${attrBlock}${note}${custNote}
        </div>`;
}

/**
 * When the preparation printer is unreachable, open a browser print dialog so
 * the ticket is not lost. Uses window.open() for a clean print preview.
 * Falls back to an injected iframe if the popup is blocked.
 */
function openBrowserPrintFallback(el, data) {
    const ref = esc(data.pos_reference || "");
    const html = `<!DOCTYPE html><html>
<head>
    <meta charset="utf-8">
    <title>Kitchen Receipt ${ref}</title>
    <style>
        body { margin: 0; background: #f0f0f0; display: flex; flex-direction: column; align-items: center; }
        .toolbar {
            width: 100%; background: #c0392b; color: white; padding: 12px 16px;
            box-sizing: border-box; text-align: center; font-family: Arial, sans-serif;
        }
        .toolbar strong { font-size: 15px; display: block; margin-bottom: 8px; }
        .toolbar button {
            padding: 10px 22px; margin: 4px; font-size: 14px; cursor: pointer;
            border: none; border-radius: 4px; font-weight: bold;
        }
        .print-btn { background: #27ae60; color: white; }
        .close-btn { background: #555; color: white; }
        @media print { .toolbar { display: none; } body { background: white; } }
    </style>
</head>
<body>
    <div class="toolbar">
        <strong>⚠️ Εκτυπωτής μη διαθέσιμος — ${ref}</strong>
        <div>
            <button class="print-btn" onclick="window.print()">🖨️ Εκτύπωση / Αποθήκευση PDF</button>
            <button class="close-btn" onclick="window.close()">✕ Κλείσιμο</button>
        </div>
    </div>
    ${el.outerHTML}
    <script>setTimeout(function(){ window.print(); }, 400);<\/script>
</body></html>`;

    const win = window.open("", "_blank", "width=680,height=900");
    if (win) {
        win.document.write(html);
        win.document.close();
        win.focus();
        return;
    }

    // Popup blocked — inject an overlay iframe instead
    const existing = document.getElementById("_pos_print_fallback");
    if (existing) existing.remove();

    const frame = document.createElement("iframe");
    frame.id = "_pos_print_fallback";
    frame.style.cssText =
        "position:fixed;top:0;left:0;width:100%;height:100%;border:none;z-index:99999;background:white;";
    document.body.appendChild(frame);
    frame.contentDocument.open();
    frame.contentDocument.write(
        html.replace(
            "window.close()",
            "parent.document.getElementById('_pos_print_fallback').remove()"
        )
    );
    frame.contentDocument.close();
}

function esc(str) {
    return String(str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
}
