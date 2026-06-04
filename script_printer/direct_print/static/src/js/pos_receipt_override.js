/** @odoo-module **/
/**
 * POS Receipt Print Override
 * ==========================
 * Patches the POS order model to intercept receipt printing and send
 * the receipt content to the local print agent for thermal printer output.
 *
 * This works alongside the standard POS receipt flow — if the print agent
 * is offline, it falls back to the default browser-based printing.
 */

import { patch } from "@web/core/utils/patch";
import { ReceiptScreen } from "@point_of_sale/app/screens/receipt_screen/receipt_screen";

// ---------------------------------------------------------------------------
// Patch ReceiptScreen to intercept the print action
// ---------------------------------------------------------------------------
patch(ReceiptScreen.prototype, {
    /**
     * Override the print receipt method.
     * Attempts to send the receipt to the local print agent first.
     * Falls back to default behavior if the agent is unavailable.
     */
    async onClickPrintReceipt() {
        const directPrint = this.env.services.direct_print;

        if (directPrint && directPrint.state.agentOnline && directPrint.state.receiptPrinter) {
            try {
                const receiptEl = document.querySelector(".pos-receipt");
                if (receiptEl) {
                    // Try raw text for thermal printers first
                    const receiptData = this._getReceiptText();
                    if (receiptData) {
                        const printed = await directPrint.printReceipt(
                            receiptData,
                            directPrint.state.receiptPrinter
                        );
                        if (printed) {
                            return;
                        }
                    }

                    // Fallback: send as HTML
                    const fullHTML = `
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body { font-family: monospace; font-size: 12px; width: 80mm; margin: 0 auto; }
        .pos-receipt { padding: 5mm; }
        table { width: 100%; border-collapse: collapse; }
        td { padding: 2px 0; }
        .pos-receipt-right-align { text-align: right; }
        .pos-receipt-center-align { text-align: center; }
        hr { border: none; border-top: 1px dashed #000; }
    </style>
</head>
<body>${receiptEl.outerHTML}</body>
</html>`;

                    const printed = await directPrint.printHTML(
                        fullHTML,
                        directPrint.state.receiptPrinter
                    );
                    if (printed) {
                        return;
                    }
                }
            } catch (e) {
                console.warn("[DirectPrint] POS receipt print failed, falling back:", e);
            }
        }

        // Default Odoo behavior
        return super.onClickPrintReceipt(...arguments);
    },

    /**
     * Extract plain text from the receipt for raw thermal printing.
     * Returns a simple text representation suitable for ESC/POS printers.
     */
    _getReceiptText() {
        try {
            const order = this.pos.get_order();
            if (!order) return null;

            const receiptData = order.export_for_printing();
            if (!receiptData) return null;

            const lines = [];
            const W = 42; // 42 chars width for 80mm thermal paper

            // Helper to center text
            const center = (text) => {
                const pad = Math.max(0, Math.floor((W - text.length) / 2));
                return " ".repeat(pad) + text;
            };

            // Helper for left-right aligned line
            const leftRight = (left, right) => {
                const space = Math.max(1, W - left.length - right.length);
                return left + " ".repeat(space) + right;
            };

            const divider = "-".repeat(W);

            // Header
            if (receiptData.company?.name) {
                lines.push(center(receiptData.company.name));
            }
            if (receiptData.company?.phone) {
                lines.push(center(`Tel: ${receiptData.company.phone}`));
            }
            lines.push(divider);

            // Order info
            if (receiptData.name) {
                lines.push(`Order: ${receiptData.name}`);
            }
            if (receiptData.date?.localestring) {
                lines.push(`Date: ${receiptData.date.localestring}`);
            }
            if (receiptData.cashier) {
                lines.push(`Cashier: ${receiptData.cashier}`);
            }
            if (receiptData.headerData?.partner_name) {
                lines.push(`Customer: ${receiptData.headerData.partner_name}`);
            }
            lines.push(divider);

            // Order lines
            if (receiptData.orderlines) {
                for (const line of receiptData.orderlines) {
                    const name = line.product_name || line.full_product_name || "Item";
                    const qty = line.quantity || 1;
                    const price = (line.price || 0).toFixed(2);

                    if (qty !== 1) {
                        lines.push(name);
                        lines.push(leftRight(`  ${qty} x ${(line.price / qty).toFixed(2)}`, price));
                    } else {
                        lines.push(leftRight(name, price));
                    }

                    if (line.discount && line.discount > 0) {
                        lines.push(`  Discount: ${line.discount}%`);
                    }
                }
            }
            lines.push(divider);

            // Totals
            if (receiptData.subtotal !== undefined) {
                lines.push(leftRight("Subtotal:", receiptData.subtotal.toFixed(2)));
            }
            if (receiptData.tax_details) {
                for (const tax of receiptData.tax_details) {
                    lines.push(leftRight(`Tax ${tax.name || ""}:`, (tax.amount || 0).toFixed(2)));
                }
            }
            lines.push(divider);
            const total = receiptData.total_with_tax || receiptData.amount_total || 0;
            lines.push(leftRight("TOTAL:", total.toFixed(2)));
            lines.push(divider);

            // Payments
            if (receiptData.paymentlines) {
                for (const pl of receiptData.paymentlines) {
                    lines.push(leftRight(pl.name || "Payment", (pl.amount || 0).toFixed(2)));
                }
            }
            if (receiptData.change !== undefined && receiptData.change > 0) {
                lines.push(leftRight("Change:", receiptData.change.toFixed(2)));
            }

            lines.push("");
            lines.push(center("Thank you!"));
            lines.push("");
            lines.push("");
            lines.push(""); // Extra lines for paper feed

            return lines.join("\n");
        } catch (e) {
            console.warn("[DirectPrint] Could not generate receipt text:", e);
            return null;
        }
    },
});
