# -*- coding: utf-8 -*-
def migrate(cr, version):
    """Consolidate the duplicate ΔΟΥ/Δραστηριότητα onto the canonical
    l10n_gr_partner fields before the redundant columns are dropped.
    Copy only where the target is empty, so AADE-looked-up data wins."""
    for src, dst in (('l10n_gr_prov_doy', 'doy'),
                     ('l10n_gr_prov_activity', 'drastiriotita')):
        cr.execute("""
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'res_partner' AND column_name = %s
        """, (src,))
        if not cr.fetchone():
            continue
        cr.execute("""
            UPDATE res_partner
               SET {dst} = {src}
             WHERE ({dst} IS NULL OR {dst} = '')
               AND {src} IS NOT NULL AND {src} != ''
        """.format(src=src, dst=dst))
