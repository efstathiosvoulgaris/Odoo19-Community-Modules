import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";

/**
 * Make the Send button exist without kitchen printers.
 *
 * Two separate gates hide it. ProductScreen.swapButton checks
 * preparationCategories.size, and the button itself is rendered only when
 * pos.categoryCount is non-empty — and that is built from getOrderChanges(),
 * which reports nothing at all unless the products sit in a preparation
 * category. A Greek restaurant with no kitchen printer therefore sees only
 * Νέα and Πληρωμή, yet still owes AADE a Δελτίο Παραγγελίας per round.
 */
patch(ProductScreen.prototype, {
    get swapButton() {
        if (this.pos.config.module_pos_restaurant && this.pos.config.l10n_gr_prov_enabled) {
            return true;
        }
        return super.swapButton;
    },
});

/**
 * Δελτίο Παραγγελίας Εστίασης (8.6).
 *
 * Each round the waiter sends to the kitchen becomes one order note. The
 * changes must be read BEFORE calling super, because sendOrderInPreparation
 * ends with order.updateLastOrderChange(), which is exactly what makes those
 * lines stop counting as "new".
 */
patch(PosStore.prototype, {
    _grCateringEnabled() {
        return Boolean(
            this.config.module_pos_restaurant &&
                this.config.l10n_gr_prov_enabled &&
                this.config.l10n_gr_prov_catering_notes
        );
    },

    /**
     * The Send button renders only when this is non-empty, and core builds it
     * from preparation categories alone. When none are configured, report the
     * round's pending items ourselves so the waiter can send — and so the note
     * gets issued. Untouched whenever core already has something to show.
     */
    getCategoryCount(order = this.getOrder()) {
        const base = super.getCategoryCount(order);
        if (base.length || !this._grCateringEnabled() || !order) {
            return base;
        }
        const pending = this._grRoundChanges(order).reduce(
            (n, c) => n + Math.abs(c.quantity),
            0
        );
        return pending ? [{ count: pending, name: _t("Παραγγελία") }] : [];
    },

    /**
     * What this round adds, for every product.
     *
     * Deliberately not core's changesToOrder(): that only reports lines whose
     * product sits in a kitchen-printer category, so a drink poured at the bar
     * would never reach the ΔΠ. The law wants everything the customer ordered.
     * updateLastOrderChange() records every line, so diffing against it is
     * safe and stays correct across rounds.
     */
    _grRoundChanges(order) {
        const previous = order.last_order_preparation_change?.lines || {};
        const changes = [];
        const live = new Set();
        for (const line of order.getOrderlines()) {
            const key = line.preparationKey;
            live.add(key);
            const sent = previous[key]?.quantity || 0;
            const quantity = line.getQuantity() - sent;
            if (quantity) {
                changes.push({
                    uuid: line.uuid,
                    prep_key: key,
                    quantity,
                    name: line.getFullProductName(),
                });
            }
        }
        // Lines the waiter deleted outright: the orderline is gone, but it was
        // transmitted, so it still owes AADE a negative note. The server prices
        // it from the original note row (`prep_key`).
        for (const [key, sent] of Object.entries(previous)) {
            if (!live.has(key) && sent.quantity) {
                changes.push({
                    uuid: null,
                    prep_key: key,
                    quantity: -sent.quantity,
                    name: sent.name || sent.display_name || "",
                });
            }
        }
        return changes;
    },

    /**
     * Money for the round: prorate each line's own net/VAT by the sent qty.
     * Cancelled items (negative quantity) carry no amounts — the server prices
     * them off the note that transmitted them, so the credit matches to the
     * cent even when the orderline no longer exists.
     */
    _grCateringLines(order, changes) {
        const lines = [];
        for (const change of changes) {
            if (change.quantity < 0) {
                lines.push({
                    name: change.name,
                    prep_key: change.prep_key,
                    quantity: change.quantity,
                });
                continue;
            }
            const line = order.lines.find((l) => l.uuid === change.uuid);
            if (!line) {
                continue;
            }
            const qty = line.getQuantity();
            if (!qty) {
                continue;
            }
            const share = change.quantity / qty;
            const net = line.priceExcl * share;
            const vat = (line.priceIncl - line.priceExcl) * share;
            // Derive the rate from the amounts rather than from tax_ids: it is
            // then guaranteed consistent with the vatAmount we transmit, even
            // when a fiscal position remapped the tax.
            const rate = net ? Math.round((vat / net) * 100) : line.tax_ids?.[0]?.amount || 0;
            lines.push({
                name: change.name || line.getFullProductName(),
                prep_key: change.prep_key,
                quantity: change.quantity,
                net: net,
                vat_amount: vat,
                vat_rate: rate,
            });
        }
        return lines;
    },

    /** getName() honours a renamed table (pos_community_addons). */
    _grTableName(order) {
        return (
            order.getTable?.()?.getName?.() ||
            order.getTable?.()?.table_number?.toString() ||
            ""
        );
    },

    /**
     * One RPC, guarded: neither service nor the cancellation of an order may
     * stop because the provider is unreachable. Anything unsent is stored and
     * retransmittable from Λογιστική → Δελτία Παραγγελίας Εστίασης.
     */
    async _grCallCatering(method, payload, failure) {
        try {
            const note = await this.data.call(
                "l10n.gr.prov.catering.order",
                method,
                [payload]
            );
            if (note?.error) {
                this.env.services.notification.add(`Δελτίο Παραγγελίας: ${note.error}`, {
                    type: "warning",
                });
            }
            return note;
        } catch (e) {
            // Do not stop service, but do not hide it either: a silent console
            // warning is how the missing note went unnoticed.
            console.warn(`[GR 8.6] ${method} failed`, e);
            this.env.services.notification.add(failure, { type: "danger" });
            return null;
        }
    },

    async sendOrderInPreparation(order, opts = {}) {
        const cancelled = Boolean(opts.cancelled);
        let changes = [];
        if (this._grCateringEnabled() && !cancelled) {
            try {
                changes = this._grCateringLines(order, this._grRoundChanges(order));
            } catch (e) {
                console.warn("[GR 8.6] could not read the order changes", e);
            }
        }
        // Cancelling the whole order: everything already transmitted for this
        // table is closed by a «Καθολική Ακύρωση 8.6», so nothing new is issued
        // for the round that is being thrown away.
        const positive = changes.filter((l) => l.quantity > 0);
        const negative = changes.filter((l) => l.quantity < 0);

        await super.sendOrderInPreparation(order, opts);

        if (!this._grCateringEnabled()) {
            return;
        }
        const base = {
            config_id: this.config.id,
            table_aa: this._grTableName(order),
            pos_order_uuid: order.uuid,
        };
        const failure = _t(
            "Το Δελτίο Παραγγελίας δεν στάλθηκε — δείτε τα Δελτία Παραγγελίας Εστίασης."
        );
        if (cancelled) {
            if (!this.config.l10n_gr_prov_catering_auto_cancel) {
                return;
            }
            await this._grCallCatering(
                "l10n_gr_prov_cancel_order",
                base,
                _t(
                    "Η Καθολική Ακύρωση δεν στάλθηκε — ακυρώστε τα δελτία από τα Δελτία Παραγγελίας Εστίασης."
                )
            );
            return;
        }
        if (positive.length) {
            await this._grCallCatering(
                "l10n_gr_prov_issue_note",
                { ...base, lines: positive },
                failure
            );
        }
        // Separate document by law: normal and Rec Type 7 rows never share a
        // note (guide §4).
        if (negative.length && this.config.l10n_gr_prov_catering_auto_negative) {
            await this._grCallCatering(
                "l10n_gr_prov_issue_note",
                { ...base, kind: "negative", lines: negative },
                failure
            );
        }
    },
});
