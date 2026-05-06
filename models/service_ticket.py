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

    def action_resolved(self):
        self.write({'state': 'resolved'})

    def action_ready_for_pickup(self):
        self.write({'state': 'ready_for_pickup'})

    def action_reset_to_in_progress(self):
        self.write({'state': 'in_progress'})

    def action_cancelled(self):
        self.write({'state': 'cancelled'})

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
