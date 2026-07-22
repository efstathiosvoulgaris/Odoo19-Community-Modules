# -*- coding: utf-8 -*-
import logging
import re
from xml.sax.saxutils import escape

import requests
from lxml import etree

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

AADE_ENDPOINT = "https://www1.gsis.gr/wsaade/RgWsPublic2/RgWsPublic2"
AADE_TIMEOUT = 15  # seconds

NS = {
    "env": "http://www.w3.org/2003/05/soap-envelope",
    "wsse": "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd",
    "srv": "http://rgwspublic2/RgWsPublic2Service",
    "pub": "http://rgwspublic2/RgWsPublic2",
}

LEGAL_FORM_MAP = [
    ("ae",           ("ΑΕ", "Α.Ε.", "ΑΝΩΝΥΜΗ")),
    ("epe",          ("ΕΠΕ", "Ε.Π.Ε.")),
    ("ike",          ("ΙΚΕ", "Ι.Κ.Ε.", "ΙΔΙΩΤΙΚΗ ΚΕΦΑΛΑΙΟΥΧΙΚΗ")),
    ("oe",           ("ΟΕ", "Ο.Ε.", "ΟΜΟΡΡΥΘΜΗ")),
    ("ee",           ("ΕΕ", "Ε.Ε.", "ΕΤΕΡΟΡΡΥΘΜΗ")),
    ("atomiki",      ("ΑΤΟΜΙΚΗ",)),
    ("syneterismos", ("ΣΥΝΕΤΑΙΡΙΣΜΟΣ",)),
]


def _build_soap_request(username, password, afm):
    # credentials are user input — escape them so &, < etc. can't break the XML
    username, password, afm = escape(username), escape(password), escape(afm)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<env:Envelope xmlns:env="http://www.w3.org/2003/05/soap-envelope"
              xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
              xmlns:srv="http://rgwspublic2/RgWsPublic2Service"
              xmlns:pub="http://rgwspublic2/RgWsPublic2">
  <env:Header>
    <wsse:Security>
      <wsse:UsernameToken>
        <wsse:Username>{username}</wsse:Username>
        <wsse:Password>{password}</wsse:Password>
      </wsse:UsernameToken>
    </wsse:Security>
  </env:Header>
  <env:Body>
    <srv:rgWsPublic2AfmMethod>
      <srv:INPUT_REC>
        <pub:afm_called_by/>
        <pub:afm_called_for>{afm}</pub:afm_called_for>
      </srv:INPUT_REC>
    </srv:rgWsPublic2AfmMethod>
  </env:Body>
