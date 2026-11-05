import { browser } from "@web/core/browser/browser";
import { registry } from "@web/core/registry";

// Opens a non-http link (viber://…) that ir.actions.act_url would mangle.
registry.category("actions").add("qol_fixes.open_external_url", (env, action) => {
    browser.location.assign(action.params.url);
});
