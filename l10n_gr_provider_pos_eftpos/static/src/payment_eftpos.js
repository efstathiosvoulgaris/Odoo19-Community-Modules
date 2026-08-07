import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { TextInputPopup } from "@point_of_sale/app/components/popups/text_input_popup/text_input_popup";
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";
import OrderPaymentValidation from "@point_of_sale/app/utils/order_payment_validation";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";

/**
 * Α.1155 EFT/POS flow for card payments in the POS.
 *
 * Before an order is validated, every card payment line (myDATA payment type
 * 7) that isn't signed yet gets a provider signature; the cashier charges the
 * terminal and types the transaction id back. The signature + transaction id
 * ride on the payment line to the invoice, which is transmitted with them.
 */
patch(OrderPaymentValidation.prototype, {
    _grIsCardLine(line) {
        // Card = a bank/terminal method, unless a manual myDATA override says
        // otherwise. Uses core fields (always loaded) so it can't go stale.
        //
        // Type 8 is deliberately excluded: that is IRIS *direct* (a QR Odoo
        // shows, paid to the merchant's IRIS id), which never reaches an
        // EFT/POS and is therefore outside Α.1155 — no terminal, no
        // terminalId, nothing to sign. IRIS chosen *on* the terminal arrives
        // here as an ordinary card line, because that is what it is.
        const pm = line.payment_method_id;
        if (!pm) {
            return false;
        }
        if (pm.l10n_gr_prov_payment_type) {
            return pm.l10n_gr_prov_payment_type === "7";
        }
        return pm.type === "bank" || pm.payment_method_type === "terminal";
    },

    _grVatRate(order) {
        // Only the VIVA signature strategy consumes vatRate; a mixed-rate
        // order sends 0, exactly like the backend flow does.
        const rates = new Set();
        for (const line of order.lines) {
            for (const tax of line.tax_ids || []) {
                rates.add(Math.round(tax.amount * 100) / 100);
            }
        }
        return rates.size === 1 ? [...rates][0] : 0;
    },

    _grEftEnabled() {
        // Only when this POS issues through the provider and a terminal is set.
        return Boolean(this.pos.config.l10n_gr_prov_alp_journal_id);
    },

    async askBeforeValidation() {
        if (!this._grEftEnabled()) {
            return await super.askBeforeValidation();
        }
        // Anything charged from here on is money already taken, so every path
        // that abandons the validation has to give it back.
        const charged = [];
        if (!(await this._grSignCardPayments(charged))) {
            await this._grVoidCharges(this.order, charged);
            return false;
        }
        const proceed = await super.askBeforeValidation();
        if (proceed === false) {
            await this._grVoidCharges(this.order, charged);
        }
        return proceed;
    },

    async _grSignCardPayments(charged) {
        const order = this.order;
        const cardLines = order.payment_ids.filter(
            (l) => this._grIsCardLine(l) && l.getAmount() > 0 && !l.l10n_gr_prov_eft_signature
        );
        for (const line of cardLines) {
            // 1. Request the provider signature for this card amount.
            let result;
            try {
                result = await this.pos.data.call(
                    "l10n.gr.prov.eft.terminal",
                    "l10n_gr_prov_pos_sign",
                    [
                        {
                            config_id: order.config_id.id,
                            amount: line.getAmount(),
                            net: order.priceExcl,
                            vat: order.amountTaxes,
                            gross: order.priceIncl,
                            vat_rate: this._grVatRate(order),
                            is_timologio: Boolean(order.to_invoice),
                        },
                    ]
                );
            } catch (e) {
                this.pos.dialog.add(AlertDialog, {
                    title: _t("Σφάλμα υπογραφής Α.1155"),
                    body: e?.message?.data?.message || e?.message || String(e),
                });
                return false;
            }
            if (!result || result.error) {
                this.pos.dialog.add(AlertDialog, {
                    title: _t("Αποτυχία λήψης υπογραφής"),
                    body: result?.error || _t("Άγνωστο σφάλμα."),
                });
                return false;
            }

            // 2. The transaction id. With the MegEftPos Driver the card was
            // already charged server-side and it came back with the
            // signature; a standalone terminal is charged by hand.
            let txId = result.transaction_id;
            if (!txId) {
                txId = await makeAwaitable(this.pos.dialog, TextInputPopup, {
                    title: _t(
                        "Χρέωση κάρτας %s (Α.1155) — Ταυτότητα Συναλλαγής",
                        this.pos.env.utils.formatCurrency(line.getAmount())
                    ),
                    placeholder: _t("Ταυτότητα Συναλλαγής τερματικού"),
                });
                if (!txId) {
                    // Abandoned after signing — release the unused signature.
                    await this._grCancelSignature(order, result.signature);
                    return false;
                }
            }

            // 3. Stash on the payment line; synced to the invoice on save.
            line.l10n_gr_prov_eft_signature = result.signature;
            line.l10n_gr_prov_eft_signing_author = result.signing_author;
            line.l10n_gr_prov_eft_terminal_code = result.terminal_code;
            line.l10n_gr_prov_eft_transaction_id = String(txId).trim();
            // Only present on the driver path — this is what makes the charge
            // reversible, so it has to be stored before anything else can fail.
            line.l10n_gr_prov_eft_signed_content = result.signed_content;
            line.l10n_gr_prov_eft_signature_uid = result.signature_uid;
            line.l10n_gr_prov_eft_signature_ts = result.signature_ts;
            line.l10n_gr_prov_eft_ecr_reference = result.ecr_reference;
            line.l10n_gr_prov_eft_bank_auth_code = result.bank_auth_code;
            line.l10n_gr_prov_eft_receipt_number = result.receipt_number;
            if (result.transaction_id) {
                charged.push(line);
            }
        }
        return true;
    },

    /** A line the driver actually took money for, so it can be given back. */
    _grIsCharged(line) {
        return Boolean(
            line.l10n_gr_prov_eft_transaction_id && line.l10n_gr_prov_eft_signed_content
        );
    },

    async _grVoidCharge(order, line) {
        const result = await this.pos.data.call(
            "l10n.gr.prov.eft.terminal",
            "l10n_gr_prov_pos_void",
            [
                {
                    config_id: order.config_id.id,
                    amount: line.getAmount(),
                    net: order.priceExcl,
                    vat: order.amountTaxes,
                    gross: order.priceIncl,
                    signature: line.l10n_gr_prov_eft_signature,
                    signed_content: line.l10n_gr_prov_eft_signed_content,
                    signature_uid: line.l10n_gr_prov_eft_signature_uid,
                    signature_ts: line.l10n_gr_prov_eft_signature_ts,
                    transaction_id: line.l10n_gr_prov_eft_transaction_id,
                    ecr_reference: line.l10n_gr_prov_eft_ecr_reference,
                    bank_auth_code: line.l10n_gr_prov_eft_bank_auth_code,
                    receipt_number: line.l10n_gr_prov_eft_receipt_number,
                },
            ]
        );
        if (result?.ok) {
            // Clear the Α.1155 trail: this line no longer stands for a payment.
            for (const field of [
                "signature",
                "signing_author",
                "terminal_code",
                "transaction_id",
                "signed_content",
                "signature_uid",
                "signature_ts",
                "ecr_reference",
                "bank_auth_code",
                "receipt_number",
            ]) {
                line[`l10n_gr_prov_eft_${field}`] = false;
            }
        }
        return result;
    },

    /**
     * Give back every charge made during this validation attempt.
     *
     * A failure here is shown, never swallowed: the customer's money is on
     * the card and somebody has to reverse it from the terminal by hand.
     */
    async _grVoidCharges(order, lines) {
        const failed = [];
        for (const line of lines) {
            let result;
            try {
                result = await this._grVoidCharge(order, line);
            } catch (e) {
                result = { error: e?.message?.data?.message || e?.message || String(e) };
            }
            if (!result?.ok) {
                failed.push(
                    `${this.pos.env.utils.formatCurrency(line.getAmount())}: ${
                        result?.error || _t("άγνωστο σφάλμα")
                    }`
                );
            }
        }
        if (failed.length) {
            this.pos.dialog.add(AlertDialog, {
                title: _t("Η χρέωση ΔΕΝ ακυρώθηκε"),
                body: _t(
                    "Έχει χρεωθεί κάρτα και η ακύρωση απέτυχε. Ακυρώστε τη " +
                        "συναλλαγή από το τερματικό.\n\n%s",
                    failed.join("\n")
                ),
            });
        }
    },

    async _grCancelSignature(order, signature) {
        try {
            await this.pos.data.call("l10n.gr.prov.eft.terminal", "l10n_gr_prov_pos_cancel", [
                { config_id: order.config_id.id, signature },
            ]);
        } catch {
            // best-effort; the provider auto-releases unused signatures after 24h
        }
    },
});

