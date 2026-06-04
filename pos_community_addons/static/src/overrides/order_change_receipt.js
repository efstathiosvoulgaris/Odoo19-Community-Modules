import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/services/pos_store";

patch(PosStore.prototype, {
    async printOrderChanges(data, printer) {
        const el = buildKitchenReceipt(data, {
            companyName: this.company?.name || this.config?.name || "",
        });
        return await printer.printReceipt(el);
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
            <div style="text-align:center;font-size:130%;font-weight:900;margin-bottom:6px;">ESOTERIKH SIMEIOSH</div>
            <div style="text-align:center;font-size:150%;font-weight:700;">${esc(data.internal_note)}</div>`;
    } else if (data.general_customer_note) {
        linesHtml = `
            <div style="text-align:center;font-size:130%;font-weight:900;margin-bottom:6px;">SEMEIVSE PELATE</div>
            <div style="text-align:center;font-size:150%;font-weight:700;">${esc(data.general_customer_note)}</div>`;
    }

    const guestHtml = data.customer_count
        ? `<div style="font-size:130%;font-weight:600;margin-bottom:4px;">Episkeptes: ${esc(String(data.customer_count))}</div>`
        : "";

    const reprintHtml = data.reprint
        ? `<div style="font-size:130%;font-weight:900;margin-top:8px;border:3px solid black;display:inline-block;padding:2px 12px;">*** ANTIGRAFO ***</div>`
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

function esc(str) {
    return String(str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
}
