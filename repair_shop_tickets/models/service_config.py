from odoo import fields, models


class ServiceJobType(models.Model):
    _name = 'service.job.type'
    _description = 'Service Job Type'
    _order = 'name'

    name = fields.Char(string='Job Type', required=True)
    product_id = fields.Many2one(
        'product.product', string='Είδος Εργασίας',
        domain="[('type', '=', 'service'), ('sale_ok', '=', True)]",
        help='Η υπηρεσία που τιμολογείται για αυτή την εργασία. Η τιμή της '
             'συμπληρώνει την τιμή εργασίας του δελτίου. Κενό = η Προεπιλεγμένη '
             'Εργασία των ρυθμίσεων.')
    list_price = fields.Float(related='product_id.lst_price', string='Τιμή')


class ServiceBrand(models.Model):
    _name = 'service.brand'
    _description = 'Service Brand'
    _order = 'name'

    name = fields.Char(string='Brand', required=True)
    product_model_ids = fields.One2many('service.product.model', 'brand_id', string='Models')


class ServiceProductModel(models.Model):
    _name = 'service.product.model'
    _description = 'Product Model'
    _order = 'name'

    name = fields.Char(string='Model', required=True)
    brand_id = fields.Many2one('service.brand', string='Brand', required=True, ondelete='cascade')
