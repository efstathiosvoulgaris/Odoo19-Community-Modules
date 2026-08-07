# -*- coding: utf-8 -*-
from odoo import fields, models


class PosConfig(models.Model):
    _inherit = 'pos.config'

    l10n_gr_prov_catering_notes = fields.Boolean(
        string='Δελτία Παραγγελίας Εστίασης (8.6)', default=True,
        help='Εκδίδει ένα Δελτίο Παραγγελίας ανά αποστολή στην κουζίνα. '
             'Υποχρεωτικό για επιχειρήσεις εστίασης που χρησιμοποιούν Πάροχο '
             '(Α.1138/2020, όπως τροποποιήθηκε με Α.1170/2023).')
    l10n_gr_prov_catering_auto_cancel = fields.Boolean(
        string='Αυτόματη Καθολική Ακύρωση', default=True,
        help='Όταν ακυρώνεται η παραγγελία, διαβιβάζεται «Καθολική Ακύρωση '
             '8.6» που κλείνει τα δελτία της. Χωρίς αυτό, τα δελτία μένουν '
             'ανοιχτά και μετά από 24 ώρες ο πάροχος αναστέλλει τη διαβίβαση '
             'για όλη την επιχείρηση — ακυρώστε τα τότε χειροκίνητα.')
    l10n_gr_prov_catering_auto_negative = fields.Boolean(
        string='Αυτόματο Αρνητικό Δελτίο', default=True,
        help='Όταν αφαιρείται είδος που έχει ήδη σταλεί, διαβιβάζεται αρνητικό '
             'δελτίο (Rec Type 7) για τη διαφορά.')
    l10n_gr_prov_catering_alert_hours = fields.Integer(
        string='Ειδοποίηση Ανοιχτών Δελτίων (ώρες)', default=20,
        help='Ειδοποίηση για δελτία που πλησιάζουν το όριο των 24 ωρών. '
             '0 = καμία ειδοποίηση.')


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    pos_l10n_gr_prov_catering_notes = fields.Boolean(
        related='pos_config_id.l10n_gr_prov_catering_notes', readonly=False)
    pos_l10n_gr_prov_catering_auto_cancel = fields.Boolean(
        related='pos_config_id.l10n_gr_prov_catering_auto_cancel', readonly=False)
    pos_l10n_gr_prov_catering_auto_negative = fields.Boolean(
        related='pos_config_id.l10n_gr_prov_catering_auto_negative', readonly=False)
    pos_l10n_gr_prov_catering_alert_hours = fields.Integer(
        related='pos_config_id.l10n_gr_prov_catering_alert_hours', readonly=False)
