# -*- coding: utf-8 -*-


def migrate(cr, version):
    """The POS myDATA payment type is now derived live from the method's kind
    (cash→3, card→7, IRIS→8, on-credit→5); the stored field is only an optional
    override. Clear the old blanket '3' that every method carried from the
    previous static default, so the live derivation takes over. Methods a user
    later sets explicitly are respected."""
    cr.execute("UPDATE pos_payment_method SET l10n_gr_prov_payment_type = NULL")
