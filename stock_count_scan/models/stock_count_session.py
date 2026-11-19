from collections import defaultdict
from datetime import datetime, time

import pytz

from odoo import api, fields, models
from odoo.exceptions import UserError


class StockCountSession(models.Model):
    _name = 'stock.count.session'
    _description = 'Απογραφή με σκανάρισμα'
    _inherit = ['mail.thread']
    _order = 'accounting_date desc, id desc'

    name = fields.Char('Περιγραφή', required=True, tracking=True,
                       default=lambda self: 'Απογραφή %s' % fields.Date.context_today(self).year)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    location_id = fields.Many2one(
        'stock.location', 'Θέση', required=True, tracking=True,
        domain="[('usage', '=', 'internal'), ('company_id', 'in', [company_id, False])]",
        default=lambda self: self.env['stock.warehouse'].search(
            [('company_id', '=', self.env.company.id)], limit=1).lot_stock_id,
        help='Μετράμε αυτή τη θέση μαζί με τις υπο-θέσεις της.')
    accounting_date = fields.Date(
        'Λογιστική ημερομηνία', required=True, tracking=True,
        help='Οι διορθώσεις της απογραφής καταχωρούνται με αυτή την ημερομηνία (τέλος ημέρας). '
             'Το μέτρημα μπορεί να γίνει και αργότερα με κινήσεις ενδιάμεσα: κάθε είδος '
             'συγκρίνεται με το απόθεμα της στιγμής που σκαναρίστηκε τελευταία φορά.')
    state = fields.Selection([('draft', 'Πρόχειρη'), ('counting', 'Σε μέτρημα'), ('done', 'Ολοκληρώθηκε')],
                             default='draft', required=True, tracking=True)
    line_ids = fields.One2many('stock.count.session.line', 'session_id', 'Μετρήσεις')
    line_count = fields.Integer('Είδη', compute='_compute_totals')
    total_qty = fields.Float('Τεμάχια', compute='_compute_totals')
    skipped_info = fields.Text('Δεν διορθώθηκαν', readonly=True)

    @api.depends('line_ids.qty')
    def _compute_totals(self):
        for session in self:
            session.line_count = len(session.line_ids)
            session.total_qty = sum(session.line_ids.mapped('qty'))

    def action_start(self):
        for session in self.filtered(lambda s: s.state == 'draft'):
            # Counting while selling needs each sale to move stock when it happens.
            if session.company_id._fields.get('point_of_sale_update_stock_quantities') and \
                    session.company_id.point_of_sale_update_stock_quantities == 'closing':
                raise UserError('Το Ταμείο (POS) ενημερώνει το απόθεμα στο κλείσιμο της συνεδρίας· '
                                'οι πωλήσεις κατά το μέτρημα θα μετρούσαν λάθος. Ρυθμίσεις → Point of Sale → '
                                'ενημέρωση ποσοτήτων «σε πραγματικό χρόνο» και ξανά «Έναρξη».')
            session.state = 'counting'

    def action_open_scan(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'stock_count_scan.scan',
            'name': self.name,
            'params': {'session_id': self.id},
        }

    # ---- scanning (called by the scan screen, one RPC per scan) ----

    def _find_product(self, code):
        Product = self.env['product.product'].with_company(self.company_id)
        domain = [('company_id', 'in', [self.company_id.id, False])]
        return (Product.search(domain + [('barcode', '=', code)], limit=1)
                or Product.search(domain + [('default_code', '=ilike', code)], limit=1))

    def scan(self, code, qty=1):
        """+qty (or -qty) for the product whose barcode/internal reference is `code`."""
        self.ensure_one()
        code = (code or '').strip()
        if self.state != 'counting':
            return {'error': 'Η απογραφή δεν είναι «Σε μέτρημα».'}
        product = self._find_product(code)
        if not product:
            return {'error': 'Δεν βρέθηκε είδος με κωδικό «%s».' % code}
        if not product.is_storable:
            return {'error': '«%s» δεν είναι είδος αποθήκης.' % product.display_name}
        if product.tracking != 'none':
            return {'error': '«%s» έχει παρτίδα/σειριακό· μετρήστε το από τη Φυσική Απογραφή.' % product.display_name}
        # Several scanners count the same session: every scan touches the session row, so
        # two scans at the same moment collide and Odoo retries the second one with fresh
        # data — both +1 are kept, no duplicate line.
        # ponytail: one row per session serialises all scanners; fine for a few guns.
        self.env.cr.execute('UPDATE stock_count_session SET write_date = now() WHERE id = %s', [self.id])
        line = self.env['stock.count.session.line'].search(
            [('session_id', '=', self.id), ('product_id', '=', product.id)], limit=1)
        if line:
            line.write({'qty': max(line.qty + qty, 0), 'counted_at': fields.Datetime.now()})
        elif qty > 0:
            line = self.env['stock.count.session.line'].create({
                'session_id': self.id, 'product_id': product.id, 'qty': qty})
        else:
            return {'error': '«%s» δεν έχει μετρηθεί ακόμα.' % product.display_name}
        return {'product': product.display_name, 'qty': line.qty, **self.scan_status()}

    def scan_status(self):
        self.ensure_one()
        Line = self.env['stock.count.session.line']
        recent = Line.search([('session_id', '=', self.id)], order='counted_at desc', limit=15)
        [(count, total)] = Line._read_group([('session_id', '=', self.id)], aggregates=['__count', 'qty:sum'])
        return {
            'state': self.state,
            'line_count': count,
            'total_qty': total,
            'recent': [{'product': l.product_id.display_name, 'qty': l.qty} for l in recent],
        }

    # ---- closing ----

    def _end_of_accounting_date(self):
        tz = pytz.timezone(self.env.user.tz or 'UTC')
        local = tz.localize(datetime.combine(self.accounting_date, time(23, 59, 59)))
        # Closing on the accounting date itself: never date moves in the future.
        return min(local.astimezone(pytz.utc).replace(tzinfo=None), fields.Datetime.now())

    def action_finish(self):
        self.ensure_one()
        if not self.env.user.has_group('stock.group_stock_manager'):
            raise UserError('Την απογραφή την ολοκληρώνει μόνο ο υπεύθυνος αποθήκης.')
        if self.state != 'counting':
            raise UserError('Η απογραφή δεν είναι «Σε μέτρημα».')
        if self.accounting_date > fields.Date.context_today(self):
            raise UserError('Η λογιστική ημερομηνία δεν μπορεί να είναι μελλοντική.')

        now = fields.Datetime.now()
        Quant = self.env['stock.quant'].with_context(active_test=False)
        locations = self.env['stock.location'].search([('id', 'child_of', self.location_id.id)])
        quants = Quant.search([('location_id', 'in', locations.ids)])

        counted = {l.product_id: l for l in self.line_ids}
        on_hand = defaultdict(float)
        for quant in quants.filtered(lambda q: q.product_id.is_storable):
            on_hand[quant.product_id] += quant.quantity
        products = self.env['product.product'].union(*counted, *on_hand).filtered('is_storable')
        tracked = products.filtered(lambda p: p.tracking != 'none')
        products -= tracked

        # When was each product counted? Unscanned ones count as "now" (= 0 right now).
        when = {p: counted[p].counted_at if p in counted else now for p in products}
        # Net stock change in the counted locations after that moment
        # (sales/purchases made while counting), so diff = counted - stock at count time.
        net_after = defaultdict(float)
        if products:
            mls = self.env['stock.move.line'].search([
                ('state', '=', 'done'), ('product_id', 'in', products.ids),
                ('date', '>', min(when.values())),
                '|', ('location_id', 'in', locations.ids), ('location_dest_id', 'in', locations.ids),
            ])
            for ml in mls:
                if ml.date <= when[ml.product_id]:
                    continue
                into = ml.location_dest_id in locations
                if into != (ml.location_id in locations):
                    net_after[ml.product_id] += ml.quantity_product_uom if into else -ml.quantity_product_uom

        to_apply = Quant
        for product in products:
            qty_at_count = on_hand[product] - net_after[product]
            diff = (counted[product].qty if product in counted else 0) - qty_at_count
            if product.uom_id.compare(diff, 0) == 0:
                continue
            # ponytail: the correction goes to the session location itself even if the stock
            # sits in sub-locations; totals are right, per-shelf split is not kept.
            quant = Quant._gather(product, self.location_id, strict=True)[:1] or \
                Quant.with_context(inventory_mode=True).create({
                    'product_id': product.id, 'location_id': self.location_id.id})
            vals = {'inventory_quantity': quant.quantity + diff}
            if 'accounting_date' in quant._fields:  # stock_account installed
                vals['accounting_date'] = self.accounting_date
            quant.with_context(inventory_mode=True).write(vals)
            to_apply |= quant

        if to_apply:
            to_apply.with_context(inventory_name=self.name)._apply_inventory(self._end_of_accounting_date())
        self.write({
            'state': 'done',
            'skipped_info': '\n'.join(tracked.mapped('display_name')) or False,
        })
        self.message_post(body='Ολοκληρώθηκε: %s διορθώσεις αποθέματος με ημερομηνία %s.' % (
            len(to_apply), self.accounting_date))
        return True


class StockCountSessionLine(models.Model):
    _name = 'stock.count.session.line'
    _description = 'Μέτρηση είδους'
    _order = 'counted_at desc'

    session_id = fields.Many2one('stock.count.session', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='session_id.company_id', store=True)
    product_id = fields.Many2one('product.product', 'Είδος', required=True,
                                 domain=[('is_storable', '=', True), ('tracking', '=', 'none')])
    barcode = fields.Char(related='product_id.barcode')
    default_code = fields.Char(related='product_id.default_code')
    qty = fields.Float('Μετρήθηκαν')
    counted_at = fields.Datetime('Τελευταίο σκανάρισμα', default=fields.Datetime.now, required=True)

    _product_unique = models.Constraint('UNIQUE(session_id, product_id)',
                                        'Το είδος υπάρχει ήδη σε αυτή την απογραφή.')
