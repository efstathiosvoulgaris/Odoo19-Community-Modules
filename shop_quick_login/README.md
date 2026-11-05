# Γρήγορη σύνδεση (PIN / κάρτα QR) και αποσύνδεση αδράνειας (`shop_quick_login`)

**Version:** 1.2 | **Odoo:** 19 | **License:** LGPL-3 | Design: `quick_login/DESIGN.md` (v2, security council)

## Quick login
- Only on **enrolled shop computers** (Γρήγορη σύνδεση → Υπολογιστές καταστήματος → new → from that PC
  «Εγγραφή αυτού του υπολογιστή»; admin password re-checked; admins are notified). Cookie `ql_device_<db>`,
  random 256-bit, HttpOnly/Secure/SameSite=Lax, 12 months, only its SHA-256 stored. Per database.
- `/quick-login` (button on the login page of an enrolled PC): pick your name **or** scan your QR card, then
  **always** your quick-login PIN. Card = selector, never a credential on its own. No dependency on any
  other addon of ours (ERGANI is optional).
- Goes through Odoo's own `session.authenticate()` with credential type `quick_pin`, checked in
  `res.users._check_credentials` (device, eligibility, PIN): session rotation, 2FA (`mfa: default`), Odoo's
  login cooldown and `res.device` all apply. A `type=quick_pin` POST to `/web/login` is refused.
- Never for: administrators, accounting managers, HR users/managers, users with 2FA, users without PIN.
- PIN: set by the administrator on the employee (tab «Γρήγορη σύνδεση» → «Ορισμός PIN», or the app menu;
  password re-check), 6 digits, weak ones refused, hash only (`ql_pin_hash`).
- Lockout: own counter (5 wrong → 15'). Per device: 10 failures/hour →
  the device is closed until an admin reopens it (notification). Odoo's per-IP cooldown also applies and the
  whole shop is one IP (NAT): a burst of wrong PINs can delay normal logins by 60''. Accepted.
- QR card: the employee's **Badge ID** (hr `barcode`), printed from the employee's «Γρήγορη σύνδεση» tab
  («Εκτύπωση κάρτας»; «Νέα κάρτα» replaces a lost one, the old QR stops working). The same card can be
  accepted by other addons (ERGANI) without either depending on the other. HR users can read the Badge ID:
  that is why the card only picks the user and the PIN is always asked.
- History (append-only, 12 months): user, PC, method, IP, time, success.

## Idle logout
- After N minutes (Ρυθμίσεις, default 15, 0 = off) without mouse/keyboard in any Odoo tab: warning 60'' before,
  then logout to the login page («ΔΕΝ δηλώθηκε Αποχώρηση»). Not while a POS tab is open in the browser (the
  session cookie is shared, logout would close the till), not while a dialog is open, not if unsaved changes
  cannot be saved, not on a PC marked «Χωρίς αποσύνδεση αδράνειας».
- Browser-side = convenience. Server-side net for quick-login sessions: (N + 5)' without a human request → expired.
- The ERGANI gate page (if installed) has no idle timer.

## Before production
Chrome password saving OFF on shared PCs; cookies not cleared on exit; 2FA for the administrator; employees
sign the GDPR notice `static/description/employee_notice_el.md`.
