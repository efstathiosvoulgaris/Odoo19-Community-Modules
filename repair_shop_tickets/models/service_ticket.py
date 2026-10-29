from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools import is_html_empty


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
    mobile = fields.Char(related='partner_id.kinito', string='Κινητό', readonly=True)

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

    # ── Intake: what came in, and in what state — settles «it wasn't like
    # this when I brought it» ───────────────────────────────────────────────
    intake_condition = fields.Text(
        string='Κατάσταση Παραλαβής',
        help='Εμφανής κατάσταση κατά την παραλαβή: γρατζουνιές, ραγισμένη '
             'οθόνη, λείπουν βίδες…')

    resolved_date = fields.Datetime(string='Επιλύθηκε Στις', readonly=True, copy=False)
    # Repaired or not, a resolved ticket takes the same road to pickup; this
    # says which. Set by «Επίλυση» / «Δεν Επισκευάστηκε», cleared by «Επαναφορά».
    repair_result = fields.Selection([
        ('repaired', 'Επισκευάστηκε'),
        ('not_repaired', 'Δεν Επισκευάστηκε'),
    ], string='Αποτέλεσμα', readonly=True, copy=False, tracking=True)
    not_repaired_reason = fields.Text(string='Αιτία Μη Επισκευής', readonly=True, copy=False)

    # ── Pickup: the customer signs on the phone at the till ────────────────
    pickup_signature = fields.Binary(string='Υπογραφή Πελάτη', attachment=True,
                                     readonly=True, copy=False)
    pickup_signed_at = fields.Datetime(string='Υπογράφηκε Στις', readonly=True, copy=False)
    pickup_request_id = fields.Many2one('service.signature.request', readonly=True, copy=False)
    pickup_requested_by = fields.Many2one(related='pickup_request_id.requested_by',
                                          string='Αίτημα Υπογραφής από')
    pickup_unsigned_reason = fields.Text(string='Παραλαβή χωρίς Υπογραφή', readonly=True,
                                         copy=False)

    state = fields.Selection([
        ('new', 'New'),
        ('in_progress', 'In Progress'),
        ('waiting_for_parts', 'Waiting for Parts'),
        ('resolved', 'Resolved'),
        ('picked_up', 'Picked Up'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='new', group_expand='_read_group_state')

    @api.depends('line_ids.price_subtotal', 'line_ids.product_id', 'labor_price',
                 'job_type_ids', 'partner_id', 'repair_result')
    def _compute_total(self):
        """Πάντα το ποσό που πληρώνει ο πελάτης (με ΦΠΑ), όποια κι αν είναι η ρύθμιση τιμών."""
        for rec in self:
            rec.total_price = rec._repair_amounts()['gross']

    # ── Τιμές και ΦΠΑ ─────────────────────────────────────────────────────────
    # Ρύθμιση «Τιμές με ΦΠΑ» (προεπιλογή: ναι): οι τιμές που γράφονται στο δελτίο (ανταλλακτικά
    # από την τιμή πώλησης του προϊόντος, εργασία) είναι τελικές. Αλλιώς είναι καθαρές.

    def _repair_prices_gross(self):
        return self.env.company.repair_prices_include_tax

    def _repair_line_taxes(self, product):
        """Οι φόροι πώλησης μιας γραμμής, μετά τη φορολογική θέση του πελάτη (π.χ. νησιά)."""
        self.ensure_one()
        company = self.env.company
        if product:
            taxes = product.taxes_id.filtered(lambda t: t.company_id in (company, company.root_id))
        else:
            taxes = company.account_sale_tax_id
        fpos = self.env['account.fiscal.position']._get_fiscal_position(self.partner_id) \
            if self.partner_id else False
        return fpos.map_tax(taxes) if fpos else taxes

    @staticmethod
    def _repair_rate(taxes):
        return sum(t.amount for t in taxes if t.amount_type == 'percent') / 100.0

    def _repair_split(self, amount, taxes):
        """(καθαρό, ΦΠΑ) ενός ποσού του δελτίου, σύμφωνα με τη ρύθμιση τιμών."""
        rate = self._repair_rate(taxes)
        if self._repair_prices_gross():
            net = amount / (1 + rate) if rate else amount
            return net, amount - net
        return amount, amount * rate

    def _repair_labour_product(self):
        self.ensure_one()
        return self.job_type_ids.product_id[:1] or self.env.company.repair_labor_product_id

    def _repair_charged_lines(self):
        """Parts the customer pays for: none when the device was not repaired."""
        self.ensure_one()
        return self.line_ids if self.repair_result != 'not_repaired' else self.line_ids.browse()

    def _repair_amounts(self):
        """Καθαρό, ΦΠΑ και σύνολο του δελτίου, με τον φόρο κάθε γραμμής."""
        self.ensure_one()
        net = vat = 0.0
        for line in self._repair_charged_lines():
            n, v = self._repair_split(line.price_subtotal, self._repair_line_taxes(line.product_id))
            net, vat = net + n, vat + v
        if self.labor_price:
            n, v = self._repair_split(self.labor_price,
                                      self._repair_line_taxes(self._repair_labour_product()))
            net, vat = net + n, vat + v
        cur = self.env.company.currency_id
        net, vat = cur.round(net), cur.round(vat)
        return {'net': net, 'vat': vat, 'gross': cur.round(net + vat)}

    def _repair_invoice_price(self, amount, taxes):
        """Η τιμή μονάδας για το τιμολόγιο: το Odoo την ερμηνεύει με ή χωρίς ΦΠΑ ανάλογα με
        τον φόρο, οπότε μετατρέπεται μόνο όταν η ρύθμιση του δελτίου διαφέρει από τον φόρο."""
        rate = self._repair_rate(taxes)
        tax_included = any(t.price_include for t in taxes)
        if not rate or tax_included == self._repair_prices_gross():
            return amount
        return amount / (1 + rate) if self._repair_prices_gross() else amount * (1 + rate)

    @api.model_create_multi
    def create(self, vals_list):
        new_placeholder = _('New')
        for vals in vals_list:
            self._check_pickup_signed(vals)
            if vals.get('name', new_placeholder) == new_placeholder:
                vals['name'] = self.env['ir.sequence'].next_by_code('service.ticket') or new_placeholder
        return super().create(vals_list)

    def _check_pickup_signed(self, vals):
        """With a signing device set, «Παραλήφθηκε» only through a signature or
        the manager's fallback (_mark_picked_up) — not a kanban drag, a list
        edit, an import or an RPC, for admin neither. Without one the shop
        works as before 1.9."""
        if vals.get('state') == 'picked_up' and self.env.company.sudo().repair_signature_device_id:
            raise UserError(_('Η παραλαβή ολοκληρώνεται μόνο με υπογραφή πελάτη.'))

    def write(self, vals):
        self._check_pickup_signed(vals)
        return super().write(vals)

    def _mark_picked_up(self, **vals):
        # Past the guard on purpose: the two legitimate ways in.
        return super(ServiceTicket, self).write(dict(vals, state='picked_up'))

    @api.ondelete(at_uninstall=False)
    def _unlink_except_invoiced_or_consumed(self):
        """A ticket with an invoice or with parts out of stock is part of the
        books: deleting it would orphan both. Cancel it instead."""
        locked = self.filtered(lambda t: t.invoice_id or t.stock_consumed)
        if locked:
            raise UserError(_(
                'Τα δελτία %s έχουν τιμολόγιο ή ανταλλακτικά που βγήκαν από την '
                'αποθήκη και δεν διαγράφονται. Χρησιμοποιήστε «Ακύρωση Δελτίου».',
                ', '.join(locked.mapped('name'))))

    @api.model
    def _read_group_state(self, states, domain):
        return [s[0] for s in self._fields['state'].selection]

    @api.onchange('job_type_ids')
    def _onchange_job_type_ids(self):
        """Labour price from the job types' own service products; the default
        labour product when none has one. Still editable afterwards."""
        prices = self.job_type_ids.product_id.mapped('lst_price')
        if prices:
            self.labor_price = sum(prices)
        elif not self.labor_price and self.env.company.repair_labor_product_id:
            self.labor_price = self.env.company.repair_labor_product_id.lst_price

    def action_in_progress(self):
        self.write({'state': 'in_progress'})

    def action_waiting_for_parts(self):
        self.write({'state': 'waiting_for_parts'})

    def _compute_stock_move_count(self):
        for rec in self:
            rec.stock_move_count = len(rec.stock_move_ids)

    def _get_parts_location(self):
        """Where parts are taken from: the setting, else the main stock."""
        return (self.env.company.repair_location_id
                or self.env.ref('stock.stock_location_stock', raise_if_not_found=False))

    def _get_outgoing_picking_type(self, location=None):
        """The delivery type of the warehouse that holds `location`."""
        domain = [('code', '=', 'outgoing'),
                  ('warehouse_id.company_id', '=', self.env.company.id)]
        warehouse = location and location.warehouse_id
        if warehouse:
            domain.append(('warehouse_id', '=', warehouse.id))
        return self.env['stock.picking.type'].search(domain, limit=1)

    def _consume_stock(self):
        if self.stock_consumed:
            return
        source = self._get_parts_location()
        picking_type = self._get_outgoing_picking_type(source)
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
        # The parts left the shelf: complete the delivery, or the stock stays
        # reserved forever and the quantity on hand never goes down.
        self._validate_picking(picking)

    def _validate_picking(self, picking):
        """Complete `picking` when everything is reserved. Otherwise — not in
        stock, or a serial number to pick — leave it open and say so on the
        ticket; completing it by hand from Stock Moves finishes the job."""
        self.ensure_one()
        if picking.state != 'assigned':
            self.message_post(body=_(
                'Η κίνηση αποθήκης %s δεν ολοκληρώθηκε: δεν υπάρχει επαρκές '
                'απόθεμα για όλα τα ανταλλακτικά. Ολοκληρώστε την χειροκίνητα '
                'από τις Κινήσεις Αποθήκης του δελτίου.', picking.name))
            return False
        picking.move_ids.picked = True
        result = picking.with_context(
            skip_backorder=True, picking_ids_not_to_backorder=picking.ids,
        ).button_validate()
        if picking.state != 'done':
            # button_validate asked for something (a wizard) instead of
            # finishing — e.g. a serial number that was not reserved.
            self.message_post(body=_(
                'Η κίνηση αποθήκης %s χρειάζεται ολοκλήρωση με το χέρι (π.χ. '
                'σειριακός αριθμός). Ανοίξτε τη από τις Κινήσεις Αποθήκης.',
                picking.name))
            return result
        return True

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
            # The wizard's lines start at 0 — a return of nothing is refused.
            # Give back exactly what the delivery took out.
            for line in return_wizard.product_return_moves:
                line.quantity = line.move_id.quantity
            action = return_wizard.action_create_returns()
            returned = self.env['stock.picking'].browse(action.get('res_id'))
            if returned:
                self.stock_move_ids = [(4, m.id) for m in returned.move_ids]
                returned.action_assign()
                self._validate_picking(returned)

        self.stock_consumed = False

    def action_resolved(self):
        self.write({'state': 'resolved', 'resolved_date': fields.Datetime.now(),
                    'repair_result': 'repaired'})
        if self.env.company.repair_consume_on == 'resolve':
            for rec in self:
                rec._consume_stock()

    def action_picked_up(self):
        """Ask the customer to sign on the phone; the ticket becomes
        «Παραλήφθηκε» when the signature arrives (service.signature.request)."""
        self.ensure_one()
        if self.state != 'resolved':
            raise UserError(_('Παραλαβή γίνεται μόνο για δελτίο σε «Επιλύθηκε».'))
        device = self.env.company.sudo().repair_signature_device_id
        if not device:
            # No phone configured (yet): pickup without a signature, as before 1.9.
            return self._mark_picked_up()
        if not device.paired:
            raise UserError(_('Η συσκευή υπογραφής «%s» δεν είναι συνδεδεμένη.', device.name))
        device.last_request_at = fields.Datetime.now()
        Request = self.env['service.signature.request'].sudo()
        Request._expire_stale()
        pending = Request.search([('device_id', '=', device.id), ('state', '=', 'pending')],
                                 limit=1)
        if pending and pending.ticket_id != self:
            raise UserError(_('Η συσκευή υπογραφής περιμένει υπογραφή για το %s.',
                              pending.ticket_id.name))
        request = pending or Request.create({
            'ticket_id': self.id,
            'device_id': device.id,
            'kind': self.repair_result or 'repaired',
            'requested_by': self.env.user.id,
        })
        return {
            'type': 'ir.actions.client',
            'tag': 'repair_shop_tickets.signature_wait',
            'params': {'request_id': request.id, 'ticket': self.name},
        }

    def action_pickup_unsigned(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Παραλήφθηκε χωρίς υπογραφή'),
            'res_model': 'service.ticket.pickup.unsigned.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_ticket_id': self.id},
        }

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
        self.write({'state': 'in_progress', 'repair_result': False, 'not_repaired_reason': False})

    def action_not_repaired(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Δεν Επισκευάστηκε'),
            'res_model': 'service.ticket.not.repaired.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_ticket_id': self.id},
        }

    def _set_not_repaired(self, reason, fee):
        """The device goes back unrepaired: no part is charged or leaves stock
        (any that already left come back), the labour price becomes the
        inspection fee."""
        self.ensure_one()
        if self.state not in ('in_progress', 'waiting_for_parts'):
            raise UserError(_('«Δεν Επισκευάστηκε» μόνο για δελτίο σε εξέλιξη.'))
        invoice = self.invoice_id
        if invoice.state == 'posted':
            raise UserError(_(
                'Το δελτίο %(t)s έχει εκδοθέν παραστατικό (%(i)s) που χρεώνει την επισκευή. '
                'Εκδώστε πρώτα πιστωτικό.', t=self.name, i=invoice.name))
        if invoice.state == 'draft':
            invoice.button_cancel()  # it bills parts; a labour-only one can be made again
        if self.stock_consumed:
            self._reverse_stock()
        self.write({
            'state': 'resolved',
            'resolved_date': fields.Datetime.now(),
            'repair_result': 'not_repaired',
            'not_repaired_reason': reason,
            'labor_price': fee,
        })

    def action_cancelled(self):
        for rec in self:
            invoice = rec.invoice_id
            if invoice.state == 'posted':
                raise UserError(_(
                    'Το δελτίο %(t)s έχει εκδοθέν παραστατικό (%(i)s). Εκδώστε πρώτα πιστωτικό '
                    'από το παραστατικό και μετά ακυρώστε το δελτίο.', t=rec.name, i=invoice.name))
            if invoice.state == 'draft':
                invoice.button_cancel()  # το πρόχειρο τιμολόγιο ακολουθεί το δελτίο
            if rec.stock_consumed:
                rec._reverse_stock()
        self.write({'state': 'cancelled'})

    def action_view_stock_moves(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'stock.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.stock_move_ids.ids)],
            'name': _('Stock Moves'),
        }

    INVOICE_STATES = ('resolved', 'picked_up')

    def action_create_invoice(self):
        self.ensure_one()
        if self.invoice_id and self.invoice_id.state != 'cancel':
            return self.action_view_invoice()
        if self.state not in self.INVOICE_STATES:
            raise UserError(_('Τιμολόγιο φτιάχνεται μόνο για επισκευή που έχει επιλυθεί.'))

        invoice_line_vals = []

        for line in self._repair_charged_lines():
            invoice_line_vals.append((0, 0, {
                'product_id': line.product_id.id,
                'name': line.name or line.product_id.display_name,
                'quantity': line.quantity,
                'price_unit': self._repair_invoice_price(
                    line.price_unit, self._repair_line_taxes(line.product_id)),
            }))

        if self.labor_price:
            labour = {
                # Printed on the legal document: Greek.
                'name': _('Εργασία: %s', ', '.join(self.job_type_ids.mapped('name'))
                          or self.fixes_needed or _('Επισκευή')),
                'quantity': 1,
                'price_unit': self._repair_invoice_price(
                    self.labor_price, self._repair_line_taxes(self._repair_labour_product())),
            }
            # A service product carries tax, income account and myDATA
            # classification; Odoo maps its tax through the customer's fiscal
            # position by itself. The job type's own product first.
            product = self._repair_labour_product()
            if product:
                labour['product_id'] = product.id
            else:
                # No product: the company default tax, mapped through the
                # customer's fiscal position so island rates follow.
                tax = self.env.company.account_sale_tax_id
                fpos = self.env['account.fiscal.position']._get_fiscal_position(self.partner_id)
                if fpos and tax:
                    tax = fpos.map_tax(tax)
                labour['tax_ids'] = [(6, 0, tax.ids)]
            invoice_line_vals.append((0, 0, labour))

        invoice_vals = {
            'move_type': 'out_invoice',
            'partner_id': self.partner_id.id,
            'invoice_line_ids': invoice_line_vals,
            'invoice_origin': self.name,
        }
        journal = self._get_invoice_journal()
        if journal:
            invoice_vals['journal_id'] = journal.id
        invoice = self.env['account.move'].create(invoice_vals)
        self.invoice_id = invoice.id

        if self._repair_charged_lines() and self.env.company.repair_consume_on == 'invoice':
            self._consume_stock()

        return self.action_view_invoice()

    def _get_invoice_journal(self):
        """The Greek document a repair calls for, when the database has the
        myDATA journals: parts sold → Απόδειξη Λιανικής (11.1) / Τιμολόγιο
        Πώλησης (1.1); labour only → Απόδειξη Παροχής Υπηρεσιών (11.2) /
        Τιμολόγιο Παροχής Υπηρεσιών (2.1). A business customer is one with a
        company card or an ΑΦΜ. The invoice is a draft — the journal can still
        be changed before posting. Empty = leave Odoo's default."""
        self.ensure_one()
        Journal = self.env['account.journal']
        partner = self.partner_id.commercial_partner_id
        business = bool(partner.is_company or partner.vat)
        company = self.env.company
        chosen = (company.repair_journal_business_id if business
                  else company.repair_journal_retail_id)
        if chosen:
            return chosen
        if 'l10n_gr_edi_inv_type_default' not in Journal._fields:
            return Journal
        goods = any(l.product_id.type != 'service' for l in self._repair_charged_lines())
        inv_type = {
            (True, True): '1.1', (True, False): '2.1',
            (False, True): '11.1', (False, False): '11.2',
        }[(business, goods)]
        domain = [
            ('company_id', '=', self.env.company.id),
            ('type', '=', 'sale'),
            ('l10n_gr_edi_inv_type_default', '=', inv_type),
        ]
        if 'l10n_gr_prov_delivery_note' in Journal._fields:
            domain.append(('l10n_gr_prov_delivery_note', '=', False))
        return Journal.search(domain, limit=1)

    def action_view_invoice(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': self.invoice_id.id,
            'view_mode': 'form',
            'target': 'current',
        }


    PICKUP_REMINDER_SUMMARY = 'Η συσκευή δεν έχει παραληφθεί'

    @api.model
    def _cron_pickup_reminder(self):
        """Repaired devices still on the shelf after the configured number of
        days: an activity for the technician (or whoever opened the ticket) to
        call the customer again. One open reminder per ticket."""
        todo = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
        for company in self.env['res.company'].search([
                ('repair_pickup_reminder_days', '>', 0)]):
            limit = fields.Datetime.subtract(
                fields.Datetime.now(), days=company.repair_pickup_reminder_days)
            tickets = self.search([
                ('state', '=', 'resolved'),
                '|', ('resolved_date', '<=', limit),
                     '&', ('resolved_date', '=', False), ('write_date', '<=', limit),
            ])
            for ticket in tickets.filtered(lambda t: not t.activity_ids.filtered(
                    lambda a: a.summary == self.PICKUP_REMINDER_SUMMARY)):
                ticket.activity_schedule(
                    act_type_xmlid='mail.mail_activity_data_todo' if todo else None,
                    summary=self.PICKUP_REMINDER_SUMMARY,
                    note=_('Επισκευάστηκε πριν από %s ημέρες και δεν έχει '
                           'παραληφθεί. Ειδοποιήστε ξανά τον πελάτη.',
                           company.repair_pickup_reminder_days),
                    user_id=(ticket.employee_id.user_id or ticket.create_uid).id,
                )

    def _get_receipt_terms(self):
        """The shop's own terms for the intake slip, or False for the module's
        defaults. An emptied HTML field is «<p><br></p>», not empty."""
        terms = self.env.company.repair_receipt_terms
        return False if is_html_empty(terms) else terms

    def action_print_receipt(self):
        return self.env.ref('repair_shop_tickets.action_report_service_receipt').report_action(self)
