# User Guide — Greek E-Invoicing Provider

This guide is for accountants and finance staff using `l10n_gr_provider_base`
with a driver module (e.g. `l10n_gr_provider_ilyda`) to issue invoices through
a licensed Greek e-invoicing provider (Υ.ΠΑ.Η.Ε.Σ.).

---

## What changes in your workflow

When a provider is configured, Odoo issues your sales invoices **through the
provider** instead of directly via the myDATA ERP channel. The provider
submits the invoice to AADE, receives the legal markings (ΜΑΡΚ, verification
hash, identifier), and returns them to Odoo. The printed invoice PDF carries
these markings as required by A.1035/2020 art. 3 par. 7.

**You do not need to use the myDATA ERP channel separately — it is
automatically suppressed for documents sent through the provider.**

---

## Initial setup (done by your IT administrator)

1. **Settings → Accounting → Greek E-Invoicing Provider**
   - Set **Provider** to your licensed provider (e.g. `ILYDA (vs.gr)`).
   - Enter the credentials provided by your provider (e.g. X-Auth-Key).
   - Keep **Test Environment** enabled during onboarding; disable it only
     when your provider confirms you are ready for production.
   - Enable **Auto-send on Post** if you want invoices sent automatically as
     soon as they are posted, without pressing a button.

2. **Contacts → customer records**: for public-sector buyers, enter the
   customer's **ΑΑΗΤ** code (from the ΜΑΑΗΤ registry at
   webapps.gsis.gr/dsae2/foreisreg). This pre-fills the B2G Buyer Reference.

3. **Products**: for products sold under public contracts, enter the **CPV
   Code** (Common Procurement Vocabulary, e.g. `30237200-1`). This is
   mandatory on B2G invoice lines.

---

## Issuing a regular invoice (B2B or B2C)

1. Create and fill in the invoice as normal, including the **myDATA** tab
   (invoice type, income classifications, payment method).
2. Click **Confirm** (post the invoice).
3. Choose how to send it:
   - **Auto-send enabled**: the invoice is queued and the scheduled job
     (runs every 10 minutes) transmits it automatically. No further action
     needed.
   - **Manual**: click the **Send to Provider** button in the invoice header.
     The invoice is issued immediately; any errors are shown in a popup.
   - **Send & Print**: use the standard **Send & Print** button. The provider
     submission happens first, so the downloaded or emailed PDF already
     carries the ΜΑΡΚ and QR code.

4. After successful issuance, the **E-Invoicing Provider** tab on the invoice
   shows:
   - **Provider Status**: `Issued (Marked)`
   - **ΜΑΡΚ (Provider)**, **Authentication String**, **Invoice Identifier**,
     **Provider QR URL**, **Provider Site**
   - **Provider Sent At**: timestamp of successful issuance

---

## The printed invoice

After issuance, the printed PDF carries a legal markings block below the
myDATA QR code:

```
[QR image]  ΜΑΡΚ: 400001234567890
            Συμβολοσειρά Αυθεντικοποίησης: abc123...
            Αναγνωριστικό Παραστατικού: def456...
            Πάροχος: https://vs.gr — Ηλεκτρονική έκδοση μέσω Παρόχου Υ.ΠΑ.Η.Ε.Σ.
```

---

## Issuing a public-sector invoice (B2G / Peppol)

B2G invoices are routed through the Peppol network in addition to myDATA.

1. Open the invoice, go to the **E-Invoicing Provider** tab.
2. Check **B2G (Public Sector)**.
3. Fill in the B2G fields that appear:

   | Field | Description |
   |-------|-------------|
   | **Contract Reference (BT-12, ΑΔΑΜ)** | The ΑΔΑΜ number of the public contract (e.g. `20SYMV006467658`). Mandatory. |
   | **Budget Type (BT-11)** | `1` — Regular Budget (ΑΔΑ Ανάληψης) · `2` — Public Investment Programme (Ενάριθμος) · `3` — Other Budgets (ΑΔΑ Ανάληψης). |
   | **Budget Identifier (BT-11)** | The ΑΔΑ Ανάληψης or Ενάριθμος ΠΔΕ corresponding to the budget type. Mandatory. |
   | **Buyer Reference (BT-10)** | Auto-filled from the customer's name and ΑΑΗΤ code as `"Name\|ΑΑΗΤ"`. Adjust if the contracting authority differs from the billing customer. |
   | **Purchase Order (BT-13)** | The buyer's purchase order number (Αναγνωριστικό Εντολής Αγοράς), if available. |

4. Confirm and send as usual.
5. After issuance, the **B2G Status** field shows the Peppol delivery status.
   Click **Refresh B2G Status** to poll the provider for the latest state.

**Before sending a B2G invoice, ensure:**
- The customer has a VAT number.
- Every product line has a CPV code set on the product record.
- The company address (city and ZIP) is complete.

---

## Issuing a credit note

Credit notes referencing a previously issued invoice must be sent through the
provider in the same way as invoices.

**Important:** the original invoice must already have a ΜΑΡΚ (must have been
successfully submitted to the provider). The credit note validation will block
submission if the original has no ΜΑΡΚ — submit the original first.

The credit note payload automatically includes a reference to the original
invoice's ΜΑΡΚ, date, and document type.

---

## Error handling and retries

If a submission fails, the invoice moves to **Error** state and the error
message is shown in the **Provider Error** field and in the chatter.

The scheduled job retries all documents in **Error** state every 10 minutes,
regardless of the auto-send setting. You can also retry immediately by
clicking **Send to Provider** on the invoice.

Common error causes:
- Missing fields (VAT number, income classification, B2G references).
- Provider API unavailable — the job will retry automatically.
- AADE rejection (check the error message for the AADE error code).

---

## Checking the provider status column in the invoice list

The invoice list shows a **Provider Status** badge column (optional; enable it
via the column picker):

| Badge | Meaning |
|-------|---------|
| Orange — To Send | Queued, not yet transmitted |
| Green — Issued (Marked) | Successfully marked by the provider |
| Red — Error | Last submission failed; will be retried |

---

## Frequently asked questions

**Q: Can I still use Send & Print for customers who need the PDF by email?**
Yes. Use **Send & Print** as you normally would. The provider submission
happens automatically before the PDF is generated, so the emailed PDF carries
the markings.

**Q: The invoice was sent but the PDF was uploaded separately — is that normal?**
Yes. The PDF upload happens in a second step (after marking). The scheduled
job handles it automatically within the next 10-minute cycle. The **PDF
Uploaded to Provider** flag on the invoice shows the status.

**Q: What is `Previously Submitted`?**
If AADE had already seen this document from a prior attempt and returned the
same ΜΑΡΚ (error 228 recovery), this flag is set. The marking is valid. It
is flagged for visibility so you can audit any duplicate-submission scenarios.

**Q: I see the myDATA ERP channel is greyed out for my invoices. Is that a problem?**
No. When a provider is configured, the ERP channel is deliberately suppressed
for sales documents — the provider reports to myDATA on your behalf. Vendor
bills and expense classifications still use the ERP channel as normal.
