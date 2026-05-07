from odoo import api, fields, models, _


class ServiceTicketLine(models.Model):
    _name = 'service.ticket.line'
    _description = 'Service Ticket Part'

    ticket_id = fields.Many2one('service.ticket', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Part', required=True)
    name = fields.Char(string='Description')
    quantity = fields.Float(string='Qty', default=1.0)
    price_unit = fields.Float(string='Unit Price')
    price_subtotal = fields.Float(string='Subtotal', compute='_compute_subtotal', store=True)

    @api.depends('quantity', 'price_unit')
    def _compute_subtotal(self):
        for line in self:
            line.price_subtotal = line.quantity * line.price_unit

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.name = self.product_id.name
            self.price_unit = self.product_id.lst_price


class ServiceTicket(models.Model):
    _name = 'service.ticket'
    _description = 'Service Ticket'
    _order = 'create_date desc, id desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Ticket Reference', required=True, copy=False, readonly=True,
                       index=True, default=lambda self: _('New'))

    partner_id = fields.Many2one('res.partner', string='Customer')
    phone = fields.Char(related='partner_id.phone', string='Phone', readonly=True)

    brand_id = fields.Many2one('service.brand', string='Brand')
    product_model_id = fields.Many2one('service.product.model', string='Model',
                                       domain="[('brand_id', '=', brand_id)]")

    job_type_id = fields.Many2one('service.job.type', string='Job Type')
    fixes_needed = fields.Text(string='Notes')
    labor_price = fields.Float(string='Labor Price')
    total_price = fields.Float(string='Total', compute='_compute_total', store=True)

    line_ids = fields.One2many('service.ticket.line', 'ticket_id', string='Parts')

    invoice_id = fields.Many2one('account.move', string='Invoice', readonly=True, copy=False)

    stock_move_ids = fields.Many2many(
        'stock.move',
        'service_ticket_stock_move_rel',
        'ticket_id', 'move_id',
        string='Stock Moves',
        copy=False,
    )
    stock_move_count = fields.Integer(compute='_compute_stock_move_count', store=True, depends=['stock_move_ids'])
    stock_consumed = fields.Boolean(string='Stock Consumed', copy=False)

    state = fields.Selection([
        ('new', 'New'),
        ('in_progress', 'In Progress'),
        ('waiting_for_parts', 'Waiting for Parts'),
        ('resolved', 'Resolved'),
        ('ready_for_pickup', 'Ready for Pickup'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='new', group_expand='_read_group_state')

    @api.depends('line_ids.price_subtotal', 'labor_price')
    def _compute_total(self):
        for rec in self:
            rec.total_price = sum(rec.line_ids.mapped('price_subtotal')) + rec.labor_price

    @api.model_create_multi
    def create(self, vals_list):
        new_placeholder = _('New')
        for vals in vals_list:
            if vals.get('name', new_placeholder) == new_placeholder:
                vals['name'] = self.env['ir.sequence'].next_by_code('service.ticket') or new_placeholder
        return super().create(vals_list)

    @api.model
    def _read_group_state(self, states, domain):
        return [s[0] for s in self._fields['state'].selection]

    def action_in_progress(self):
        self.write({'state': 'in_progress'})

    def action_waiting_for_parts(self):
        self.write({'state': 'waiting_for_parts'})

    def _compute_stock_move_count(self):
        for rec in self:
            rec.stock_move_count = len(rec.stock_move_ids)

    def _get_consumption_locations(self):
        source = self.env.ref('stock.stock_location_stock', raise_if_not_found=False)
        dest = self.env.ref('stock.location_production', raise_if_not_found=False)
        return source, dest

    def _validate_moves(self, vals_list, qtys, source, dest):
        moves = self.env['stock.move'].create(vals_list)
        moves._action_confirm()
        moves._action_assign()
        move_line_vals = []
        for move, qty in zip(moves, qtys):
            if move.move_line_ids:
                move.move_line_ids[0].quantity = qty
            else:
                move_line_vals.append({
                    'move_id': move.id,
                    'product_id': move.product_id.id,
                    'product_uom_id': move.product_uom.id,
                    'quantity': qty,
                    'location_id': source.id,
                    'location_dest_id': dest.id,
                })
        if move_line_vals:
            self.env['stock.move.line'].create(move_line_vals)
        moves._action_done()
        return moves

    def _consume_stock(self):
        if self.stock_consumed:
            return
        source, dest = self._get_consumption_locations()
        if not source or not dest:
            return
        eligible = [(l.product_id, l.quantity) for l in self.line_ids
                    if l.product_id and l.quantity > 0 and l.product_id.type != 'service']
        if not eligible:
            return
        vals_list = [{
            'name': self.name,
            'product_id': product.id,
            'product_uom_qty': qty,
            'product_uom': product.uom_id.id,
            'location_id': source.id,
            'location_dest_id': dest.id,
            'origin': self.name,
        } for product, qty in eligible]
        moves = self._validate_moves(vals_list, [q for _, q in eligible], source, dest)
        self.stock_move_ids = [(4, m.id) for m in moves]
        self.stock_consumed = True

    def _reverse_stock(self):
        source, dest = self._get_consumption_locations()
        if not source or not dest:
            return
        done_moves = self.stock_move_ids.filtered(lambda m: m.state == 'done')
        if not done_moves:
            self.stock_consumed = False
            return
        vals_list = [{
            'name': _('Reversal: %s') % self.name,
            'product_id': m.product_id.id,
            'product_uom_qty': m.product_uom_qty,
            'product_uom': m.product_uom.id,
            'location_id': dest.id,
            'location_dest_id': source.id,
            'origin': self.name,
        } for m in done_moves]
        qtys = done_moves.mapped('product_uom_qty')
        reverse_moves = self._validate_moves(vals_list, qtys, dest, source)
        self.stock_move_ids = [(4, m.id) for m in reverse_moves]
        self.stock_consumed = False

    def action_resolved(self):
        self.write({'state': 'resolved'})
        self._consume_stock()

    def action_ready_for_pickup(self):
        self.write({'state': 'ready_for_pickup'})

    def action_reset_to_in_progress(self):
        if self.stock_consumed:
            self._reverse_stock()
        self.write({'state': 'in_progress'})

    def action_cancelled(self):
        if self.stock_consumed:
            self._reverse_stock()
        self.write({'state': 'cancelled'})

    def action_view_stock_moves(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'stock.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.stock_move_ids.ids)],
            'name': _('Stock Moves'),
        }

    def action_create_invoice(self):
        if self.invoice_id:
            return self.action_view_invoice()

        invoice_line_vals = []

        for line in self.line_ids:
            invoice_line_vals.append((0, 0, {
                'product_id': line.product_id.id,
                'name': line.name or line.product_id.display_name,
                'quantity': line.quantity,
                'price_unit': line.price_unit,
            }))

        if self.labor_price:
            account = self.env['account.account'].search([
                ('company_ids', 'in', self.env.company.id),
                ('account_type', 'in', ['income', 'income_other']),
            ], limit=1)
            tax = self.env['account.tax'].search([
                ('type_tax_use', '=', 'sale'),
                ('amount', '=', 24),
                ('active', '=', True),
                ('company_id', '=', self.env.company.id),
            ], limit=1)
            invoice_line_vals.append((0, 0, {
                'name': 'Labor: ' + (self.job_type_id.name or self.fixes_needed or 'Service Work'),
                'quantity': 1,
                'price_unit': self.labor_price,
                'account_id': account.id,
                'tax_ids': [(6, 0, tax.ids)],
            }))

        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner_id.id,
            'invoice_line_ids': invoice_line_vals,
            'invoice_origin': self.name,
        })
        self.invoice_id = invoice.id

        return self.action_view_invoice()

    def action_view_invoice(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': self.invoice_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_print_receipt(self):
        return self.env.ref('service.action_report_service_receipt').report_action(self)
