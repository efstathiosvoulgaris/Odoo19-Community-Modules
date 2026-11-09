# -*- coding: utf-8 -*-
{
    'name': 'Supplier XML Catalog for Website',
    'version': '19.0.1.0.0',
    'category': 'Website/eCommerce',
    'summary': 'Display supplier XML feed products on website without warehouse or stock tracking',
    'description': """
Supplier XML Catalog for Website
================================
- Import and sync products from multiple supplier XML feeds or files.
- Zero warehouse stock impact: imported items are created as non-storable consumables.
- Pricing policies: Markup percentage, fixed margin, rounding, optional VAT calculation.
- Availability policies: Lead times, stock status notes, auto-unpublish when out of stock.
- Shipping details: Supplier lead time and shipping notes displayed on product pages.
- Category and brand mapping (integrates with website_sale_brand if present).
- Smart image synchronization: only downloads images when URL changes.
- Automated scheduled background synchronization.
    """,
    'author': 'eskarlas.gr',
    'license': 'LGPL-3',
    'depends': [
        'website_sale',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/supplier_xml_feed_views.xml',
        'views/product_template_views.xml',
        'views/website_sale_templates.xml',
        'data/ir_cron_data.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
