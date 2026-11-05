/* Γρήγορη σύνδεση: vanilla JS, όπως η πύλη ΕΡΓΑΝΗ (η σελίδα δεν φορτώνει τα αρχεία του Odoo). */
(function () {
    "use strict";
    const root = document.querySelector("main.ql");
    if (!root || !document.getElementById("step-who")) {
        return;
    }
    const db = root.dataset.db || "";
    const $ = (id) => document.getElementById(id);
    const show = (id) => {
        for (const s of ["step-who", "step-camera", "step-pin"]) {
            $(s).hidden = s !== id;
        }
    };
    const say = (text) => {
        $("msg").textContent = text || "";
    };
    let chosen = { user_id: null, card: null };
    let reader = null;

    async function rpc(url, params) {
        const resp = await fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ jsonrpc: "2.0", method: "call", params }),
            credentials: "same-origin",
        });
        const data = await resp.json();
        if (data.error) {
            throw new Error((data.error.data && data.error.data.message) || "Σφάλμα σύνδεσης");
        }
        return data.result;
    }

    // Ταμείο ανοιχτό σε αυτόν τον browser; (το heartbeat του POS εκπέμπει στο ίδιο κανάλι)
    try {
        const channel = new BroadcastChannel("ql_" + db);
        channel.onmessage = (ev) => {
            if (ev.data && ev.data.type === "pos-alive") {
                $("pos-warning").hidden = false;
            }
        };
        channel.postMessage({ type: "who-is-there" });
    } catch {
        // χωρίς BroadcastChannel δεν γίνεται η προειδοποίηση· η σύνδεση δουλεύει κανονικά
    }

    function buildPad() {
        // Ανακατεμένα ψηφία: όποιος κοιτά από πίσω δεν βλέπει το PIN από τη θέση των κουμπιών.
        const digits = ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9"];
        for (let i = digits.length - 1; i > 0; i--) {
            const j = Math.floor(Math.random() * (i + 1));
            [digits[i], digits[j]] = [digits[j], digits[i]];
        }
        const pad = $("pad");
        pad.textContent = "";
        for (const d of [...digits, "⌫"]) {
            const b = document.createElement("button");
            b.type = "button";
            b.textContent = d;
            b.addEventListener("click", () => {
                const pin = $("pin");
                pin.value = d === "⌫" ? pin.value.slice(0, -1) : (pin.value + d).slice(0, 6);
                pin.focus();
            });
            pad.appendChild(b);
        }
    }

    function askPin(label) {
        $("who").textContent = label;
        $("pin").value = "";
        buildPad();
        show("step-pin");
        say("");
        $("pin").focus();
    }

    function stopCamera() {
        if (reader) {
            try {
                reader.reset();
            } catch {
                // ήδη σταματημένη
            }
            reader = null;
        }
    }

    function gotCard(text) {
        stopCamera();
        chosen = { user_id: null, card: (text || "").trim() };
        askPin("Κάρτα διαβάστηκε — δώστε το PIN σας");
    }

    for (const tile of document.querySelectorAll(".tile")) {
        tile.addEventListener("click", () => {
            chosen = { user_id: Number(tile.dataset.user), card: null };
            askPin(tile.textContent);
        });
    }

    $("btn-scan").addEventListener("click", async () => {
        if (!window.ZXing) {
            say("Η κάμερα δεν είναι διαθέσιμη. Επιλέξτε το όνομά σας.");
            return;
        }
        show("step-camera");
        reader = new window.ZXing.BrowserQRCodeReader();
        try {
            const result = await reader.decodeOnceFromVideoDevice(undefined, "video");
            gotCard(result.getText());
        } catch (e) {
            stopCamera();
            show("step-who");
            if (e && e.name !== "NotFoundException") {
                say("Η κάμερα δεν άνοιξε. Επιλέξτε το όνομά σας ή χρησιμοποιήστε σκάνερ.");
            }
        }
    });
    $("btn-cancel-scan").addEventListener("click", () => {
        stopCamera();
        show("step-who");
    });

    // Χειροσκάνερ (πληκτρολόγιο): γράφει το QR και πατά Enter.
    $("wedge").addEventListener("keydown", (ev) => {
        if (ev.key === "Enter" && ev.target.value.trim()) {
            ev.preventDefault();
            const text = ev.target.value;
            ev.target.value = "";
            gotCard(text);
        }
    });

    $("btn-back").addEventListener("click", () => {
        chosen = { user_id: null, card: null };
        $("pin").value = "";
        show("step-who");
        say("");
    });

    async function login() {
        const btn = $("btn-login");
        if (btn.disabled) {
            return;
        }
        const pin = $("pin").value;
        if (!/^\d{6}$/.test(pin)) {
            say("Το PIN έχει 6 ψηφία.");
            return;
        }
        btn.disabled = true;
        say("");
        try {
            const res = await rpc("/quick-login/authenticate", {
                user_id: chosen.user_id,
                card: chosen.card,
                pin,
            });
            if (res.redirect) {
                window.location = res.redirect;
                return;
            }
            $("pin").value = "";
            buildPad();
            say(res.error);
        } catch (e) {
            say(e.message);
        } finally {
            btn.disabled = false;
        }
    }
    $("btn-login").addEventListener("click", login);
    $("pin").addEventListener("keydown", (ev) => {
        if (ev.key === "Enter") {
            login();
        }
    });
    show("step-who");
    $("wedge").focus();
})();
