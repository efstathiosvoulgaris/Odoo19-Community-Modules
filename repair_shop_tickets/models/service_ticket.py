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

    job_type_ids = fields.Many2many(
        'service.job.type',
        'service_ticket_job_type_rel',
        'ticket_id', 'job_type_id',
        string='Job Type',
    )
    employee_id = fields.Many2one('hr.employee', string='Assigned Technician')
    fixes_needed = fields.Text(string='Customer Notes')
    technician_notes = fields.Text(string='Technician Notes')
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

    notified = fields.Boolean(string='Customer Notified', readonly=True, copy=False, tracking=True)
    notified_date = fields.Datetime(string='Notified On', readonly=True, copy=False)
    notified_uid = fields.Many2one('res.users', string='Notified By', readonly=True, copy=False)
    notified_channel = fields.Selection([
        ('phone', 'Phone'),
        ('sms', 'SMS'),
        ('email', 'Email'),
        ('viber', 'Viber'),
    ], string='Notification Channel', default='phone', copy=False, tracking=True)

    state = fields.Selection([
        ('new', 'New'),
        ('in_progress', 'In Progress'),
        ('waiting_for_parts', 'Waiting for Parts'),
        ('resolved', 'Resolved'),
        ('picked_up', 'Picked Up'),
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

    def _get_outgoing_picking_type(self):
        return self.env['stock.picking.type'].search([
            ('code', '=', 'outgoing'),
            ('warehouse_id.company_id', '=', self.env.company.id),
        ], limit=1)

    def _consume_stock(self):
        if self.stock_consumed:
            return
        source = self.env.ref('stock.stock_location_stock', raise_if_not_found=False)
        picking_type = self._get_outgoing_picking_type()
        if not source or not picking_type:
            return
        eligible = [(l.product_id, l.quantity) for l in self.line_ids
                    if l.product_id and l.quantity > 0 and l.product_id.type != 'service']
        if not eligible:
            return

        picking = self.env['stock.picking'].create({
            'picking_type_id': picking_type.id,
            'partner_id': self.partner_id.id,
            'origin': self.name,
            'location_id': source.id,
            'location_dest_id': picking_type.default_location_dest_id.id,
            'move_ids': [(0, 0, {
                'product_id': product.id,
                'product_uom_qty': qty,
                'product_uom': product.uom_id.id,
                'location_id': source.id,
                'location_dest_id': picking_type.default_location_dest_id.id,
                'origin': self.name,
            }) for product, qty in eligible],
        })
        picking.action_confirm()
        picking.action_assign()

        self.stock_move_ids = [(4, m.id) for m in picking.move_ids]
        self.stock_consumed = True

    def _reverse_stock(self):
        pickings = self.stock_move_ids.mapped('picking_id')
        pending = pickings.filtered(lambda p: p.state not in ('done', 'cancel'))
        done = pickings.filtered(lambda p: p.state == 'done')

        pending.action_cancel()

        for picking in done:
            return_wizard = self.env['stock.return.picking'].with_context(
                active_id=picking.id,
                active_model='stock.picking',
            ).create({})
            return_wizard._create_return()

        self.stock_consumed = False

    def action_resolved(self):
        self.write({'state': 'resolved'})
        self._consume_stock()

    def action_picked_up(self):
        self.write({'state': 'picked_up'})

    def action_notify_customer(self):
        """Record that a human told the customer the device is ready. The chatter
        entry comes from tracking=True on notified/notified_channel."""
        self.write({
            'notified': True,
            'notified_date': fields.Datetime.now(),
            'notified_uid': self.env.user.id,
        })

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
            # ponytail: no account_id — Odoo derives it from the journal / fiscal
            # position. Tax is the company default mapped through the customer's
            # fiscal position, so island rates (17%/13%) follow automatically.
            tax = self.env.company.account_sale_tax_id
            fpos = self.env['account.fiscal.position']._get_fiscal_position(self.partner_id)
            if fpos and tax:
                tax = fpos.map_tax(tax)
            invoice_line_vals.append((0, 0, {
                'name': 'Labor: ' + (', '.join(self.job_type_ids.mapped('name'))
                                     or self.fixes_needed or 'Service Work'),
                'quantity': 1,
                'price_unit': self.labor_price,
                'tax_ids': [(6, 0, tax.ids)],
            }))

        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner_id.id,
            'invoice_line_ids': invoice_line_vals,
            'invoice_origin': self.name,
        })
        self.invoice_id = invoice.id

        if self.line_ids:
            self._consume_stock()

        return self.action_view_invoice()

    def action_view_invoice(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': self.invoice_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _get_receipt_vat_rate(self):
        if self.invoice_id:
            tax = self.invoice_id.invoice_line_ids.tax_ids.filtered(
                lambda t: t.type_tax_use == 'sale' and t.amount_type == 'percent' and t.active
            )[:1]
        else:
            tax = self.env['account.tax'].search([
                ('type_tax_use', '=', 'sale'),
                ('amount_type', '=', 'percent'),
                ('active', '=', True),
                ('company_id', '=', self.env.company.id),
            ], order='amount desc', limit=1)
        if not tax:
            return 0
        rate = tax.amount
        return int(rate) if rate == int(rate) else rate

    def action_print_receipt(self):
        return self.env.ref('repair_shop_tickets.action_report_service_receipt').report_action(self)
