import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { TextInputPopup } from "@point_of_sale/app/components/popups/text_input_popup/text_input_popup";
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";
import OrderPaymentValidation from "@point_of_sale/app/utils/order_payment_validation";

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
        const pm = line.payment_method_id;
        if (!pm) {
            return false;
        }
        if (pm.l10n_gr_prov_payment_type) {
            return pm.l10n_gr_prov_payment_type === "7";
        }
        return pm.type === "bank" || pm.payment_method_type === "terminal";
    },

    _grEftEnabled() {
        // Only when this POS issues through the provider and a terminal is set.
        return Boolean(this.pos.config.l10n_gr_prov_alp_journal_id);
    },

    async askBeforeValidation() {
        if (this._grEftEnabled()) {
            const ok = await this._grSignCardPayments();
            if (!ok) {
                return false;
            }
        }
        return await super.askBeforeValidation();
    },

    async _grSignCardPayments() {
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

            // 2. Cashier charges the terminal, then types the transaction id.
            const txId = await makeAwaitable(this.pos.dialog, TextInputPopup, {
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

            // 3. Stash on the payment line; synced to the invoice on save.
            line.l10n_gr_prov_eft_signature = result.signature;
            line.l10n_gr_prov_eft_signing_author = result.signing_author;
            line.l10n_gr_prov_eft_terminal_code = result.terminal_code;
            line.l10n_gr_prov_eft_transaction_id = txId.trim();
        }
        return true;
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
