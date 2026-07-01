# Developer Guide — Writing a Provider Driver

This guide explains how to create a new driver module that plugs into
`l10n_gr_provider_base`.

---

## Overview

`l10n_gr_provider_base` defines the fields, cron, UI, and PDF markings. It
delegates all API calls to a driver module via a naming convention:

```
account.move._l10n_gr_prov_<operation>_<provider_key>(self)
```

The `provider_key` is the string you add to the `l10n_gr_prov_provider`
selection field on `res.company`.

---

## Step 1 — Create the module

Minimal `__manifest__.py`:

```python
{
    'name': 'Greece - E-Invoicing Provider: ACME',
    'version': '1.0',
    'category': 'Accounting/Localizations',
    'depends': ['l10n_gr_provider_base'],
    'data': ['views/res_config_settings_views.xml'],
    'installable': True,
    'auto_install': False,
}
```

---

## Step 2 — Register the provider key

In `models/res_company.py`, extend the selection and add any credential fields:

```python
from odoo import fields, models

class ResCompany(models.Model):
    _inherit = 'res.company'

    l10n_gr_prov_provider = fields.Selection(
        selection_add=[('acme', 'ACME e-Invoice')],
    )
    l10n_gr_prov_acme_api_key = fields.Char(
        string='ACME API Key',
        groups='base.group_system',
    )
```

Expose the credential in `res.config.settings` and a settings view the same
way `l10n_gr_provider_ilyda` does.

---

## Step 3 — Implement the three operations

Create `models/account_move.py` inheriting `account.move`. The three method
names must match exactly.

### `_l10n_gr_prov_send_<provider_key>`

Called by the base module to submit the document and receive the AADE markings.

**Contract:**

- Call `self.ensure_one()`.
- Raise `UserError` (or any exception) on failure — the base module catches it,
  stores the message in `l10n_gr_prov_error`, sets `l10n_gr_prov_state = 'error'`,
  and posts a chatter message.
- On success, write the marking fields and return normally. The base module
  writes `l10n_gr_prov_state = 'sent'` and the send timestamp.

**Marking fields to write on success:**

| Field | Type | Notes |
|-------|------|-------|
| `l10n_gr_prov_mark` | Char | ΜΑΡΚ from AADE. Required. |
| `l10n_gr_prov_invoice_id` | Char | Provider's internal invoice ID. Used for PDF upload and status polling. |
| `l10n_gr_prov_verification_hash` | Char | SHA-1 authentication string (Appendix B1, A.1035/2020). |
| `l10n_gr_prov_invoice_identifier` | Char | SHA-1 invoice identifier (Appendix B2). |
| `l10n_gr_prov_qr_url` | Char | URL to encode in the provider QR code. |
| `l10n_gr_prov_provider_url` | Char | Provider verification portal URL (printed on the invoice). |
| `l10n_gr_prov_previously_submitted` | Boolean | `True` when the provider recovered a prior marking (AADE error 228). |

```python
def _l10n_gr_prov_send_acme(self):
    self.ensure_one()
    client = AcmeClient(self.company_id)
    payload = self._build_acme_payload()   # your builder
    data = client.submit(payload)
    if not data.get('mark'):
        raise UserError(_('ACME did not return a MARK: %s', data))
    self.write({
        'l10n_gr_prov_mark': data['mark'],
        'l10n_gr_prov_invoice_id': data.get('invoiceId'),
        'l10n_gr_prov_verification_hash': data.get('verificationHash'),
        'l10n_gr_prov_invoice_identifier': data.get('invoiceIdentifier'),
        'l10n_gr_prov_qr_url': data.get('qrUrl'),
        'l10n_gr_prov_provider_url': data.get('portalUrl'),
        'l10n_gr_prov_previously_submitted': bool(data.get('previouslySubmitted')),
    })
```

### `_l10n_gr_prov_upload_pdf_<provider_key>`

Called after a document is marked, to upload the legal PDF.

