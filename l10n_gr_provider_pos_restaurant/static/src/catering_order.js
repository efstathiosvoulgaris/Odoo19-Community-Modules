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
            this.config.module_pos_restaurant && this.config.l10n_gr_prov_enabled
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
        const pending = this._grRoundChanges(order).reduce((n, c) => n + c.quantity, 0);
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
        for (const line of order.getOrderlines()) {
            const key = line.preparationKey;
            const sent = previous[key]?.quantity || 0;
            const quantity = line.getQuantity() - sent;
            if (quantity > 0) {
                changes.push({ uuid: line.uuid, quantity, name: line.getFullProductName() });
            }
        }
        return changes;
    },

    /** Money for the round: prorate each line's own net/VAT by the sent qty. */
    _grCateringLines(order, changes) {
        const lines = [];
        for (const change of changes) {
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
                quantity: change.quantity,
                net: net,
                vat_amount: vat,
                vat_rate: rate,
            });
        }
        return lines;
    },

    async sendOrderInPreparation(order, opts = {}) {
        let cateringLines = [];
        if (this._grCateringEnabled() && !opts.cancelled) {
            try {
                cateringLines = this._grCateringLines(order, this._grRoundChanges(order));
            } catch (e) {
                console.warn("[GR 8.6] could not read the order changes", e);
            }
        }

        await super.sendOrderInPreparation(order, opts);

        if (cateringLines.length) {
            try {
                const note = await this.data.call(
                    "l10n.gr.prov.catering.order",
                    "_l10n_gr_prov_issue",
                    [
                        {
                            config_id: this.config.id,
                            // getName() honours a renamed table (pos_community_addons),
                            // falling back to the table number.
                            table_aa:
                                order.getTable?.()?.getName?.() ||
                                order.getTable?.()?.table_number?.toString() ||
                                "",
                            pos_order_uuid: order.uuid,
                            lines: cateringLines,
                        },
                    ]
                );
                if (note?.error) {
                    // Service must not stop for a provider failure — the note is
                    // stored and can be retransmitted from the back office.
                    this.env.services.notification.add(
                        `Δελτίο Παραγγελίας: ${note.error}`,
                        { type: "warning" }
                    );
                }
            } catch (e) {
                console.warn("[GR 8.6] transmission call failed", e);
            }
        }
    },
});
