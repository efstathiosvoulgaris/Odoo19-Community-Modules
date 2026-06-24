/** @odoo-module **/

import { ReceiptScreen } from "@point_of_sale/app/screens/receipt_screen/receipt_screen";
import { OrderReceipt } from "@point_of_sale/app/screens/receipt_screen/receipt/order_receipt";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { PosOrderline } from "@point_of_sale/app/models/pos_order_line";
import { patch } from "@web/core/utils/patch";
import { onMounted } from "@odoo/owl";

// ---------------------------------------------------------------------------
// After payment: auto-print receipt then go straight back to floor plan.
// ---------------------------------------------------------------------------
patch(ReceiptScreen.prototype, {
    setup() {
        super.setup();
        onMounted(async () => {
            try {
                await this.pos.printReceipt({ order: this.currentOrder });
            } catch (e) {
                // Error already handled by PosStore.printReceipt patch below;
                // this catch is a safety net only.
                console.error("Receipt print failed:", e);
            }
            this.pos.orderDone(this.currentOrder);
        });
    },
});

// ---------------------------------------------------------------------------
// Receipt printer fallback — covers both payment receipt and ticket-list reprint.
// When the receipt printer is unreachable, render the receipt to HTML and open
// a browser print dialog instead of showing an error.
// ---------------------------------------------------------------------------
patch(PosStore.prototype, {
    async printReceipt(args = {}) {
        const order = args.order || this.getOrder();
        try {
            return await super.printReceipt(args);
        } catch (e) {
            console.warn("Receipt printer unavailable, using browser print:", e);
            try {
                const el = await this.printer.renderer.toHtml(OrderReceipt, {
                    order,
                    basic_receipt: args.basic || false,
                });
                openReceiptBrowserPrint(el, order);
            } catch (renderErr) {
                console.error("Could not render receipt for browser print:", renderErr);
            }
            // Return truthy so nb_print counter increments and no error dialog appears.
            return { successful: true };
        }
    },
});

// ---------------------------------------------------------------------------
// note is always a JSON array string e.g. '[{"text":"ZAZOS","colorIndex":0}]'
// ---------------------------------------------------------------------------
patch(PosOrderline.prototype, {
    get noteText() {
        try {
            const parsed = JSON.parse(this.note);
            if (Array.isArray(parsed)) return parsed.map((p) => p.text || "").join(" ").trim();
        } catch {}
        return this.note || "";
    },
});

// Replace Odoo's default receipt with our clean customer receipt.
OrderReceipt.template = "pos_community_addons.CustomerReceipt";

// ---------------------------------------------------------------------------
// Browser print fallback for receipt printer failures.
// Opens a new tab with the receipt HTML and auto-triggers window.print().
// Falls back to an iframe overlay if popups are blocked.
// ---------------------------------------------------------------------------
function openReceiptBrowserPrint(el, order) {
    const ref = order?.pos_reference || order?.getName?.() || "";
    const table = order?.table_id
        ? "ΤΡΑΠΕΖΙ " + (order.table_id.table_name || order.table_id.table_number)
        : "";

    const html = `<!DOCTYPE html><html>
<head>
    <meta charset="utf-8">
    <title>Απόδειξη ${escHtml(ref)}</title>
    <style>
        body { margin: 0; background: #f0f0f0; display: flex; flex-direction: column; align-items: center; }
        .toolbar {
            width: 100%; background: #2c3e50; color: white; padding: 12px 16px;
            box-sizing: border-box; text-align: center; font-family: Arial, sans-serif;
        }
        .toolbar strong { font-size: 15px; display: block; margin-bottom: 8px; }
        .toolbar button {
            padding: 10px 22px; margin: 4px; font-size: 14px; cursor: pointer;
            border: none; border-radius: 4px; font-weight: bold;
        }
        .print-btn { background: #27ae60; color: white; }
        .close-btn { background: #7f8c8d; color: white; }
        .receipt-wrap { background: white; margin: 16px; padding: 16px; border-radius: 4px; }
        @media print { .toolbar { display: none; } body { background: white; } .receipt-wrap { margin: 0; padding: 0; } }
    </style>
</head>
<body>
    <div class="toolbar">
        <strong>⚠️ Εκτυπωτής αποδείξεων μη διαθέσιμος${table ? " — " + escHtml(table) : ""} ${escHtml(ref)}</strong>
        <div>
            <button class="print-btn" onclick="window.print()">🖨️ Εκτύπωση / Αποθήκευση PDF</button>
            <button class="close-btn" onclick="window.close()">✕ Κλείσιμο</button>
        </div>
    </div>
    <div class="receipt-wrap">${el.outerHTML}</div>
    <script>setTimeout(function(){ window.print(); }, 400);<\/script>
</body></html>`;

    const win = window.open("", "_blank", "width=680,height=900");
    if (win) {
        win.document.write(html);
        win.document.close();
        win.focus();
        return;
    }

    // Popup blocked — inject fullscreen iframe instead.
    const existing = document.getElementById("_pos_receipt_fallback");
    if (existing) existing.remove();
    const frame = document.createElement("iframe");
    frame.id = "_pos_receipt_fallback";
    frame.style.cssText =
        "position:fixed;top:0;left:0;width:100%;height:100%;border:none;z-index:99999;background:white;";
    document.body.appendChild(frame);
    frame.contentDocument.open();
    frame.contentDocument.write(
        html.replace(
            "window.close()",
            "parent.document.getElementById('_pos_receipt_fallback').remove()"
        )
    );
    frame.contentDocument.close();
}

function escHtml(str) {
    return String(str || "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
}
