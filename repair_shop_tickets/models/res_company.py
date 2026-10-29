from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    repair_prices_include_tax = fields.Boolean(
        string='Τιμές Δελτίου με ΦΠΑ', default=True,
        help='Ναι: οι τιμές ανταλλακτικών και εργασίας στο δελτίο είναι τελικές (με ΦΠΑ), όπως '
             'στο ταμείο. Όχι: είναι καθαρές και ο ΦΠΑ προστίθεται.')

    repair_labor_product_id = fields.Many2one(
        'product.product', string='Προεπιλεγμένη Εργασία',
        domain="[('type', '=', 'service'), ('sale_ok', '=', True)]",
        help='Το είδος (υπηρεσία) που μπαίνει στη γραμμή εργασίας του '
             'τιμολογίου, όταν ο τύπος εργασίας δεν έχει δικό του. Από αυτό '
             'παίρνει η γραμμή ΦΠΑ, λογαριασμό εσόδων και χαρακτηρισμό myDATA.')
    repair_location_id = fields.Many2one(
        'stock.location', string='Θέση Ανταλλακτικών',
        domain="[('usage', '=', 'internal')]",
        help='Από πού βγαίνουν τα ανταλλακτικά. Κενό = η κύρια θέση αποθήκης.')
    repair_consume_on = fields.Selection([
        ('resolve', 'Στην Επίλυση'),
        ('invoice', 'Στη Δημιουργία Τιμολογίου'),
    ], string='Αφαίρεση Ανταλλακτικών', default='resolve', required=True,
        help='Πότε τα ανταλλακτικά του δελτίου βγαίνουν από την αποθήκη.')
    repair_journal_retail_id = fields.Many2one(
        'account.journal', string='Ημερολόγιο για Ιδιώτες',
        domain="[('type', '=', 'sale')]",
        help='Κενό = αυτόματα: ΑΛΠ (11.1) με ανταλλακτικά, ΑΠΥ (11.2) μόνο '
             'εργασία.')
    repair_journal_business_id = fields.Many2one(
        'account.journal', string='Ημερολόγιο για Επιχειρήσεις',
        domain="[('type', '=', 'sale')]",
        help='Κενό = αυτόματα: Τιμολόγιο Πώλησης (1.1) με ανταλλακτικά, '
             'Τιμολόγιο Παροχής Υπηρεσιών (2.1) μόνο εργασία.')
    repair_receipt_terms = fields.Html(
        string='Όροι στο Δελτίο Παραλαβής',
        help='Τυπώνονται στο δελτίο παραλαβής της συσκευής. Κενό = οι '
             'προεπιλεγμένοι όροι του module.')
    repair_pickup_reminder_days = fields.Integer(
        string='Υπενθύμιση Μη Παραλαβής (ημέρες)', default=14,
        help='Μετά από τόσες ημέρες σε «Επιλύθηκε» χωρίς παραλαβή, μπαίνει '
             'δραστηριότητα στον τεχνικό να ξαναειδοποιήσει τον πελάτη. '
             '0 = καμία υπενθύμιση.')

    # ── Viber messages (the employee sends them; nothing leaves by itself) ──
    repair_viber_ready_text = fields.Text(
        string='Viber: Έτοιμη Συσκευή',
        default='Καλησπέρα σας. Η συσκευή σας {device} (δελτίο {ticket}) είναι '
                'έτοιμη για παραλαβή. {company}',
        help='Πεδία: {customer} {device} {ticket} {amount} {company}')
    # ── Pickup signature on the phone at the till ───────────────────────────
    repair_signature_device_id = fields.Many2one(
        'service.signature.device', string='Συσκευή Υπογραφής',
        help='Το κινητό όπου υπογράφει ο πελάτης στην παραλαβή.')
    repair_sign_text_repaired = fields.Char(
        string='Φράση Υπογραφής: Επισκευάστηκε', default='Παρέλαβα τη συσκευή μου.')
    repair_sign_text_not_repaired = fields.Char(
        string='Φράση Υπογραφής: Δεν Επισκευάστηκε',
        default='Παρέλαβα τη συσκευή μου χωρίς επισκευή.')

    repair_viber_not_repaired_text = fields.Text(
        string='Viber: Δεν Επισκευάστηκε',
        default='Καλησπέρα σας. Η συσκευή σας {device} (δελτίο {ticket}) είναι '
                'διαθέσιμη για παραλαβή. {company}',
        help='Πεδία: {customer} {device} {ticket} {amount} {company}')
