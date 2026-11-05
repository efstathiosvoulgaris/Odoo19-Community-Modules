import { session } from "@web/session";

/* Στο ταμείο: λέει στις καρτέλες του backend «είμαι ανοιχτό». Όσο ακούγεται, δεν γίνεται
   αποσύνδεση αδράνειας (η συνεδρία είναι κοινή για όλο τον browser και θα έκλεινε και το ταμείο). */
try {
    const channel = new BroadcastChannel("ql_" + (session.db || ""));
    const beat = () => channel.postMessage({ type: "pos-alive" });
    channel.onmessage = (ev) => {
        if (ev.data && ev.data.type === "who-is-there") {
            beat();
        }
    };
    beat();
    setInterval(beat, 20000);
} catch {
    // χωρίς BroadcastChannel: το backend δεν ξέρει για το ταμείο· βλ. README
}
