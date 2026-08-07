# aade_vat_lookup — ΑΦΜ lookup against the AADE registry

**Version:** 1.1 | **Odoo:** 19 | **License:** LGPL-3
**Service:** ΑΑΔΕ «Αναζήτηση Βασικών Στοιχείων Μητρώου Επιχειρήσεων»
(RgWsPublic2)

A button beside the ΑΦΜ field on a contact calls the AADE web service and fills
the rest of the form in.

---

## What it fills

| Odoo field | From |
|------------|------|
| `name`, `eponymia` | Επωνυμία / διακριτικός τίτλος |
| `doy` | Δ.Ο.Υ. |
| `street`, `arithmos_odou`, `zip`, `city` | Registered address |
| `drastiriotita` | Κύρια δραστηριότητα / ΚΑΔ |
| `mydata_entity_type` | Φυσικό / Νομικό πρόσωπο |
| `legal_form` | Fuzzy-matched from `legal_status_descr` |
| `country_id`, `is_company` | Ελλάδα, True |

The ΑΦΜ is stored as 9 digits with no `EL` prefix — what myDATA and the other
Greek ERPs expect.

---

## Behaviour

- The button appears only when the country is Greece or empty.
- It works on **new, unsaved** contacts: no name, no save needed first. The
  fields are written client-side from a small Owl widget.
- An ΑΦΜ inactive at AADE produces a warning rather than silent success.
- Service errors (wrong ΑΦΜ, bad credentials, call-rate limit) are translated
  into a readable message.

---

## Configuration

**Settings → AADE VAT Lookup** — TaxisNet credentials, **per company**.

You need special-purpose TaxisNet credentials for the registry service, issued
from the AADE portal; ordinary login credentials will not authenticate.

---

## Technical

- Endpoint `https://www1.gsis.gr/wsaade/RgWsPublic2/RgWsPublic2`
- SOAP 1.2 with WS-Security `UsernameToken`
- No new Python dependencies — `requests` and `lxml` already ship with Odoo
- Loaded in both the backend and the POS asset bundles, so the button is
  available on the POS customer form too

---

## Changelog

### 1.1
- Credentials and the ΑΦΜ are XML-escaped before entering the SOAP envelope; an
  `&` in a TaxisNet password broke the request.

### 1.0
- Initial public release.
