import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { TextInputPopup } from "@point_of_sale/app/components/popups/text_input_popup/text_input_popup";
import { NumberPopup } from "@point_of_sale/app/components/popups/number_popup/number_popup";
import { ask, makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";
import { uuidv4 } from "@point_of_sale/utils";
import OrderPaymentValidation from "@point_of_sale/app/utils/order_payment_validation";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { GrTerminalDialog } from "./terminal_dialog";

/**
 * Α.1155 EFT/POS flow for card payments in the POS.
 *
 * Before an order is validated, every card payment line (myDATA payment type
 * 7) that isn't signed yet gets a provider signature; with the MegEftPos
 * Driver the card is charged server-side in the same call, otherwise the
 * cashier charges the terminal and types the transaction id back. The
 * signature + transaction id ride on the payment line to the invoice, which is
 * transmitted with them.
 *
 * Every attempt is recorded on the server (l10n.gr.prov.eft.payment) under a
 * key the till makes up, BEFORE the card is charged. When an answer is lost
 * the till asks what happened to that key instead of charging again.
 */
patch(OrderPaymentValidation.prototype, {
    _grIsCardLine(line) {
        // Card = a bank/terminal method, unless a manual myDATA override says
        // otherwise. Uses core fields (always loaded) so it can't go stale.
        //
        // Type 8 is excluded — but only until ILYDA answers question Α7.
        // The Α.1155 guide §7.1 lists signature fields for type 7 alone, which
        // is what this exclusion rests on; the myDATA 2.0.1 XSD, however, hangs
        // ProvidersSignature off any type 1-8 and documents its
        // EndToEndReferenceID as «για πληρωμές IRIS». So a type-8 line may well
        // need a signature and we are not giving it one.
        // ponytail: left as-is on purpose — signing blind would mint
        // signatures nothing spends, and an unused signature is an «Ανοιχτό
        // Παραστατικό» after 24h. Revisit when the answer lands.
        // IRIS chosen *on* the terminal arrives here as an ordinary card line,
        // because that is what it is.
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
        // Every line touched here holds a live provider signature, and a
        // signature left unused reaches AADE as an «Ανοιχτό Παραστατικό» after
        // 24h — so every path that abandons the validation has to release
        // them, and give back whatever money was taken.
        const touched = [];
        if (!(await this._grSignCardPayments(touched))) {
            await this._grVoidCharges(this.order, touched);
            return false;
        }
        const proceed = await super.askBeforeValidation();
        if (proceed === false) {
            await this._grVoidCharges(this.order, touched);
        }
        return proceed;
    },

    /**
     * Which terminal this charge runs on. With one terminal (or none) nothing
     * is asked and the server uses the till's default; with several the
     * cashier picks, the last pick on this till offered first. null = the
     * cashier backed out.
     */
    async _grChooseTerminal() {
        const terminals = this.pos.config.l10n_gr_prov_eft_terminal_choices || [];
        if (terminals.length < 2) {
            return terminals[0]?.id || false;
        }
        const storageKey = `l10n_gr_prov_eft_terminal_${this.pos.config.id}`;
        let last = null;
        try {
            last = Number(localStorage.getItem(storageKey)) || null;
        } catch {
            // private window or blocked storage: no preselection
        }
        const picked = await makeAwaitable(this.pos.dialog, GrTerminalDialog, {
            title: _t("Σε ποιο τερματικό θα γίνει η χρέωση;"),
            terminals,
            preselected: terminals.some((t) => t.id === last) ? last : terminals[0].id,
        });
        if (!picked) {
            return null;
        }
        try {
            localStorage.setItem(storageKey, String(picked));
        } catch {
            // not remembered; harmless
        }
        return picked;
    },

    /**
     * Δόσεις for this charge: 0 when the till doesn't offer them, null when
     * the cashier backed out. Asked BEFORE the signature is requested — the
     * signature is spent on the charge that follows it, so nothing may sit
     * between the two that the cashier can abandon.
     */
    async _grAskInstallments() {
        const max = this.pos.config.l10n_gr_prov_eft_max_installments || 0;
        if (max < 2) {
            return 0;
        }
        const answer = await makeAwaitable(this.pos.dialog, NumberPopup, {
            title: _t("Δόσεις (1 = εφάπαξ, έως %s)", max),
            startingValue: 1,
        });
        if (answer === undefined || answer === null || answer === "") {
            return null;
        }
        const count = Math.trunc(Number(answer));
        if (!(count >= 1 && count <= max)) {
            this._grAlert(_t("Μη έγκυρες δόσεις"), _t("Δώστε αριθμό από 1 έως %s.", max));
            return null;
        }
        return count;
    },

    /**
     * Sign — and with the driver, charge — every unsigned card line.
     *
     * A line whose attempt has no definite outcome can only be settled by
     * «Ανάκτηση»; nothing here charges it a second time.
     */
    async _grSignCardPayments(touched) {
        const order = this.order;
        // A return is a credit document, and §5.3 makes signature and
        // transactionId mandatory on every type-7 payment line — credit ones
        // included. Its amounts are negative in Odoo and positive on the wire,
        // like the credit document itself.
        // Judged by the amount, not `order.isRefund`: that flag is only set by
        // the Refund action, while an order typed in with negative quantities
        // is just as much a credit document. `_l10n_gr_prov_pos_journal()`
        // picks the credit series the same way.
        const isRefund = order.priceIncl < 0;
        const abs = (n) => Math.abs(n);
        const cardLines = order.payment_ids.filter(
            (l) => this._grIsCardLine(l) && l.getAmount() !== 0 && !l.l10n_gr_prov_eft_signature
        );
        for (const line of cardLines) {
            let result = null;

            // 0. An earlier attempt on this line never got a definite answer:
            // ask the server what became of it before anything else.
            if (line.l10n_gr_prov_eft_client_key) {
                result = await this._grCall("l10n_gr_prov_pos_status", order, {
                    client_key: line.l10n_gr_prov_eft_client_key,
                });
                if (!result) {
                    return false;
                }
                if (result.status === "unknown") {
                    if (!this._grAttemptExpired(line.l10n_gr_prov_eft_client_key)) {
                        // It may still be signing or charging on the server.
                        this._grAlert(
                            _t("Η προηγούμενη χρέωση δεν έχει ακόμη αποτέλεσμα"),
                            _t(
                                "ΜΗΝ χρεώσετε ξανά την κάρτα. Περιμένετε λίγο και " +
                                    "πατήστε ξανά Επικύρωση για να ελεγχθεί."
                            )
                        );
                        return false;
                    }
                    result = null; // never reached the server: start over
                } else if (["cancelled", "error"].includes(result.status)) {
                    result = null; // nothing charged: start over
                }
                if (!result) {
                    line.l10n_gr_prov_eft_client_key = false;
                }
            }

            // 1. A new attempt: Δόσεις first — the signature is spent on the
            // charge that follows it, so nothing the cashier can abandon may
            // sit between the two.
            if (!result) {
                const terminalId = await this._grChooseTerminal();
                if (terminalId === null) {
                    return false;
                }
                const installments = isRefund ? 0 : await this._grAskInstallments();
                if (installments === null) {
                    return false;
                }
                const key = `${Date.now()}-${uuidv4()}`;
                line.l10n_gr_prov_eft_client_key = key;
                try {
                    result = await this.pos.data.call(
                        "l10n.gr.prov.eft.terminal",
                        "l10n_gr_prov_pos_sign",
                        [
                            {
                                config_id: order.config_id.id,
                                client_key: key,
                                terminal_id: terminalId,
                                amount: abs(line.getAmount()),
                                net: abs(order.priceExcl),
                                vat: abs(order.amountTaxes),
                                gross: abs(order.priceIncl),
                                vat_rate: this._grVatRate(order),
                                is_timologio: Boolean(order.to_invoice),
                                is_refund: isRefund,
                                installments: installments,
                            },
                        ]
                    );
                } catch (e) {
                    // The answer was lost — not necessarily the charge. The
                    // key stays on the line; the next Επικύρωση asks for it.
                    this._grAlert(
                        _t("Χάθηκε η απάντηση του διακομιστή"),
                        _t(
                            "Η κάρτα ίσως χρεώθηκε — ΜΗΝ χρεώσετε ξανά. Πατήστε " +
                                "ξανά Επικύρωση για να ελεγχθεί η κατάσταση.\n\n%s",
                            this._grErrorText(e)
                        )
                    );
                    return false;
                }
            }

            // 2. Outcome unknown: only the terminal can tell.
            while (result.status === "pending") {
                const recover = await ask(this.pos.dialog, {
                    title: _t("Άγνωστη έκβαση χρέωσης"),
                    body: _t(
                        "%s\n\nΗ κάρτα ίσως χρεώθηκε — ΜΗΝ χρεώσετε ξανά. " +
                            "Να ρωτηθεί το τερματικό;",
                        result.error || ""
                    ),
                    confirmLabel: _t("Ανάκτηση"),
                    cancelLabel: _t("Αργότερα"),
                });
                if (!recover) {
                    return false;
                }
                const recovered = await this._grCall("l10n_gr_prov_pos_recover", order, {
                    client_key: line.l10n_gr_prov_eft_client_key,
                });
                if (!recovered) {
                    return false;
                }
                result = recovered;
            }
            if (result.status !== "approved" && result.status !== "signed") {
                line.l10n_gr_prov_eft_client_key = false;
                this._grAlert(
                    _t("Η χρέωση δεν ολοκληρώθηκε"),
                    result.error || _t("Άγνωστο σφάλμα.")
                );
                return false;
            }

            // 3. The transaction id. With the MegEftPos Driver the card was
            // already charged server-side; a standalone terminal (and any
            // return) is charged by hand.
            let txId = result.transaction_id;
            if (result.status === "signed") {
                if (this.pos.config.l10n_gr_prov_eft_require_signature && !isRefund) {
                    // This till may not take a card without the terminal having
                    // answered for it — a typed transaction id is a promise, not
                    // a proof. Returns are exempt: they are always keyed in by
                    // hand, so the rule would make card refunds impossible.
                    await this._grRelease(order, line);
                    this._grAlert(
                        _t("Το τερματικό δεν απάντησε"),
                        _t(
                            "Το ταμείο απαιτεί χρέωση μέσω του τερματικού. " +
                                "Επαναλάβετε ή επιλέξτε άλλον τρόπο πληρωμής."
                        )
                    );
                    return false;
                }
                txId = await makeAwaitable(this.pos.dialog, TextInputPopup, {
                    title: isRefund
                        ? _t(
                              "Επιστροφή %s στην κάρτα (Α.1155) — κάντε την " +
                                  "επιστροφή στο τερματικό και καταχωρίστε την " +
                                  "Ταυτότητα Συναλλαγής",
                              this.pos.env.utils.formatCurrency(abs(line.getAmount()))
                          )
                        : _t(
                              "Χρέωση κάρτας %s (Α.1155) — Ταυτότητα Συναλλαγής",
                              this.pos.env.utils.formatCurrency(line.getAmount())
                          ),
                    placeholder: _t("Ταυτότητα Συναλλαγής τερματικού"),
                });
                if (!txId) {
                    // Abandoned after signing — release the unused signature.
                    await this._grRelease(order, line);
                    return false;
                }
            }

            // 4. Stash on the payment line; synced to the invoice on save. The
            // references a Void needs stay on the server-side record.
            line.l10n_gr_prov_eft_signature = result.signature;
            line.l10n_gr_prov_eft_signing_author = result.signing_author;
            line.l10n_gr_prov_eft_terminal_code = result.terminal_code;
            line.l10n_gr_prov_eft_transaction_id = String(txId).trim();
            // Every signed line, not only the driver-charged ones: a manually
            // charged line holds a signature that has to be released too.
            touched.push(line);
        }
        return true;
    },

    /** Attempt keys start with their creation time (ms). */
    _grAttemptExpired(key) {
        // Longer than the driver's own timeout (210s) plus the provider's
        // (90s): past this, an attempt the server never recorded never will.
        const created = Number(String(key).split("-")[0]);
        return !created || Date.now() - created > 6 * 60 * 1000;
    },

    async _grCall(method, order, vals) {
        try {
            return await this.pos.data.call("l10n.gr.prov.eft.terminal", method, [
                { config_id: order.config_id.id, ...vals },
            ]);
        } catch (e) {
            this._grAlert(_t("Σφάλμα επικοινωνίας Α.1155"), this._grErrorText(e));
            return null;
        }
    },

    _grAlert(title, body) {
        this.pos.dialog.add(AlertDialog, { title, body });
    },

    _grErrorText(e) {
        return e?.data?.message || e?.message?.data?.message || e?.message || String(e);
    },

    /**
     * Give a line's attempt back: the server voids a driver charge from its
     * own record and cancels the signature. Returns the server's answer.
     */
    async _grRelease(order, line) {
        if (!line.l10n_gr_prov_eft_client_key) {
            this._grClearLine(line);
            return { ok: true, voided: false };
        }
        let result;
        try {
            result = await this.pos.data.call(
                "l10n.gr.prov.eft.terminal",
                "l10n_gr_prov_pos_release",
                [{ config_id: order.config_id.id, client_key: line.l10n_gr_prov_eft_client_key }]
            );
        } catch (e) {
            result = { error: this._grErrorText(e) };
        }
        if (result?.ok) {
            this._grClearLine(line);
        }
        return result;
    },

    /** The line no longer stands for a payment: drop the Α.1155 trail. */
    _grClearLine(line) {
        for (const field of [
            "signature",
            "signing_author",
            "terminal_code",
            "transaction_id",
            "client_key",
            "signed_content",
            "signature_uid",
            "signature_ts",
            "ecr_reference",
            "bank_auth_code",
            "receipt_number",
        ]) {
            line[`l10n_gr_prov_eft_${field}`] = false;
        }
    },

    /**
     * Unwind every line touched during this validation attempt.
     *
     * Driver-charged lines are voided on the terminal, which also releases
     * their signature. A line the cashier charged by hand cannot be voided
     * from here — only its signature is released, and the cashier is told to
     * reverse the money on the terminal themselves.
     *
     * A failure is shown, never swallowed: the customer's money is on the card
     * and somebody has to reverse it from the terminal by hand.
     */
    async _grVoidCharges(order, lines) {
        const failed = [];
        const manual = [];
        for (const line of lines) {
            const amount = this.pos.env.utils.formatCurrency(line.getAmount());
            const typedByHand = Boolean(line.l10n_gr_prov_eft_transaction_id);
            const result = await this._grRelease(order, line);
            if (!result?.ok) {
                failed.push(`${amount}: ${result?.error || _t("άγνωστο σφάλμα")}`);
            } else if (!result.voided && typedByHand) {
                manual.push(amount);
            }
        }
        if (failed.length) {
            this._grAlert(
                _t("Η χρέωση ΔΕΝ ακυρώθηκε"),
                _t(
                    "Έχει χρεωθεί κάρτα και η ακύρωση απέτυχε. Ακυρώστε τη " +
                        "συναλλαγή από το τερματικό.\n\n%s",
                    failed.join("\n")
                )
            );
        }
        if (manual.length) {
            this._grAlert(
                _t("Ακυρώστε τη συναλλαγή στο τερματικό"),
                _t(
                    "Η υπογραφή ακυρώθηκε, αλλά η κάρτα χρεώθηκε χειροκίνητα " +
                        "και δεν μπορεί να ακυρωθεί από εδώ. Ακυρώστε τη " +
                        "συναλλαγή στο τερματικό.\n\n%s",
                    manual.join("\n")
                )
            );
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
        if (line?.l10n_gr_prov_eft_client_key && !line.l10n_gr_prov_eft_signature) {
            // An attempt with no definite outcome: the card may be charged,
            // and deleting the line would drop the only handle on it here.
            this.dialog.add(AlertDialog, {
                title: _t("Εκκρεμής χρέωση κάρτας"),
                body: _t(
                    "Η χρέωση αυτής της γραμμής έχει άγνωστη έκβαση. Πατήστε " +
                        "Επικύρωση για να ελεγχθεί, ή λύστε την από Λογιστική → " +
                        "myDATA → Πληρωμές EFT/POS."
                ),
            });
            return;
        }
        // Any signed line, not only a driver-charged one: a manually charged
        // line still holds a live signature that has to be released.
        if (!line || !line.l10n_gr_prov_eft_signature) {
            return super.deletePaymentLine(uuid);
        }
        // The screen builds a fresh validation object per action; do the same
        // rather than reimplement the void logic here.
        const validation = new OrderPaymentValidation({
            pos: this.pos,
            orderUuid: this.currentOrder.uuid,
        });
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
                // The trail is cleared only once the line no longer stands for
                // a payment; a failed void leaves it in place, with its own
                // error already shown.
                if (!line.l10n_gr_prov_eft_signature) {
                    super.deletePaymentLine(uuid);
                }
            },
        });
    },
});
