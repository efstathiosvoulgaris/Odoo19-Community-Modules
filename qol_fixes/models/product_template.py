import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    qol_no_auto_publish = fields.Boolean(
        'Χωρίς αυτόματη δημοσίευση',
        help='Το eshop δεν ακολουθεί το απόθεμα για αυτό το προϊόν: δημοσίευση και απόσυρση '
             'γίνονται μόνο με το χέρι.')

    @api.model
    def _qol_cron_publish_by_stock(self):
        """Eshop = απόθεμα: προϊόν με απόθεμα δημοσιεύεται, χωρίς απόθεμα αποσύρεται. Μόνο
        προϊόντα με παρακολούθηση αποθέματος. Το Skroutz ακολουθεί μόνο του (παίρνει όσα είναι
        δημοσιευμένα και έχουν MPN)."""
        products = self.search([('sale_ok', '=', True), ('is_storable', '=', True),
                                ('qol_no_auto_publish', '=', False)])
        publish = products.filtered(lambda p: p.qty_available > 0 and not p.is_published)
        withdraw = products.filtered(lambda p: p.qty_available <= 0 and p.is_published)
        publish.write({'is_published': True})
        withdraw.write({'is_published': False})
        if publish or withdraw:
            _logger.info('qol_fixes: eshop ← απόθεμα: %d δημοσιεύτηκαν, %d αποσύρθηκαν',
                         len(publish), len(withdraw))
