# -*- coding: utf-8 -*-
from odoo import fields, models

# AADE «Είδος Ποσότητας» (myDATA v2.0.1 §8.13)
MEASUREMENT_UNITS = [
    ('1', '1 - Τεμάχια'),
    ('2', '2 - Κιλά'),
    ('3', '3 - Λίτρα'),
    ('4', '4 - Μέτρα'),
    ('5', '5 - Τετραγωνικά Μέτρα'),
    ('6', '6 - Κυβικά Μέτρα'),
    ('7', '7 - Τεμάχια (Λοιπές Περιπτώσεις)'),
]

# Odoo unit xmlid → AADE code. Only units that ARE the AADE unit are mapped:
# a line in δωδεκάδες, γραμμάρια or λίβρες would send a quantity that does not
# match the declared unit, so those fall back to code 7, which carries the real
# unit name in otherMeasurementUnitTitle.
UOM_UNIT_MAP = {
    'uom.product_uom_unit': '1',
    'uom.product_uom_kgm': '2',
    'uom.product_uom_litre': '3',
    'uom.product_uom_meter': '4',
    'uom.product_uom_square_meter': '5',
    'uom.product_uom_cubic_meter': '6',
}


class UomUom(models.Model):
    _inherit = 'uom.uom'

    l10n_gr_prov_measurement_unit = fields.Selection(
        MEASUREMENT_UNITS, string='Είδος Ποσότητας (myDATA)',
        help='Κωδικός μονάδας μέτρησης ΑΑΔΕ (§8.13) που διαβιβάζεται στα '
             'παραστατικά διακίνησης. Κενό = διαβιβάζεται ως 7 (Λοιπές '
             'Περιπτώσεις) με το όνομα της μονάδας.')

    def _l10n_gr_prov_map_units(self):
        """Stamp the AADE code on the standard Odoo units. Idempotent — only
        fills blanks, so manual choices survive. Returns the number stamped."""
        mapped = 0
        for xmlid, code in UOM_UNIT_MAP.items():
            uom = self.env.ref(xmlid, raise_if_not_found=False)
            if uom and not uom.l10n_gr_prov_measurement_unit:
                uom.l10n_gr_prov_measurement_unit = code
                mapped += 1
        return mapped