**Contract:**

- Call `self.ensure_one()`.
- Use `self._l10n_gr_prov_get_pdf()` (from the base module) to get
  `(filename, pdf_bytes)`. It returns the stored attachment if available,
  or renders the invoice PDF on demand.
- Raise on fatal errors; log warnings for non-fatal ones.
- The base module sets `l10n_gr_prov_pdf_uploaded = True` on success.

```python
def _l10n_gr_prov_upload_pdf_acme(self):
    self.ensure_one()
    if not self.l10n_gr_prov_invoice_id:
        raise UserError(_('No invoice ID; submit first.'))
    filename, pdf = self._l10n_gr_prov_get_pdf()
    client = AcmeClient(self.company_id)
    client.upload_pdf(self.l10n_gr_prov_invoice_id, filename, pdf)
```

### `_l10n_gr_prov_poll_b2g_status_<provider_key>`

Called periodically by the cron for B2G documents waiting for Peppol delivery
confirmation.

**Contract:**

- Call `self.ensure_one()`.
- Write the status string to `l10n_gr_prov_b2g_status` when it changes.
- Post a chatter message on status change.
- Raise on errors (the cron catches and logs them as warnings).

```python
def _l10n_gr_prov_poll_b2g_status_acme(self):
    self.ensure_one()
    client = AcmeClient(self.company_id)
    data = client.get_status(self.l10n_gr_prov_invoice_id)
    status = data.get('status') or str(data)[:200]
    if status and status != self.l10n_gr_prov_b2g_status:
        self.l10n_gr_prov_b2g_status = status
        self.message_post(body=_('B2G status update: %s', status))
```

---

## Step 4 — Source data available on `self`

Your payload builder has access to everything `l10n_gr_edi` and the base module
have already computed:

| Field | Notes |
|-------|-------|
| `self.l10n_gr_edi_inv_type` | myDATA invoice type code (e.g. `1.1`) |
| `self.l10n_gr_edi_payment_method` | Payment method code `'1'`–`'7'` |
| `line.l10n_gr_edi_cls_category` | Income classification category |
| `line.l10n_gr_edi_cls_type` | Income classification type |
| `line.l10n_gr_edi_tax_exemption_category` | VAT exemption category (for 0% lines) |
| `self.company_id.partner_id.l10n_gr_edi_branch_number` | Branch number (0 = head office) |
| `self.l10n_gr_prov_b2g` | B2G flag |
| `self.l10n_gr_prov_contract_ref` | ΑΔΑΜ (BT-12) |
| `self.l10n_gr_prov_budget_type` / `budget_ref` | Budget type + identifier (BT-11) |
| `self.l10n_gr_prov_purchase_order_ref` | PO reference (BT-13) |
| `self.l10n_gr_prov_buyer_ref` | Buyer reference (BT-10) |
| `partner.l10n_gr_prov_aaht` | Contracting authority ΑΑΗΤ code |
| `line.product_id.l10n_gr_prov_cpv` | CPV code (BT-158) |

Import the VAT category map from `l10n_gr_edi`:

```python
from odoo.addons.l10n_gr_edi.models.preferred_classification import (
    TYPES_WITH_VAT_CATEGORY_8,
    TYPES_WITH_VAT_EXEMPT,
    VALID_TAX_CATEGORY_MAP,
)
```

---

## Step 5 — Checklist before going live

- [ ] `selection_add` uses a unique key (no collision with other installed drivers).
- [ ] Credentials are stored with `groups='base.group_system'`.
- [ ] All three operations are implemented (missing ones raise `UserError` from
  the base dispatch, not a silent no-op).
- [ ] `_l10n_gr_prov_send_*` writes `l10n_gr_prov_mark` before returning;
  the cron and Send & Print rely on this to avoid double-submission.
- [ ] The module is tested with the provider's sandbox before enabling
  production (`l10n_gr_prov_test_env = False`).
