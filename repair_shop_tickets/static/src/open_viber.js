import { browser } from "@web/core/browser/browser";
import { registry } from "@web/core/registry";

// Opens viber://chat?number=…&draft=… (ir.actions.act_url would turn it into a
// relative path). The text is also copied: not every Viber fills the draft.
registry.category("actions").add("repair_shop_tickets.open_viber", async (env, action) => {
    const { url, text } = action.params;
    try {
        await browser.navigator.clipboard.writeText(text);
        env.services.notification.add(
            "Το μήνυμα αντιγράφηκε. Αν δεν εμφανιστεί στο Viber, κάντε επικόλληση (Ctrl+V).",
            { type: "info" }
        );
    } catch {
        // no clipboard permission: the draft in the link is all we have
    }
    browser.location.assign(url);
});