/**
 * Removing a payment line that the driver already charged has to give the
 * money back first — otherwise the card is debited and no document says so.
 */
patch(PaymentScreen.prototype, {
    deletePaymentLine(uuid) {
        const line = this.paymentLines.find((l) => l.uuid === uuid);
        // The screen builds a fresh validation object per action; do the same
        // rather than reimplement the void logic here.
        const validation = new OrderPaymentValidation({
            pos: this.pos,
            orderUuid: this.currentOrder.uuid,
        });
        if (!line || !validation._grIsCharged(line)) {
            return super.deletePaymentLine(uuid);
        }
        this.dialog.add(ConfirmationDialog, {
            title: _t("Ακύρωση χρέωσης κάρτας"),
            body: _t(
                "Η κάρτα έχει ήδη χρεωθεί %s. Η γραμμή θα αφαιρεθεί μόνο αν " +
                    "ακυρωθεί η συναλλαγή στο τερματικό.",
                this.pos.env.utils.formatCurrency(line.getAmount())
            ),
            confirmLabel: _t("Ακύρωση στο τερματικό"),
            confirm: async () => {
                await validation._grVoidCharges(this.currentOrder, [line]);
                // _grVoidCharges clears the trail only on success; a still
                // charged line stays put, with its own error already shown.
                if (!validation._grIsCharged(line)) {
                    super.deletePaymentLine(uuid);
                }
            },
        });
    },
});
