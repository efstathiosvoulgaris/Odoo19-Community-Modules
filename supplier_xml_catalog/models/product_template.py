# -*- coding: utf-8 -*-
from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    is_supplier_feed_product = fields.Boolean(
        string='Προϊόν Feed Προμηθευτή',
        default=False,
        index=True,
        help='Δηλώνει ότι το προϊόν προέρχεται από XML feed προμηθευτή και δεν παρακολουθείται στην αποθήκη.',
    )
    supplier_feed_id = fields.Many2one(
        comodel_name='supplier.xml.feed',
        string='Feed Προμηθευτή',
        ondelete='set null',
        index=True,
    )
    supplier_sku = fields.Char(
        string='Κωδικός Προμηθευτή (SKU)',
        index=True,
        copy=False,
    )
    supplier_cost = fields.Float(
        string='Κόστος Προμηθευτή',
        digits='Product Price',
        help='Τιμή χονδρικής / κόστους από το XML feed.',
    )
    supplier_availability_text = fields.Char(
        string='Διαθεσιμότητα Feed',
        help='Κείμενο διαθεσιμότητας που εμφανίζεται στο eshop (π.χ. "Διαθέσιμο από προμηθευτή")',
    )
    supplier_shipping_text = fields.Char(
        string='Πληροφορίες Αποστολής Feed',
        help='Χρόνος παράδοσης ή σημείωση αποστολής που εμφανίζεται στο eshop.',
    )
    supplier_image_url = fields.Char(
        string='URL Εικόνας Feed',
        help='Αποθηκεύει το τελευταίο συγχρονισμένο URL εικόνας για αποφυγή περιττών λήψεων.',
    )
    supplier_manual_unpublish = fields.Boolean(
        string='Χειροκίνητη Απόσυρση',
        default=False,
        help='Αν ενεργοποιηθεί, το προϊόν δεν θα δημοσιεύεται αυτόματα από το feed ακόμα κι αν έχει απόθεμα ο προμηθευτής.',
    )
    supplier_last_sync = fields.Datetime(
        string='Τελευταίος Συγχρονισμός Feed',
        readonly=True,
    )
