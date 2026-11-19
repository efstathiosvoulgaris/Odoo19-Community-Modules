import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    qol_no_auto_publish = fields.Boolean(
        'Χωρίς αυτόματη δημοσίευση',
        help='Το eshop δεν ακολουθεί το απόθεμα για αυτό το προϊόν: δημοσίευση και απόσυρση '
             'γίνονται μόνο με το χέρι.')

    @api.model_create_multi
    def create(self, vals_list):
        products = super().create(vals_list)
        for product, vals in zip(products, vals_list):
            public = product.categ_id.qol_public_categ_id
            if public and 'public_categ_ids' not in vals:
                product.public_categ_ids = [(4, public.id)]
        return products

    def write(self, vals):
        """New category → its eShop category; the previous category's eShop
        category goes, ones added by hand stay. Skipped when the same save
        sets the eShop categories itself."""
        if 'categ_id' not in vals or 'public_categ_ids' in vals:
            return super().write(vals)
        old = {p.id: p.categ_id.qol_public_categ_id for p in self}
        res = super().write(vals)
        for product in self:
            new = product.categ_id.qol_public_categ_id
            if not new:
                continue
            cmds = [(4, new.id)]
            if old[product.id] and old[product.id] != new:
                cmds.insert(0, (3, old[product.id].id))
            super(ProductTemplate, product).write({'public_categ_ids': cmds})
        return res

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
