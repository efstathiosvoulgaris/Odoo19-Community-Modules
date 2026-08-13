# -*- coding: utf-8 -*-
import re

from odoo import fields, models

# Trailing house number: «Γεωργαντά 22», «Λ. Κηφισίας 12-14», «Πατησίων 5Α».
# Anchored at the end so «3ης Σεπτεμβρίου» or «25ης Μαρτίου» keep their digits.
STREET_NUMBER_RE = re.compile(r'^(.*?)[\s,]+(\d[\w\-/]*)$', re.UNICODE)


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # ΔΟΥ and δραστηριότητα are NOT redefined here — they live in
    # l10n_gr_partner as `doy` / `drastiriotita` (filled by the AADE VAT
    # lookup). We consumed those directly; a duplicate pair here only went
    # stale against the AADE data.
    l10n_gr_prov_aaht = fields.Char(
        string='ΑΑΗΤ',
        help='Unique e-invoicing code of the contracting authority (Αναθέτουσα '
             'Αρχή Ηλεκτρονικής Τιμολόγησης) from the ΜΑΑΗΤ registry '
             '(webapps.gsis.gr/dsae2/foreisreg). Used in the B2G buyer '
             'reference (BT-10).',
    )

    def _l10n_gr_prov_street_number(self):
        """(street, number) with the house number separated out.

        AADE wants them apart — BT-36 as its own field, and every address in
        otherDeliveryNoteHeader carries an explicit `number`. Odoo has no such
        field: `l10n_gr_partner` adds «Αριθμός» (`arithmos_odou`), which the
        AADE VAT lookup fills, but a hand-typed partner keeps everything in
        `street` («Γεωργαντά 22») and the number reaches the provider empty —
        MDP-0024 / MDP-0026.

        Order: the explicit field, then street2, then split the trailing number
        off `street`. The split is a fallback for existing data, not a licence
        to leave «Αριθμός» empty — an address with no trailing number (a square,
        a village) still comes back with an empty number and is caught by
        validation before the document goes out.
        """
        self.ensure_one()
        street = (self.street or '').strip()
        explicit = (getattr(self, 'arithmos_odou', '') or self.street2 or '').strip()
        match = STREET_NUMBER_RE.match(street)
        trailing = match.group(2) if match else ''
        number = explicit or trailing
        # Strip the number off the street only when it is the number we send —
        # otherwise filling «Αριθμός» on a partner whose street already reads
        # «Γεωργαντά 22» would transmit «Γεωργαντά 22» + «22».
        if trailing and number == trailing:
            street = match.group(1).strip()
        return street, number
