from odoo import _, fields, models


def _path(name):
    return ' / '.join(part.strip() for part in (name or '').split('/'))


class ProductCategory(models.Model):
    _inherit = 'product.category'

    qol_public_categ_id = fields.Many2one(
        'product.public.category', 'Κατηγορία eShop', index='btree_not_null',
        help='Μπαίνει μόνη της στο είδος όταν του δίνετε αυτή την κατηγορία.')
    qol_no_eshop = fields.Boolean(
        'Χωρίς eShop',
        help='Η «Σύνδεση με eShop» δεν συνδέει ούτε δημιουργεί κατηγορία eShop για αυτή '
             'την κατηγορία (π.χ. υπηρεσίες, έξοδα).')

    def write(self, vals):
        if vals.get('qol_no_eshop'):
            # off the site means no eShop category handed to its products either
            vals = dict(vals, qol_public_categ_id=False)
        return super().write(vals)

    def action_qol_link_public_by_name(self):
        """For categories without an eShop category (and not «Χωρίς eShop»):
        - same path in the eShop («Gaming / Gaming Αξεσουάρ») → link it;
        - the name exists nowhere among the eShop categories made by hand →
          create it at the same place (missing parents too), empty ones too, so
          a category's first product already finds its eShop category;
        - the name exists in a hand-made eShop category elsewhere → left for
          the user to pick (a second «Εκτυπωτές» would duplicate the site's
          menu). Categories this action created are mirrors, never conflicts,
          so «Ποντίκια / Ασύρματα» and «Σετ / Ασύρματα» both get made.
        Categories that must stay off the site get «Χωρίς eShop»."""
        Public = self.env['product.public.category']
        by_path = {_path(c.display_name): c for c in Public.search([])}
        mirrored = self.search([('qol_public_categ_id', '!=', False)]).qol_public_categ_id
        names = {c.name for c in by_path.values() if c not in mirrored}
        # Odoo's root «All / Όλες» is a container, never a shop category
        root = self.env.ref('product.product_category_all', raise_if_not_found=False)
        todo = self.filtered(lambda c: not c.qol_public_categ_id and not c.qol_no_eshop
                             and c != root).sorted('complete_name')
        created = pick = 0
        for categ in todo:
            path = _path(categ.complete_name)
            if path in by_path:
                continue
            if categ.name in names:
                pick += 1
                continue
            parent = Public
            parts = path.split(' / ')
            for depth in range(1, len(parts) + 1):
                sub = ' / '.join(parts[:depth])
                if sub not in by_path:
                    by_path[sub] = Public.create({'name': parts[depth - 1], 'parent_id': parent.id})
                    created += 1
                parent = by_path[sub]
        linked = 0
        for categ in todo:
            public = by_path.get(_path(categ.complete_name))
            if public:
                categ.qol_public_categ_id = public
                linked += 1
        return self._qol_notify(_(
            '%(linked)s κατηγορίες συνδέθηκαν (%(created)s κατηγορίες eShop δημιουργήθηκαν), '
            '%(pick)s έχουν ίδιο όνομα σε άλλη θέση του eShop — διαλέξτε τις με το χέρι.',
            linked=linked, created=created, pick=pick))

    def action_qol_apply_public_to_products(self):
        """Give the linked eShop category to this category's products that have
        none yet. Products with an eShop category already are not touched."""
        count = 0
        for categ in self.filtered('qol_public_categ_id'):
            products = self.env['product.template'].search([
                ('categ_id', '=', categ.id), ('public_categ_ids', '=', False)])
            products.write({'public_categ_ids': [(4, categ.qol_public_categ_id.id)]})
            count += len(products)
        return self._qol_notify(_('%s είδη πήραν κατηγορία eShop.', count))

    def _qol_notify(self, message):
        return {'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'type': 'success', 'message': message, 'sticky': False,
                           'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'}}}
