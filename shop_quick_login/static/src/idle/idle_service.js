import { browser } from "@web/core/browser/browser";
import { registry } from "@web/core/registry";
import { session } from "@web/session";
import { clearUncommittedChanges } from "@web/webclient/actions/action_service";

/* Αποσύνδεση μετά από Ν λεπτά αδράνειας του ανθρώπου (ποντίκι, πλήκτρο, κύλιση, άγγιγμα) σε
   ΟΠΟΙΑΔΗΠΟΤΕ καρτέλα του Odoo στον browser. Όχι όσο είναι ανοιχτό ταμείο, παράθυρο διαλόγου ή
   εκκρεμεί αποθήκευση. Ευκολία, όχι φραγμός: ο server έχει το δικό του όριο για τις γρήγορες συνδέσεις. */
const WARN_SECONDS = 60;
const POS_STALE_MS = 60000;
const EVENTS = ["mousemove", "mousedown", "keydown", "wheel", "touchstart", "scroll"];

const idleService = {
    dependencies: ["notification"],
    start(env) {
        const minutes = Number(session.ql_idle_minutes || 0);
        if (!minutes) {
            return;
        }
        const db = session.db || "";
        const limitMs = minutes * 60000;
        const key = "ql_last_" + db;
        let channel = null;
        try {
            channel = new BroadcastChannel("ql_" + db);
        } catch {
            channel = null;
        }
        let lastActivity = Date.now();
        let lastPos = 0;
        let lastWrite = 0;
        let warning = null;
        let originalTitle = document.title;

        const share = () => {
            const now = Date.now();
            if (now - lastWrite < 5000) {
                return;
            }
            lastWrite = now;
            try {
                browser.localStorage.setItem(key, String(now));
            } catch {
                // ιδιωτικό παράθυρο: μένει το BroadcastChannel
            }
            channel?.postMessage({ type: "activity", at: now });
        };
        const activity = () => {
            lastActivity = Date.now();
            hideWarning();
            share();
        };
        for (const ev of EVENTS) {
            window.addEventListener(ev, activity, { passive: true, capture: true });
        }
        if (channel) {
            channel.onmessage = (ev) => {
                const data = ev.data || {};
                if (data.type === "activity") {
                    lastActivity = Math.max(lastActivity, data.at || Date.now());
                    hideWarning();
                } else if (data.type === "pos-alive") {
                    lastPos = Date.now();
                } else if (data.type === "logout") {
                    browser.location.href = data.url;
                }
            };
            channel.postMessage({ type: "who-is-there" });
        }

        const busy = () =>
            Date.now() - lastPos < POS_STALE_MS ||
            document.querySelector(".modal.show, .o_dialog") !== null;

        function showWarning(secondsLeft) {
            if (!warning) {
                warning = document.createElement("div");
                warning.className = "o_ql_idle_warning";
                warning.innerHTML =
                    '<div class="o_ql_idle_box"><p class="o_ql_idle_text"></p>' +
                    '<button type="button" class="btn btn-primary">Παραμένω</button></div>';
                warning.querySelector("button").addEventListener("click", activity);
                document.body.appendChild(warning);
                originalTitle = document.title;
            }
            warning.querySelector(".o_ql_idle_text").textContent =
                `Αποσύνδεση λόγω αδράνειας σε ${secondsLeft}''`;
            document.title = secondsLeft % 2 ? "⚠ Αποσύνδεση σε " + secondsLeft + "''" : originalTitle;
        }
        function hideWarning() {
            if (warning) {
                warning.remove();
                warning = null;
                document.title = originalTitle;
            }
        }

        let loggingOut = false;
        async function logout() {
            if (loggingOut) {
                return;
            }
            loggingOut = true;
            // Πρώτα αποθήκευση· αν δεν γίνεται (π.χ. λείπει υποχρεωτικό πεδίο), δεν φεύγουμε.
            let saved = true;
            try {
                saved = await clearUncommittedChanges(env);
            } catch {
                saved = false;
            }
            if (!saved) {
                loggingOut = false;
                hideWarning();
                lastActivity = Date.now();
                env.services.notification.add(
                    "Δεν έγινε αποσύνδεση αδράνειας: υπάρχουν αλλαγές που δεν αποθηκεύονται.",
                    { type: "warning", sticky: true }
                );
                return;
            }
            const url =
                "/web/session/logout?redirect=" +
                encodeURIComponent("/web/login?db=" + encodeURIComponent(db) + "&ql_idle=1");
            channel?.postMessage({ type: "logout", url });
            browser.location.href = url;
        }

        browser.setInterval(() => {
            try {
                const shared = Number(browser.localStorage.getItem(key) || 0);
                lastActivity = Math.max(lastActivity, shared);
            } catch {
                // χωρίς localStorage: μένει το BroadcastChannel
            }
            if (busy()) {
                lastActivity = Math.max(lastActivity, Date.now() - limitMs + WARN_SECONDS * 1000 + 1000);
                hideWarning();
                return;
            }
            const left = Math.ceil((lastActivity + limitMs - Date.now()) / 1000);
            if (left <= 0) {
                logout();
            } else if (left <= WARN_SECONDS) {
                showWarning(left);
            }
        }, 1000);
    },
};

registry.category("services").add("shop_quick_login_idle", idleService);
