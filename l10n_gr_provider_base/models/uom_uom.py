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

# AADE §8.13 code → UN/ECE Rec 20 code, for invoicedQuantityUnits (BT-130) on
# the EN16931 side of the payload. Derived from the AADE code rather than kept
# as a second field, so the unit the buyer reads can never disagree with the
# one AADE was told. 7 (Λοιπές Περιπτώσεις) is a pieces variant, hence EA.
REC20_BY_AADE_UNIT = {
    '1': 'EA',      # τεμάχια
    '2': 'KGM',     # κιλά
    '3': 'LTR',     # λίτρα
    '4': 'MTR',     # μέτρα
    '5': 'MTK',     # τετραγωνικά μέτρα
    '6': 'MTQ',     # κυβικά μέτρα
    '7': 'EA',
}


class UomUom(models.Model):
    _inherit = 'uom.uom'

    l10n_gr_prov_measurement_unit = fields.Selection(
        MEASUREMENT_UNITS, string='Είδος Ποσότητας (myDATA)',
        help='Κωδικός μονάδας μέτρησης ΑΑΔΕ (§8.13) που διαβιβάζεται στα '
             'παραστατικά διακίνησης. Κενό = διαβιβάζεται ως 7 (Λοιπές '
             'Περιπτώσεις) με το όνομα της μονάδας.')

    def _l10n_gr_prov_map_units(self):
        """Make the six AADE units usable and stamp their §8.13 code.

        The units themselves ship with Odoo, so unlike the journals there is
        nothing to create — but Odoo archives m³ out of the box, which left
        «Κυβικά Μέτρα» stamped and unpickable. Unarchiving is the «create»
        half of the job.

        Idempotent: only fills blank codes, so a manual choice survives.
        Returns {mapped, activated, unmapped} for the settings notification;
        `unmapped` counts the active units still without a code, each of which
        transmits as 7 (Λοιπές Περιπτώσεις) with its name."""
        mapped = activated = 0
        for xmlid, code in UOM_UNIT_MAP.items():
            uom = self.env.ref(xmlid, raise_if_not_found=False)
            if not uom:
                continue
            if not uom.active:
                uom.active = True
                activated += 1
            if not uom.l10n_gr_prov_measurement_unit:
                uom.l10n_gr_prov_measurement_unit = code
                mapped += 1
        archived = self._l10n_gr_prov_archive_unused_units()
        return {
            'units': mapped,
            'units_activated': activated,
            'units_archived': archived,
            'units_unmapped': self.search_count(
                [('l10n_gr_prov_measurement_unit', '=', False)]),
        }

    def _l10n_gr_prov_archive_unused_units(self):
        """Archive active units with no §8.13 code that nothing refers to.

        A unit without a code transmits as 7 (Λοιπές Περιπτώσεις), so the fewer
        of them the picker offers, the fewer accidents. Anything carrying a code
        is left alone, and so is anything in use.

        «In use» is answered by scanning every stored relational field in the
        registry that points at uom.uom, rather than by listing models: that
        covers products, invoice/stock/sale/purchase lines and whatever else is
        installed — and, crucially, `uom.uom.relative_uom_id`, which is what
        keeps g, ml and mm alive as the base of kg, L and m. Archived referrers
        count as use too, so unarchiving cm later does not find a dead base.

        Reversible from Μονάδες Μέτρησης → φίλτρο «Archived»."""
        candidates = self.search([('l10n_gr_prov_measurement_unit', '=', False)])
        if not candidates:
            return 0
        referrers = []
        for field in self.env['ir.model.fields'].sudo().search([
                ('relation', '=', 'uom.uom'),
                ('ttype', 'in', ('many2one', 'many2many')),
                ('store', '=', True)]):
            model = self.env.get(field.model)
            if model is None or model._transient or not model._auto:
                continue
            if field.name not in model._fields or not model._fields[field.name].store:
                continue
            referrers.append((model.sudo().with_context(active_test=False), field.name))
        unused = self.browse()
        for uom in candidates:
            if not any(model.search_count([(name, '=', uom.id)], limit=1)
                       for model, name in referrers):
                unused |= uom
        unused.active = False
        return len(unused)