</env:Envelope>"""


def _xtext(node, tag):
    """Return stripped text of first descendant element with local-name=tag, or '' if nil/missing."""
    if node is None:
        return ""
    found = node.find(f".//{{*}}{tag}")
    if found is None:
        return ""
    if found.get("{http://www.w3.org/2001/XMLSchema-instance}nil") == "true":
        return ""
    return (found.text or "").strip()


def _guess_legal_form(legal_status_descr):
    if not legal_status_descr:
        return False
    upper = legal_status_descr.upper()
    for code, keywords in LEGAL_FORM_MAP:
        for kw in keywords:
            if kw in upper:
                return code
    return "other"


class ResPartner(models.Model):
    _inherit = "res.partner"

    aade_lookup_visible = fields.Boolean(
        compute="_compute_aade_lookup_visible",
        help="Εμφάνιση κουμπιού άντλησης ΑΑΔΕ μόνο για ελληνικά ΑΦΜ.",
    )

    def _compute_aade_lookup_visible(self):
        gr = self.env.ref("base.gr", raise_if_not_found=False)
        gr_id = gr.id if gr else False
        for rec in self:
            rec.aade_lookup_visible = bool(gr_id) and (
                rec.country_id.id == gr_id or not rec.country_id
            )

    # ──────────────────────────────────────────────────────────────────────
    @api.model
    def aade_lookup_vals(self, vat, existing=None):
        """Κλήση ΑΑΔΕ και επιστροφή dict με {vals, message, type}.

        Δεν κάνει write — η κλήση γίνεται από JS και τα vals
        εφαρμόζονται client-side ώστε να δουλεύει και σε νέες
        (μη αποθηκευμένες) επαφές χωρίς απαιτούμενο όνομα.
        """
        existing = existing or {}
        company = self.env.company
        username = (company.aade_username or "").strip()
        password = company.aade_password or ""
        if not username or not password:
            raise UserError(_(
                "Δεν έχουν οριστεί credentials AADE για την εταιρεία «%s».\n"
                "Ρυθμίσεις → Γενικές Ρυθμίσεις → AADE VAT Lookup."
            ) % company.display_name)

        raw_vat = (vat or "").strip().upper()
        digits = re.sub(r"\D", "", raw_vat)
        if len(digits) != 9:
            raise UserError(_(
                "Το ΑΦΜ πρέπει να περιέχει 9 ψηφία. Δόθηκε: «%s»."
            ) % (vat or ""))

        body = _build_soap_request(username, password, digits)
        headers = {
            "Content-Type": "application/soap+xml; charset=utf-8",
        }
        try:
            resp = requests.post(
                AADE_ENDPOINT,
                data=body.encode("utf-8"),
                headers=headers,
                timeout=AADE_TIMEOUT,
            )
        except requests.RequestException as e:
            _logger.warning("AADE lookup network error: %s", e)
            raise UserError(_("Σφάλμα επικοινωνίας με την ΑΑΔΕ: %s") % e)

        if resp.status_code != 200:
            _logger.warning("AADE lookup HTTP %s: %s", resp.status_code, resp.text[:500])
            raise UserError(_(
                "Η ΑΑΔΕ επέστρεψε HTTP %s.\n%s"
            ) % (resp.status_code, resp.text[:500]))

        try:
            root = etree.fromstring(resp.content)
        except etree.XMLSyntaxError as e:
            raise UserError(_("Μη έγκυρη απάντηση από την ΑΑΔΕ: %s") % e)

        error_code = _xtext(root, "error_code")
        error_descr = _xtext(root, "error_descr")
        if error_code:
            raise UserError(_("Η ΑΑΔΕ επέστρεψε σφάλμα %s: %s") % (error_code, error_descr or ""))

        basic = root.find(".//{*}basic_rec")
        if basic is None:
            raise UserError(_("Δεν επιστράφηκαν στοιχεία επιχείρησης για το ΑΦΜ %s.") % digits)

        deactivation_flag = _xtext(basic, "deactivation_flag")
        deactivation_descr = _xtext(basic, "deactivation_flag_descr")

        onomasia = _xtext(basic, "onomasia")
        commer_title = _xtext(basic, "commer_title")
        doy_descr = _xtext(basic, "doy_descr")
        postal_address = _xtext(basic, "postal_address")
        postal_address_no = _xtext(basic, "postal_address_no")
        postal_zip_code = _xtext(basic, "postal_zip_code")
        postal_area = _xtext(basic, "postal_area_description")
        i_ni_flag = _xtext(basic, "i_ni_flag_descr")
        legal_status = _xtext(basic, "legal_status_descr")

        main_act = ""
        for item in root.findall(".//{*}firm_act_tab/{*}item"):
            kind = _xtext(item, "firm_act_kind")
            if kind == "1":
                main_act = _xtext(item, "firm_act_descr")
                break

        entity_type = False
        if i_ni_flag:
            if "ΜΗ ΦΠ" in i_ni_flag.upper():
                entity_type = "2"
            elif "ΦΠ" in i_ni_flag.upper():
                entity_type = "1"

        vals = {
            "vat": digits,
            "eponymia": onomasia or existing.get("eponymia") or False,
            "doy": doy_descr or existing.get("doy") or False,
            "street": postal_address or existing.get("street") or False,
            "arithmos_odou": postal_address_no or existing.get("arithmos_odou") or False,
            "zip": postal_zip_code or existing.get("zip") or False,
            "city": postal_area or existing.get("city") or False,
            "drastiriotita": main_act or existing.get("drastiriotita") or False,
        }

        if commer_title:
            vals["name"] = commer_title
        elif onomasia:
            vals["name"] = onomasia

        if entity_type:
            vals["mydata_entity_type"] = entity_type

        legal_form = _guess_legal_form(legal_status)
        if legal_form:
            vals["legal_form"] = legal_form

        gr = self.env.ref("base.gr", raise_if_not_found=False)
        if gr:
            vals["country_id"] = {"id": gr.id, "display_name": gr.display_name}

        if not existing.get("is_company"):
            vals["is_company"] = True

        message = _("Τα στοιχεία ενημερώθηκαν από την ΑΑΔΕ.")
        ntype = "success"
        if deactivation_flag and deactivation_flag != "1":
            message = _("Τα στοιχεία ενημερώθηκαν, αλλά ο ΑΦΜ είναι ΑΝΕΝΕΡΓΟΣ (%s).") % (deactivation_descr or "")
            ntype = "warning"

        return {"vals": vals, "message": message, "type": ntype}
