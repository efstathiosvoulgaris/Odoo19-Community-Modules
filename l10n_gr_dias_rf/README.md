# ΔΙΑΣ RF – Κωδικοί Πληρωμής (`l10n_gr_dias_rf`)

**Version:** 1.0 | **Odoo:** 19 | **License:** LGPL-3 | Design: `rf/DESIGN.md` (v2)

Port of the v13 module `lam_dias_rf` (ΔΙΑΣ DCT Creditor, DIAS-ORG02).

## What it does

- **RF codes** (RI18, 25 chars) `RF cc | org | u | partner | K doc`, K = 1 order, 2 invoice, 3 fixed
  customer code. K = 0 is a code of the old v13 system: never matched automatically.
  - Invoice: set at posting from the total, kept in the registry `dias.rf.code` (old printed codes still
    find their invoice). Printed on the Greek A4 form only while the invoice has a balance; after a
    partial payment the fixed customer code is printed instead (no amount check).
  - Order/quotation: follows the current total. Customer: fixed code on the contact.
- **Webhook** `POST /dias/online/<db>` (Basic Auth hashed + IP list, fail closed):
  - `DPG_ONRequest` (before the payment) only validates: ACCEPTED / REJECTED BE06. Nothing is booked.
    Already paid invoice → rejected. v13 code → accepted, handled by a person.
  - `DPG_ON` → the payment is booked by the cron «ΔΙΑΣ: καταχώρηση πληρωμών» right after the commit.
  - Wrong environment (T/P) → HTTP 409, never a silent 200.
- **Files** (PNO .XOO / csv / xlsx): hourly REST download (cron, off by default) or manual import.
  Debits, reversals and non-EUR are skipped. Same RID as an online payment = same payment.
- **Booking**: customer payment in the DIAS bank journal, reconciled with the invoice / the order's
  invoices / the customer's oldest open invoices; surplus stays as customer credit.
- Payments that need a person (no match, v13 code, error) get an activity for the DIAS manager.

## Server requirement

The server has two databases and no dbfilter, so Odoo needs the database for `/dias/online/<db>`:
nginx must send it, e.g.

    location ~ ^/dias/online/(test|skarlas)$ {
        proxy_set_header X-Odoo-Database $1;
        ... the usual proxy settings ...
    }

Without it the URL answers 404.

## Not verified

REST download endpoint (from the v13 code, not from DIAS documentation) · DIAS mode 11i/11ii ·
DIAS behaviour on timeout/5xx · PNO Status codes · ILYDA acceptance of `paymentInstruction`
(setting off by default). Questions for DIAS/ALPHA are listed in `rf/DESIGN.md`.
