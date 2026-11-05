# ΕΡΓΑΝΗ — Ψηφιακή Κάρτα Εργασίας (`l10n_gr_ergani_card`)

**Version:** 2.1 | **Odoo:** 19 | **License:** LGPL-3 | Design: `ergani/DESIGN.md` (v3.1)

The employee punches the ΕΡΓΑΝΗ ΙΙ work card himself, through Odoo:

1. Login → `/ergani/gate` asks him to scan his own card QR (hand scanner or camera) → «Προσέλευση».
2. «Αποχώρηση» in the top bar → card again → «Αποχώρηση» → logged out of this browser. His other devices lose the back office until the next «Προσέλευση»; a till open under his account keeps working.
3. Split schedule: after the midday «Αποχώρηση», the afternoon login asks a new «Προσέλευση».

Plain logout, session expiry or a closed browser send nothing. Breaks send nothing.

## What is gated, what is not

| Gated until the employee punches | Never gated |
|---|---|
| `/odoo` (web client), every `auth='user'` route | POS (`/pos/*` and every call the POS makes) |
| | API-key / XML-RPC / `/json/2` (Skroutz etc.) |
| | website, bus/websocket, logout, assets |

Only employees with **ΕΡΓΑΝΗ → «Χτυπά κάρτα»** enabled see the gate. The owner is exempt.

## Rules built in (DESIGN §3)

- A card is created **only** by the gate, for the logged-in user's own employee, after he scans his own card.
  No «New» button, no import, no admin punch. Cards are never deleted or edited (hash chain).
- The card QR is the employee's **Badge ID** (hr `barcode`), printed from his ΕΡΓΑΝΗ tab
  («Εκτύπωση κάρτας»; «Νέα κάρτα» replaces a lost one). The quick login accepts the same card
  without either addon depending on the other. Only the logged-in user's own card is accepted;
  5 wrong scans → locked for 15 minutes.
- A check-in without check-out older than 16 hours counts as a forgotten «Αποχώρηση»:
  nothing is sent for the employee, the ΕΡΓΑΝΗ manager is notified once.

## Sending

Mode (Settings → ΕΡΓΑΝΗ): **Προσομοίωση** (default, nothing leaves Odoo) · **Δοκιμαστικό (trial)** ·
**Παραγωγικό**. A card belongs to the mode it was punched in and is only ever sent in that mode.

One cron (`ΕΡΓΑΝΗ: αποστολή καρτών`, every 2′ and right after each punch) sends one card per request:

| Outcome | Card | Who acts |
|---|---|---|
| Accepted | `Στάλθηκε` + protocol | — |
| Could not connect (nothing left) | stays `Σε αναμονή`, retried | — |
| Sent but no clear answer | `Άγνωστη έκβαση` — never re-sent automatically | manager: «Βρέθηκε στο ΕΡΓΑΝΗ» / «Δεν βρέθηκε — επαναποστολή» / «Αγνόησε» |
| Refused (400) | `Σφάλμα` | manager |
| Login fails, 429, same 400 twice | sending **paused** for the company | manager: fix, then «Συνέχιση αποστολής» |
| > 14′ after the punch | flagged late; recorded technical failure → automatic reason code; otherwise waits for the manager to set a reason | manager |

## Checking (1.3, `ergani/PLAN_1.3.md`)

Everything here compares punches with the employee's **Odoo working schedule**, not with the schedule the
accountant declared in ΕΡΓΑΝΗ. It is not a compliance check and every screen says so. Keep the Odoo schedule
equal to the declared one and set **«Ωράριο επιβεβαιωμένο με λογιστή στις»** on the employee; a later change of
the schedule is flagged.

| Menu | Who | What |
|---|---|---|
| Σήμερα | manager | one card per employee and work period: μέσα / έξω / δεν ήρθε / χωρίς χτύπημα / ρεπό / ξεχασμένη |
| Κατάσταση κινήσεων | everyone (employees: own only) | period → list / pivot / Excel / PDF |
| Αρχείο υποβολών | manager | one row per call to ΕΡΓΑΝΗ |

Report filters, in two groups:
- **Χρειάζεται έλεγχος** (red, no tolerance, exact minutes): προσέλευση πριν την έναρξη · εργασία μετά τη λήξη /
  εκτός ωραρίου / περισσότερη · χτύπημα σε ρεπό ή αργία · μη ζευγαρωμένες · μέρα με ωράριο χωρίς χτύπημα.
- **Πληροφορία προσωπικού** (tolerance in Settings, default 10′): καθυστέρηση · προαναχώρηση · λιγότερη εργασία.

A lunch break inside the schedule does not split the day; only a real gap does (split schedule). Leaves are only
those entered in the Odoo calendar (`hr_holidays` is not installed).

**Receipt.** «Αποδεικτικό ΕΡΓΑΝΗ» on a sent card: the first click asks the sender cron to fetch the PDF, the next
opens it. Response format UNVERIFIED until trial.

**Submission log.** Never credentials, tokens or the card body (the card has it). Other bodies only on failure,
cleared after 2 years.

## Retention

Cards and receipts: at least 5 years, never deleted by Odoo. IP / user-agent: pseudonymised after 2 years.
Submission log rows stay; their failure bodies are cleared after 2 years. Report lines are not stored (rebuilt
on demand, removed after an hour).

## Setup order

1. Settings → ΕΡΓΑΝΗ: manager, branch (0 = έδρα). Leave mode on **Προσομοίωση**.
2. Each employee → tab ΕΡΓΑΝΗ: ΑΦΜ, surname and name **exactly as in ΕΡΓΑΝΗ**, enable.
3. Give employees `static/description/employee_notice_el.md` (GDPR notice; **re-sign after 1.3**) and
   `static/description/outage_procedure_el.md`.
4. A week of simulation. Check «Κάρτες» daily.
5. When credentials arrive: mode **trial**, «Δοκιμή σύνδεσης», confirm on trial: reason codes,
   `f_reference_date` after midnight, split schedule with two pairs. Production only by decision.

## Open (UNVERIFIED until trial)

Late-reason codes · production URL (default eservices.yeka.gr, unconfirmed) · whether ΕΡΓΑΝΗ rejects a check-out without check-in ·
what it does with a duplicate check-in · whether the old refresh token is invalidated.
