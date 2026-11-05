/* ΕΡΓΑΝΗ gate page: the employee scans his own card QR (hand scanner or
 * camera). Plain JS on purpose — the page is shown before the web client and
 * must stay tiny. */
(function () {
    "use strict";
    const root = document.querySelector(".gate");
    const mode = root.dataset.mode;
    const redirect = root.dataset.redirect || "/odoo";
    const $ = (id) => document.getElementById(id);
    const msg = $("msg");
    const codeInput = $("code");
    let reader = null;
    let busy = false;

    function say(text, kind) {
        msg.textContent = text || "";
        msg.className = "msg " + (kind || "");
    }

    async function rpc(url, params) {
        const resp = await fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ jsonrpc: "2.0", method: "call", params }),
        });
        const data = await resp.json();
        if (data.error) {
            throw new Error((data.error.data && data.error.data.message) || data.error.message);
        }
        return data.result;
    }

    function stopCamera() {
        if (reader) {
            try {
                reader.reset();
            } catch {
                // already stopped
            }
            reader = null;
        }
        $("video").hidden = true;
        $("btn-camera-stop").hidden = true;
        $("btn-camera").hidden = false;
    }

    async function punch(code) {
        code = (code || "").trim();
        if (busy || !code) return;
        busy = true;
        try {
            const res = await rpc("/ergani/gate/punch", { code, mode });
            if (res.error) {
                return say(res.error, "err");
            }
            const what = mode === "out" ? "Αποχώρηση" : "Προσέλευση";
            const tail = res.simulation ? " — προσομοίωση, δεν στάλθηκε" : " — σε αναμονή αποστολής";
            say(res.already ? "Έχετε ήδη χτυπήσει προσέλευση." : `${what} ${res.time}${tail}`, "ok");
            setTimeout(() => { window.location = res.redirect || redirect; }, 1500);
        } catch (e) {
            say(e.message, "err");
        } finally {
            busy = false;
            codeInput.value = "";
            codeInput.focus();
        }
    }

    async function startCamera() {
        if (!window.ZXing) {
            return say("Η κάμερα δεν είναι διαθέσιμη. Χρησιμοποιήστε το σκάνερ.", "err");
        }
        say("");
        $("video").hidden = false;
        $("btn-camera-stop").hidden = false;
        $("btn-camera").hidden = true;
        reader = new window.ZXing.BrowserQRCodeReader();
        try {
            const result = await reader.decodeOnceFromVideoDevice(undefined, "video");
            stopCamera();
            punch(result.getText());
        } catch (e) {
            stopCamera();
            if (e && e.name !== "NotFoundException") {
                say("Η κάμερα δεν άνοιξε. Χρησιμοποιήστε το σκάνερ.", "err");
            }
        }
    }

    codeInput.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter") {
            ev.preventDefault();
            punch(codeInput.value);
        }
    });
    $("btn-camera").addEventListener("click", startCamera);
    $("btn-camera-stop").addEventListener("click", stopCamera);

    const hasCard = root.dataset.hasCard === "1";
    $("no-card").hidden = hasCard;
    $("punch").hidden = !hasCard;
    if (hasCard) codeInput.focus();
})();
