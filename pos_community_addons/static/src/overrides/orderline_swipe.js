/** @odoo-module **/

/**
 * Swipe-to-delete gesture for order lines in display mode.
 *
 * Swipe a line left > 80px to remove it from the order.
 * The background turns red as threshold feedback; the item
 * animates out before the model deletion fires.
 *
 * touch events are used (not pointer events) so they can
 * coexist with useTimedPress (which uses pointer events).
 * Calling e.preventDefault() on a horizontal touchmove also
 * suppresses the synthesised pointerup / click.
 */

import { Orderline } from "@point_of_sale/app/components/orderline/orderline";
import { patch } from "@web/core/utils/patch";
import { onMounted } from "@odoo/owl";

patch(Orderline.prototype, {
    setup() {
        super.setup();
        if (this.props.mode === "display") {
            onMounted(() => this._setupSwipeToDelete());
        }
    },

    _setupSwipeToDelete() {
        const el = this.root.el;
        if (!el) return;

        let startX = 0;
        let startY = 0;
        let currentDx = 0;
        let isSwiping = false;
        let directionLocked = false;

        const THRESHOLD = 80; // px swipe needed to delete

        el.addEventListener(
            "touchstart",
            (e) => {
                const t = e.touches[0];
                startX = t.clientX;
                startY = t.clientY;
                currentDx = 0;
                isSwiping = false;
                directionLocked = false;
                el.style.transition = "none";
            },
            { passive: true }
        );

        el.addEventListener(
            "touchmove",
            (e) => {
                // Once direction is locked to vertical, ignore.
                if (directionLocked && !isSwiping) return;

                const t = e.touches[0];
                const dx = t.clientX - startX;
                const dy = t.clientY - startY;

                if (!directionLocked) {
                    // Wait for at least 6px of movement before deciding direction.
                    if (Math.abs(dx) < 6 && Math.abs(dy) < 6) return;
                    directionLocked = true;
                    // Vertical → let native scroll handle it.
                    if (Math.abs(dy) >= Math.abs(dx)) return;
                    isSwiping = true;
                }

                if (!isSwiping) return;

                // Only left swipes (dx < 0) trigger delete.
                if (dx < 0) {
                    currentDx = Math.max(dx, -120);
                    e.preventDefault(); // suppress click / pointer events

                    el.style.transform = `translateX(${currentDx}px)`;

                    // Red background grows as we approach threshold.
                    const intensity = Math.min(-currentDx / THRESHOLD, 1);
                    el.style.backgroundColor = `rgba(220, 53, 69, ${(intensity * 0.35).toFixed(2)})`;
                }
            },
            { passive: false }
        );

        el.addEventListener(
            "touchend",
            () => {
                if (!isSwiping) return;

                if (currentDx <= -THRESHOLD) {
                    // Animate the line out, then remove it from the model.
                    el.style.transition = "transform 0.15s ease-out, opacity 0.15s ease-out";
                    el.style.transform = "translateX(-110%)";
                    el.style.opacity = "0";
                    setTimeout(() => {
                        const line = this.props.line;
                        if (line?.order_id) {
                            line.order_id.removeOrderline(line);
                        }
                    }, 150);
                } else {
                    // Snap back to original position.
                    el.style.transition = "transform 0.2s ease, background-color 0.2s ease";
                    el.style.transform = "translateX(0)";
                    el.style.backgroundColor = "";
                }

                isSwiping = false;
                currentDx = 0;
            },
            { passive: true }
        );
    },
});
