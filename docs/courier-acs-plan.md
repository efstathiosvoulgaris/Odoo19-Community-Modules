# Courier vouchers (courier_vouchers) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create ACS vouchers (A4 labels) from inside Odoo 19 — from a delivery order or standalone to any contact — on a courier-neutral base that later couriers plug into.

**Architecture:** `courier_vouchers` owns the `courier.account` and `courier.voucher` models, the voucher lifecycle, the delivery-order and sale-order hooks and a dispatch layer (`_courier_create` → `_<courier>_create`). **One addon:** each courier is one file inside it — `models/courier_acs.py` adds ACS credentials and the five `_acs_*` methods against the ACS REST API. No dependency on the myDATA addons; **Skroutz is not touched at all** (Skroutz issues its own vouchers).

**Tech Stack:** Odoo 19 (Python 3.12, OWL views in XML), `requests`, ACS REST API (`ACSAutoRest`).

**Spec:** `addons/docs/courier-acs-design.md`

## Global Constraints

- Odoo **19.0**: list views are `<list>`, visibility via `invisible="..."` expressions, no `attrs`/`states`.
- **No Odoo on the dev PC.** Local verification = `python -m py_compile` + XML well-formedness only. The user uploads to the server (`/root/odoo19/extra-addons`).
- Deploy order: **Python changed → `docker restart odoo19` first, then upgrade**; XML only → upgrade. CLI upgrade: `docker exec -u odoo odoo19 /entrypoint.sh odoo -d test -u <module> --stop-after-init --http-port=8070` (install: `-i`).
- **No new test files, no scripted DB writes.** Functional testing is done by Claude in the browser on db `test`, after the user deploys.
- **No per-task commits.** One commit at the end of the day, only when the user asks. The user pushes.
- **Credentials:** the user types them into Odoo. Never print, log, chatter or echo them. Password fields use `password="True"` and `groups="base.group_system"`.
- **Greek text:** write files with the Write/Edit tools, never via a bash heredoc (corrupts Greek).
- ACS has **no test server**: tests only create → print → delete on the same day. Never issue a pickup list during testing.
- Manifest style as `repair_shop_tickets`: author `Efstathios Voulgaris`, support `efstathiosvoulgaris@gmail.com`, license `LGPL-3`, version `1.0`, Changelog in `description`.

## Notes

`carrier_tracking_ref` is defined in core **`stock_delivery`** (which depends on `sale_stock` + `delivery`), so `courier_vouchers` depends on `stock_delivery`. Task 1 step 1 checks it is installed on `test`.

The spec puts «Λίστα Παραλαβής Ημέρας» on the voucher list; the plan puts it on the **courier account form** (one button per account, no guessing which account a list selection means). Same behaviour otherwise.

## File Structure

```
addons/courier_vouchers/
  __init__.py, __manifest__.py
  models/__init__.py
  models/courier_account.py     account + dispatch layer + close-day action
  models/courier_voucher.py     voucher model, lifecycle buttons, cron
  models/stock_picking.py       smart button, «Δημιουργία Voucher», tracking ref
  models/sale_order.py          courier_cod flag
  security/ir.model.access.csv
  data/ir_cron.xml
  views/courier_account_views.xml
  views/courier_voucher_views.xml
  views/stock_picking_views.xml
  views/sale_order_views.xml
  views/courier_menus.xml
  models/courier_acs.py         ACS fields, _acs_call, the five _acs_* methods (Task 4)
  views/courier_acs_views.xml   ACS credential block on the account form (Task 4)
```

A future courier = one more `models/courier_<x>.py` + `views/courier_<x>_views.xml` in the same addon.

---

### Task 1: `courier_vouchers` — accounts, vouchers, menus (installable, no courier yet)

**Files:**
- Create: everything under `addons/courier_vouchers/` except `stock_picking.py`, `sale_order.py`, `stock_picking_views.xml`, `sale_order_views.xml` (Tasks 2–3)

**Interfaces:**
- Produces:
  - `courier.account` with `courier` Selection (empty list, extended with `selection_add`), `sender_name`, `default_weight`, `default_charge_type` (`'sender'|'recipient'`), `pickup_list_attachment_id`.
  - Dispatch: `account._courier_create(voucher) -> str`, `account._courier_print(vouchers) -> bytes`, `account._courier_cancel(voucher) -> None`, `account._courier_close_day(date) -> (str, bytes)`, `account._courier_track(voucher) -> (str state_or_False, str text)`. Each calls `self._<courier>_<method>(...)`; missing → `UserError`.
  - `courier.voucher` fields per spec; methods `action_send()`, `action_print()`, `action_cancel()`, `action_refresh_status()`, `_cron_track()`, `_pickup_date_default()`, `_check_ready()`.

- [ ] **Step 1: Ask the user to confirm `stock_delivery` (Inventory → «Delivery Methods» feature) is installed on `test`**

If it is not, the user installs it from Apps before deploying. Do not install it yourself.

- [ ] **Step 2: Create `courier_vouchers/__init__.py` and `models/__init__.py`**

```python
# courier_vouchers/__init__.py
from . import models
```

```python
# courier_vouchers/models/__init__.py
from . import courier_account
from . import courier_voucher
```

- [ ] **Step 3: Create `courier_vouchers/__manifest__.py`**

```python
{
    'name': 'Courier Vouchers',
    'version': '1.0',
    'category': 'Inventory/Delivery',
    'summary': 'Courier vouchers from delivery orders or standalone',
    'description': (
        'Base for courier integrations: courier accounts, vouchers with the\n'
        'courier lifecycle (create, print, cancel, pickup list, tracking),\n'
        'from a delivery order or standalone to any contact. Each courier\n'
        'is one file inside this addon (models/courier_acs.py, ...).\n'
        '\n'
        'Changelog\n'
        '---------\n'
        '1.0 — Initial release.'
    ),
    'author': 'Efstathios Voulgaris',
    'support': 'efstathiosvoulgaris@gmail.com',
    'license': 'LGPL-3',
    'depends': ['stock_delivery', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_cron.xml',
        'views/courier_account_views.xml',
        'views/courier_voucher_views.xml',
        'views/courier_menus.xml',
    ],
    'installable': True,
    'application': False,
}
```

- [ ] **Step 4: Create `courier_vouchers/models/courier_account.py`**

```python
# -*- coding: utf-8 -*-
import base64

from odoo import _, fields, models
from odoo.exceptions import UserError


class CourierAccount(models.Model):
    _name = 'courier.account'
    _description = 'Λογαριασμός Courier'

    name = fields.Char(string='Όνομα', required=True)
    courier = fields.Selection([], string='Courier', required=True)
    company_id = fields.Many2one(
        'res.company', string='Εταιρεία', required=True,
        default=lambda self: self.env.company)
    active = fields.Boolean(default=True)
    sender_name = fields.Char(
        string='Αποστολέας', required=True,
        help='Το όνομα αποστολέα που τυπώνεται στο voucher.')
    default_weight = fields.Float(string='Προεπιλεγμένο Βάρος (kg)', default=0.5)
    default_charge_type = fields.Selection(
        [('sender', 'Χρέωση Αποστολέα'), ('recipient', 'Χρέωση Παραλήπτη')],
        string='Χρέωση Μεταφορικών', required=True, default='sender')
    pickup_list_attachment_id = fields.Many2one(
        'ir.attachment', string='Τελευταία Λίστα Παραλαβής', readonly=True, copy=False)

    # ── Dispatch: courier_<x> implements _<x>_create, _<x>_print, … ──────────
    def _courier_impl(self, method):
        self.ensure_one()
        impl = getattr(self, f'_{self.courier}_{method}', None)
        if not impl:
            raise UserError(_('Η λειτουργία «%(method)s» δεν υποστηρίζεται για '
                              'τον courier %(courier)s.', method=method, courier=self.courier))
        return impl

    def _courier_create(self, voucher):
        return self._courier_impl('create')(voucher)

    def _courier_print(self, vouchers):
        return self._courier_impl('print')(vouchers)

    def _courier_cancel(self, voucher):
        return self._courier_impl('cancel')(voucher)

    def _courier_close_day(self, date):
        return self._courier_impl('close_day')(date)

    def _courier_track(self, voucher):
        return self._courier_impl('track')(voucher)

    def action_close_day(self):
        """Λίστα Παραλαβής Ημέρας: finalise today's printed vouchers.

        After this the vouchers can no longer be cancelled or reprinted —
        ACS refuses both. Never run it while testing.
        """
        self.ensure_one()
        today = fields.Date.context_today(self)
        vouchers = self.env['courier.voucher'].search([
            ('account_id', '=', self.id), ('state', '=', 'printed'),
            ('pickup_date', '=', today)])
        if not vouchers:
            raise UserError(_('Δεν υπάρχουν τυπωμένα vouchers για σήμερα.'))
        list_no, pdf = self._courier_close_day(today)
        attachment = self.env['ir.attachment'].create({
            'name': f'Λίστα Παραλαβής {list_no}.pdf',
            'datas': base64.b64encode(pdf),
            'mimetype': 'application/pdf',
            'res_model': self._name, 'res_id': self.id,
        })
        self.pickup_list_attachment_id = attachment
        vouchers.write({'state': 'manifested', 'pickup_list_ref': list_no})
        return {'type': 'ir.actions.act_url',
                'url': f'/web/content/{attachment.id}', 'target': 'new'}
```

- [ ] **Step 5: Create `courier_vouchers/models/courier_voucher.py`**

```python
# -*- coding: utf-8 -*-
import base64
import logging
import re
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Same rule as l10n_gr_provider_base res_partner (copied to avoid the
# dependency): trailing house number, anchored at the end.
STREET_NUMBER_RE = re.compile(r'^(.*?)[\s,]+(\d[\w\-/]*)$', re.UNICODE)

STATES = [
    ('draft', 'Πρόχειρο'),
    ('created', 'Δημιουργήθηκε'),
    ('printed', 'Τυπώθηκε'),
    ('manifested', 'Σε Λίστα Παραλαβής'),
    ('cancelled', 'Ακυρώθηκε'),
    ('delivered', 'Παραδόθηκε'),
    ('returned', 'Επιστράφηκε'),
]


def _split_street(partner):
    street = (partner.street or '').strip()
    explicit = (getattr(partner, 'arithmos_odou', '') or partner.street2 or '').strip()
    match = STREET_NUMBER_RE.match(street)
    trailing = match.group(2) if match else ''
    number = explicit or trailing
    if trailing and number == trailing:
        street = match.group(1).strip()
    return street, number


class CourierVoucher(models.Model):
    _name = 'courier.voucher'
    _description = 'Voucher Courier'
    _inherit = ['mail.thread']
    _order = 'id desc'

    name = fields.Char(string='Αριθμός Voucher', readonly=True, copy=False, tracking=True)
    account_id = fields.Many2one(
        'courier.account', string='Λογαριασμός', required=True,
        default=lambda self: self.env['courier.account'].search([], limit=1))
    courier = fields.Selection(related='account_id.courier')
    company_id = fields.Many2one(related='account_id.company_id', store=True)
    picking_id = fields.Many2one('stock.picking', string='Παράδοση', index=True, copy=False)
    sale_order_id = fields.Many2one(related='picking_id.sale_id', store=True, string='Παραγγελία')
    partner_id = fields.Many2one('res.partner', string='Παραλήπτης', required=True)

    recipient_name = fields.Char(string='Όνομα Παραλήπτη', required=True)
    recipient_company = fields.Char(string='Επωνυμία')
    street = fields.Char(string='Οδός', required=True)
    street_number = fields.Char(string='Αριθμός')
    zip = fields.Char(string='Τ.Κ.', required=True)
    city = fields.Char(string='Περιοχή', required=True)
    phone = fields.Char(string='Τηλέφωνο')
    mobile = fields.Char(string='Κινητό')
    email = fields.Char(string='Email')
    country_code = fields.Char(string='Χώρα', default='GR', readonly=True)

    weight = fields.Float(string='Βάρος (kg)', default=0.5)
    item_quantity = fields.Integer(string='Τεμάχια', default=1)
    cod_amount = fields.Monetary(string='Αντικαταβολή', currency_field='currency_id')
    currency_id = fields.Many2one(related='company_id.currency_id')
    notes = fields.Char(string='Σημειώσεις Παράδοσης')
    reference = fields.Char(string='Αναφορά')
    pickup_date = fields.Date(string='Ημ. Παραλαβής', required=True,
                              default=lambda self: self._pickup_date_default())

    state = fields.Selection(STATES, string='Κατάσταση', default='draft',
                             required=True, readonly=True, copy=False, tracking=True)
    label_attachment_id = fields.Many2one('ir.attachment', string='Ετικέτα', readonly=True, copy=False)
    pickup_list_ref = fields.Char(string='Λίστα Παραλαβής', readonly=True, copy=False)
    tracking_status = fields.Char(string='Τελευταία Κατάσταση', readonly=True, copy=False)
    tracking_url = fields.Char(string='Σύνδεσμος Παρακολούθησης', compute='_compute_tracking_url')

    @api.model
    def _pickup_date_default(self):
        day = fields.Date.context_today(self)
        if day.weekday() == 6:  # Sunday — ACS refuses it
            day += timedelta(days=1)
        return day

    @api.depends('name', 'courier')
    def _compute_tracking_url(self):
        for voucher in self:
            impl = getattr(voucher.account_id, f'_{voucher.courier}_tracking_url', None)
            voucher.tracking_url = impl(voucher.name) if impl and voucher.name else False

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        p = self.partner_id
        if not p:
            return
        street, number = _split_street(p)
        self.update({
            'recipient_name': p.name,
            'recipient_company': p.parent_id.name if p.parent_id else False,
            'street': street, 'street_number': number,
            'zip': p.zip, 'city': p.city,
            'phone': p.phone, 'mobile': getattr(p, 'mobile', False) or p.phone,
            'email': p.email,
        })

    @api.onchange('account_id')
    def _onchange_account_id(self):
        if self.account_id and not self.weight:
            self.weight = self.account_id.default_weight

    def _check_ready(self):
        self.ensure_one()
        missing = [label for field, label in (
            ('street', 'Οδός'), ('zip', 'Τ.Κ.'), ('city', 'Περιοχή'),
            ('mobile', 'Κινητό')) if not self[field]]
        if missing:
            raise UserError(_('Λείπουν στοιχεία παραλήπτη: %s', ', '.join(missing)))
        if self.weight < 0.5:
            raise UserError(_('Το ελάχιστο βάρος είναι 0,5 kg.'))
        if self.item_quantity < 1:
            raise UserError(_('Τα τεμάχια πρέπει να είναι τουλάχιστον 1.'))

    def action_send(self):
        """Create at the courier, then print in the same click: ACS refuses
        the pickup list while any voucher is unprinted."""
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_('Το voucher έχει ήδη σταλεί.'))
        self._check_ready()
        number = self.account_id._courier_create(self)
        self.write({'name': number, 'state': 'created'})
        self.message_post(body=_('Δημιουργήθηκε voucher %s.', number))
        self.env.cr.commit()  # the voucher exists at the courier now — keep it even if printing fails
        return self.action_print()

    def action_print(self):
        self.ensure_one()
        if self.state not in ('created', 'printed'):
            raise UserError(_('Εκτύπωση γίνεται μόνο πριν τη λίστα παραλαβής.'))
        pdf = self.account_id._courier_print(self)
        if self.label_attachment_id:
            self.label_attachment_id.datas = base64.b64encode(pdf)
        else:
            self.label_attachment_id = self.env['ir.attachment'].create({
                'name': f'Voucher {self.name}.pdf',
                'datas': base64.b64encode(pdf),
                'mimetype': 'application/pdf',
                'res_model': self._name, 'res_id': self.id,
            })
        self.state = 'printed'
        return {'type': 'ir.actions.act_url',
                'url': f'/web/content/{self.label_attachment_id.id}', 'target': 'new'}

    def action_cancel(self):
        self.ensure_one()
        if self.state == 'draft':
            self.state = 'cancelled'
            return
        if self.state not in ('created', 'printed'):
            raise UserError(_('Το voucher είναι σε λίστα παραλαβής: ακύρωση μόνο '
                              'από την ACS, κατόπιν αιτήματος.'))
        self.account_id._courier_cancel(self)
        self.state = 'cancelled'
        self.message_post(body=_('Το voucher %s ακυρώθηκε στον courier.', self.name))

    def action_refresh_status(self):
        for voucher in self.filtered(lambda v: v.state == 'manifested'):
            new_state, text = voucher.account_id._courier_track(voucher)
            vals = {'tracking_status': text}
            if new_state:
                vals['state'] = new_state
            voucher.write(vals)

    @api.model
    def _cron_track(self):
        for voucher in self.search([('state', '=', 'manifested')]):
            try:
                with self.env.cr.savepoint():
                    voucher.action_refresh_status()
            except Exception:
                _logger.exception('Courier tracking failed for %s', voucher.name)
```

- [ ] **Step 6: Create `courier_vouchers/security/ir.model.access.csv`**

```csv
id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink
access_courier_account_user,courier.account user,model_courier_account,stock.group_stock_user,1,0,0,0
access_courier_account_manager,courier.account manager,model_courier_account,stock.group_stock_manager,1,1,1,1
access_courier_voucher_user,courier.voucher user,model_courier_voucher,stock.group_stock_user,1,1,1,0
access_courier_voucher_manager,courier.voucher manager,model_courier_voucher,stock.group_stock_manager,1,1,1,1
```

- [ ] **Step 7: Create `courier_vouchers/views/courier_account_views.xml`**

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="courier_account_view_list" model="ir.ui.view">
        <field name="name">courier.account.list</field>
        <field name="model">courier.account</field>
        <field name="arch" type="xml">
            <list>
                <field name="name"/>
                <field name="courier"/>
                <field name="company_id" groups="base.group_multi_company"/>
            </list>
        </field>
    </record>

    <record id="courier_account_view_form" model="ir.ui.view">
        <field name="name">courier.account.form</field>
        <field name="model">courier.account</field>
        <field name="arch" type="xml">
            <form>
                <header>
                    <button name="action_close_day" type="object" string="Λίστα Παραλαβής Ημέρας"
                            confirm="Τα σημερινά vouchers οριστικοποιούνται και δεν ακυρώνονται πλέον. Συνέχεια;"/>
                </header>
                <sheet>
                    <group name="main">
                        <group>
                            <field name="name"/>
                            <field name="courier"/>
                            <field name="company_id" groups="base.group_multi_company"/>
                            <field name="active" invisible="1"/>
                        </group>
                        <group>
                            <field name="sender_name"/>
                            <field name="default_weight"/>
                            <field name="default_charge_type"/>
                            <field name="pickup_list_attachment_id"/>
                        </group>
                    </group>
                    <notebook>
                        <page string="Σύνδεση" name="credentials"/>
                    </notebook>
                </sheet>
            </form>
        </field>
    </record>

    <record id="action_courier_account" model="ir.actions.act_window">
        <field name="name">Λογαριασμοί Courier</field>
        <field name="res_model">courier.account</field>
        <field name="view_mode">list,form</field>
    </record>
</odoo>
```

- [ ] **Step 8: Create `courier_vouchers/views/courier_voucher_views.xml`**

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="courier_voucher_view_list" model="ir.ui.view">
        <field name="name">courier.voucher.list</field>
        <field name="model">courier.voucher</field>
        <field name="arch" type="xml">
            <list decoration-muted="state == 'cancelled'" decoration-success="state == 'delivered'"
                  decoration-danger="state == 'returned'">
                <field name="pickup_date"/>
                <field name="name"/>
                <field name="recipient_name"/>
                <field name="city"/>
                <field name="reference"/>
                <field name="cod_amount" sum="Σύνολο"/>
                <field name="account_id"/>
                <field name="state" widget="badge"/>
                <field name="tracking_status" optional="hide"/>
            </list>
        </field>
    </record>

    <record id="courier_voucher_view_form" model="ir.ui.view">
        <field name="name">courier.voucher.form</field>
        <field name="model">courier.voucher</field>
        <field name="arch" type="xml">
            <form>
                <header>
                    <button name="action_send" type="object" string="Αποστολή στον Courier"
                            class="oe_highlight" invisible="state != 'draft'"/>
                    <button name="action_print" type="object" string="Επανεκτύπωση"
                            invisible="state not in ('created', 'printed')"/>
                    <button name="action_cancel" type="object" string="Ακύρωση"
                            invisible="state not in ('draft', 'created', 'printed')"
                            confirm="Ακύρωση του voucher στον courier;"/>
                    <button name="action_refresh_status" type="object" string="Ενημέρωση Κατάστασης"
                            invisible="state != 'manifested'"/>
                    <field name="state" widget="statusbar"
                           statusbar_visible="draft,printed,manifested,delivered"/>
                </header>
                <sheet>
                    <div class="oe_title">
                        <h1><field name="name" placeholder="Πρόχειρο"/></h1>
                    </div>
                    <group>
                        <group string="Παραλήπτης">
                            <field name="partner_id" readonly="state != 'draft'"/>
                            <field name="recipient_name" readonly="state != 'draft'"/>
                            <field name="recipient_company" readonly="state != 'draft'"/>
                            <field name="street" readonly="state != 'draft'"/>
                            <field name="street_number" readonly="state != 'draft'"/>
                            <field name="zip" readonly="state != 'draft'"/>
                            <field name="city" readonly="state != 'draft'"/>
                            <field name="mobile" readonly="state != 'draft'"/>
                            <field name="phone" readonly="state != 'draft'"/>
                            <field name="email" readonly="state != 'draft'"/>
                        </group>
                        <group string="Αποστολή">
                            <field name="account_id" readonly="state != 'draft'"/>
                            <field name="pickup_date" readonly="state != 'draft'"/>
                            <field name="weight" readonly="state != 'draft'"/>
                            <field name="item_quantity" readonly="state != 'draft'"/>
                            <field name="cod_amount" readonly="state != 'draft'"/>
                            <field name="currency_id" invisible="1"/>
                            <field name="reference" readonly="state != 'draft'"/>
                            <field name="notes" readonly="state != 'draft'"/>
                            <field name="picking_id" readonly="1" invisible="not picking_id"/>
                            <field name="sale_order_id" invisible="not sale_order_id"/>
                            <field name="label_attachment_id" invisible="not label_attachment_id"/>
                            <field name="pickup_list_ref" invisible="not pickup_list_ref"/>
                            <field name="tracking_status" invisible="not tracking_status"/>
                            <field name="tracking_url" widget="url" invisible="not tracking_url"/>
                        </group>
                    </group>
                </sheet>
                <chatter/>
            </form>
        </field>
    </record>

    <record id="courier_voucher_view_search" model="ir.ui.view">
        <field name="name">courier.voucher.search</field>
        <field name="model">courier.voucher</field>
        <field name="arch" type="xml">
            <search>
                <field name="name"/>
                <field name="recipient_name"/>
                <field name="reference"/>
                <filter name="today" string="Σήμερα"
                        domain="[('pickup_date', '=', context_today().strftime('%Y-%m-%d'))]"/>
                <filter name="open" string="Σε Εξέλιξη"
                        domain="[('state', 'in', ('created', 'printed', 'manifested'))]"/>
                <filter name="cod" string="Με Αντικαταβολή" domain="[('cod_amount', '>', 0)]"/>
                <group>
                    <filter name="group_state" string="Κατάσταση" context="{'group_by': 'state'}"/>
                    <filter name="group_date" string="Ημ. Παραλαβής" context="{'group_by': 'pickup_date:day'}"/>
                </group>
            </search>
        </field>
    </record>

    <record id="action_courier_voucher" model="ir.actions.act_window">
        <field name="name">Vouchers</field>
        <field name="res_model">courier.voucher</field>
        <field name="view_mode">list,form</field>
        <field name="search_view_id" ref="courier_voucher_view_search"/>
    </record>
</odoo>
```

- [ ] **Step 9: Create `courier_vouchers/views/courier_menus.xml`**

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <menuitem id="menu_courier_root" name="Αποστολές" parent="stock.menu_stock_root" sequence="5"/>
    <menuitem id="menu_courier_voucher" name="Vouchers" parent="menu_courier_root"
              action="action_courier_voucher" sequence="1"/>
    <menuitem id="menu_courier_account" name="Λογαριασμοί Courier" parent="stock.menu_stock_config_settings"
              action="action_courier_account" sequence="50" groups="stock.group_stock_manager"/>
</odoo>
```

- [ ] **Step 9b: Create `courier_vouchers/data/ir_cron.xml`** (tracking every 3 hours)

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="cron_courier_track" model="ir.cron">
        <field name="name">Courier: ενημέρωση κατάστασης vouchers</field>
        <field name="model_id" ref="model_courier_voucher"/>
        <field name="state">code</field>
        <field name="code">model._cron_track()</field>
        <field name="interval_number">3</field>
        <field name="interval_type">hours</field>
        <field name="active" eval="True"/>
    </record>
</odoo>
```

- [ ] **Step 10: Verify locally**

Run (in the scratchpad, not the repo):
```bash
cd /c/Users/User/Desktop/Odoo19/addons && python -m py_compile courier_vouchers/__manifest__.py courier_vouchers/models/*.py && python -c "import glob,xml.dom.minidom as m;[m.parse(f) for f in glob.glob('courier_vouchers/**/*.xml',recursive=True)];print('xml ok')"
```
Expected: no output from py_compile, then `xml ok`.

- [ ] **Step 11: Hand over for install; verify in the browser**

User uploads `courier_vouchers` and installs with `-i courier_vouchers`. Then Claude, on `test`:
Inventory → Αποστολές → Vouchers opens an empty list; Inventory → Ρυθμίσεις → Λογαριασμοί Courier opens. (The «Courier» selection is still empty — expected until Task 4.)

---

### Task 2: Delivery order integration

**Files:**
- Create: `courier_vouchers/models/stock_picking.py`, `courier_vouchers/views/stock_picking_views.xml`
- Modify: `courier_vouchers/models/__init__.py`, `courier_vouchers/__manifest__.py` (data list), `courier_vouchers/models/courier_voucher.py` (`write` hook)

**Interfaces:**
- Consumes: `courier.voucher` from Task 1 (`picking_id`, `state`, `name`, `_onchange_partner_id`).
- Produces: `stock.picking.courier_voucher_ids`, `courier_voucher_count`, `action_courier_new_voucher()`, `action_courier_vouchers()`; `courier.voucher._prefill_from_picking()` → dict of default values (used by Task 3 for COD).

- [ ] **Step 1: Create `courier_vouchers/models/stock_picking.py`**

```python
# -*- coding: utf-8 -*-
from odoo import fields, models


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    courier_voucher_ids = fields.One2many('courier.voucher', 'picking_id', string='Vouchers')
    courier_voucher_count = fields.Integer(compute='_compute_courier_voucher_count')

    def _compute_courier_voucher_count(self):
        for picking in self:
            picking.courier_voucher_count = len(picking.courier_voucher_ids)

    def _courier_voucher_defaults(self):
        """Default values of a new voucher for this delivery. Extended by
        sale_order.py for cash on delivery."""
        self.ensure_one()
        return {
            'default_picking_id': self.id,
            'default_partner_id': self.partner_id.id,
            'default_weight': max(self.weight or 0.0, 0.5),
            'default_reference': self.sale_id.name or self.name,
        }

    def action_courier_new_voucher(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'courier.voucher',
            'view_mode': 'form',
            'target': 'current',
            'context': self._courier_voucher_defaults(),
        }

    def action_courier_vouchers(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('courier_vouchers.action_courier_voucher')
        action['domain'] = [('picking_id', '=', self.id)]
        action['context'] = self._courier_voucher_defaults()
        return action
```

`_onchange_partner_id` fills the address when the form opens with `default_partner_id` — Odoo runs onchanges on defaults of a new record.

- [ ] **Step 2: Add the tracking-ref hook to `courier_voucher.py`**

Add inside `CourierVoucher`:

```python
    def write(self, vals):
        res = super().write(vals)
        if 'state' in vals:
            for voucher in self.filtered('picking_id'):
                picking = voucher.picking_id
                if voucher.state in ('created', 'printed', 'manifested'):
                    picking.carrier_tracking_ref = voucher.name
                elif voucher.state == 'cancelled' and picking.carrier_tracking_ref == voucher.name:
                    picking.carrier_tracking_ref = False
        return res
```

- [ ] **Step 3: Create `courier_vouchers/views/stock_picking_views.xml`**

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="view_picking_form_courier" model="ir.ui.view">
        <field name="name">stock.picking.form.courier</field>
        <field name="model">stock.picking</field>
        <field name="inherit_id" ref="stock.view_picking_form"/>
        <field name="arch" type="xml">
            <xpath expr="//header" position="inside">
                <button name="action_courier_new_voucher" type="object" string="Δημιουργία Voucher"
                        invisible="picking_type_code != 'outgoing' or state == 'cancel'"/>
            </xpath>
            <xpath expr="//div[@name='button_box']" position="inside">
                <button name="action_courier_vouchers" type="object" class="oe_stat_button"
                        icon="fa-truck" invisible="not courier_voucher_count">
                    <field name="courier_voucher_count" widget="statinfo" string="Vouchers"/>
                </button>
            </xpath>
        </field>
    </record>
</odoo>
```

- [ ] **Step 4: Register the files**

`models/__init__.py` gets `from . import stock_picking`; manifest `data` gets `'views/stock_picking_views.xml'` after `courier_voucher_views.xml`.

- [ ] **Step 5: Verify locally** — same command as Task 1 Step 10.

- [ ] **Step 6: Hand over for upgrade; verify in the browser**

User uploads, `docker restart odoo19`, upgrade `-u courier_vouchers`. Claude, on `test`: open an outgoing delivery → «Δημιουργία Voucher» opens a draft voucher with recipient, address split into street/number, reference = sale order, weight ≥ 0.5. Discard it (no courier yet).

---

### Task 3: Cash on delivery flag on the sale order

**Files:**
- Create: `courier_vouchers/models/sale_order.py`, `courier_vouchers/views/sale_order_views.xml`
- Modify: `courier_vouchers/models/__init__.py`, `courier_vouchers/__manifest__.py`, `courier_vouchers/models/stock_picking.py` (`_courier_voucher_defaults`)

**Interfaces:**
- Consumes: `stock.picking._courier_voucher_defaults()` from Task 2.
- Produces: `sale.order.courier_cod` (Boolean), ticked by hand.

- [ ] **Step 1: Create `courier_vouchers/models/sale_order.py`**

```python
# -*- coding: utf-8 -*-
from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    courier_cod = fields.Boolean(
        string='Αντικαταβολή', copy=False,
        help='Η παραγγελία πληρώνεται στον courier. Το voucher παίρνει '
             'αυτόματα το σύνολό της ως ποσό αντικαταβολής.')
```

- [ ] **Step 2: Extend `_courier_voucher_defaults` in `stock_picking.py`**

Replace its `return {...}` with:

```python
        defaults = {
            'default_picking_id': self.id,
            'default_partner_id': self.partner_id.id,
            'default_weight': max(self.weight or 0.0, 0.5),
            'default_reference': self.sale_id.name or self.name,
        }
        if self.sale_id.courier_cod:
            defaults['default_cod_amount'] = self.sale_id.amount_total
        return defaults
```

- [ ] **Step 3: Create `courier_vouchers/views/sale_order_views.xml`**

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="view_order_form_courier" model="ir.ui.view">
        <field name="name">sale.order.form.courier</field>
        <field name="model">sale.order</field>
        <field name="inherit_id" ref="sale.view_order_form"/>
        <field name="arch" type="xml">
            <xpath expr="//field[@name='payment_term_id']" position="after">
                <field name="courier_cod"/>
            </xpath>
        </field>
    </record>
</odoo>
```

- [ ] **Step 4: Register** — `from . import sale_order` in `models/__init__.py`; `'views/sale_order_views.xml'` in the manifest.

- [ ] **Step 5: Verify locally** — same command as Task 1 Step 10.

- [ ] **Step 6: Hand over; verify in the browser**

Restart + upgrade. Claude, on `test`: sale order shows «Αντικαταβολή» under the payment terms. Tick it on a test order with a delivery → «Δημιουργία Voucher» → `cod_amount` = order total. Untick afterwards; discard the draft voucher.

---

### Task 4: ACS inside `courier_vouchers` — credentials and the ACS client

**Files:**
- Create: `courier_vouchers/models/courier_acs.py`, `courier_vouchers/views/courier_acs_views.xml`
- Modify: `courier_vouchers/models/__init__.py`, `courier_vouchers/__manifest__.py` (data list + version 1.1 + Changelog line)

**Interfaces:**
- Consumes: `courier.account` dispatch from Task 1 (`_acs_<method>` names), `courier.voucher` fields.
- Produces: `courier.account._acs_call(alias, params) -> dict` (the `ACSOutputResponce` object), `_acs_create(voucher) -> str`, `_acs_print(vouchers) -> bytes`, `_acs_cancel(voucher)`, `_acs_close_day(date) -> (str, bytes)`, `_acs_track(voucher) -> (state|False, str)`, `_acs_tracking_url(number) -> str`.

- [ ] **Step 1: Register the ACS files in the addon**

`courier_vouchers/models/__init__.py` gets `from . import courier_acs` (last line). In `__manifest__.py`: append `'views/courier_acs_views.xml'` to `data` (after `courier_account_views.xml`), set `'version': '1.1'`, and add above the 1.0 line of the Changelog:

```python
        '1.1 — ACS: create, print (A4), delete voucher, daily pickup list,\n'
        'tracking summary (ACS Web Services, ACSAutoRest).\n'
        '\n'
```

- [ ] **Step 2: Create `courier_vouchers/models/courier_acs.py`**

```python
# -*- coding: utf-8 -*-
"""ACS Web Services — spec: Courier API/ACS/english-acs-web-services-2025.md.

One URL, always POST JSON {"ACSAlias", "ACSInputParameters"}, header
ACSApiKey. HTTP 200 even on business errors: ACSExecution_HasError and the
per-row Error_Message carry them. There is no test server — a voucher can be
deleted only until it is in a pickup list.
"""
import base64
import logging

import requests

from odoo import _, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

ACS_URL = 'https://webservices.acscourier.net/ACSRestServices/api/ACSAutoRest'
ACS_TIMEOUT = 60
# Tracking summary shipment_status → voucher state.
ACS_DELIVERED = {4}
ACS_RETURNED = {6, 7}


class CourierAccount(models.Model):
    _inherit = 'courier.account'

    courier = fields.Selection(selection_add=[('acs', 'ACS')], ondelete={'acs': 'cascade'})
    acs_api_key = fields.Char(string='ACS API Key', groups='base.group_system')
    acs_company_id = fields.Char(string='Company ID', groups='base.group_system')
    acs_company_password = fields.Char(string='Company Password', groups='base.group_system')
    acs_user_id = fields.Char(string='User ID', groups='base.group_system')
    acs_user_password = fields.Char(string='User Password', groups='base.group_system')
    acs_billing_code = fields.Char(string='Κωδικός Χρέωσης (Billing Code)', groups='base.group_system')

    # ── transport ────────────────────────────────────────────────────────────
    def _acs_call(self, alias, params):
        """POST one ACS alias; return ACSOutputResponce. Credentials are
        added here and never logged."""
        self.ensure_one()
        acc = self.sudo()
        if not (acc.acs_api_key and acc.acs_company_id and acc.acs_user_id):
            raise UserError(_('Συμπληρώστε τα στοιχεία σύνδεσης ACS στον λογαριασμό «%s».', self.name))
        body = {'ACSAlias': alias, 'ACSInputParameters': {
            'Company_ID': acc.acs_company_id,
            'Company_Password': acc.acs_company_password,
            'User_ID': acc.acs_user_id,
            'User_Password': acc.acs_user_password,
            'Language': None,
            **params,
        }}
        try:
            resp = requests.post(ACS_URL, json=body, timeout=ACS_TIMEOUT,
                                 headers={'ACSApiKey': acc.acs_api_key})
        except requests.RequestException as e:
            raise UserError(_('Η ACS δεν απαντά: %s', e)) from e
        if resp.status_code == 403:
            raise UserError(_('Η ACS απέρριψε το API key (403).'))
        if resp.status_code == 406:
            raise UserError(_('Πάρα πολλές κλήσεις προς την ACS — ξαναδοκιμάστε σε λίγο.'))
        if resp.status_code != 200:
            raise UserError(_('Η ACS απάντησε HTTP %s.', resp.status_code))
        data = resp.json()
        _logger.info('ACS %s → HasError=%s', alias, data.get('ACSExecution_HasError'))
        if data.get('ACSExecution_HasError'):
            raise UserError(_('ACS (%(alias)s): %(msg)s', alias=alias,
                              msg=data.get('ACSExecutionErrorMessage') or '?'))
        # The spec spells it both ways; the demo responses use «Responce».
        return data.get('ACSOutputResponce') or data.get('ACSOutputResponse') or {}

    @staticmethod
    def _acs_value(out):
        """First ACSValueOutput row, raising its Error_Message if any."""
        rows = out.get('ACSValueOutput') or [{}]
        row = rows[0] or {}
        err = row.get('Error_Message') or row.get('error_message')
        if err:
            raise UserError(_('ACS: %s', err))
        return row

    @staticmethod
    def _acs_table(out):
        return (out.get('ACSTableOutput') or {}).get('Table_Data') or []

    @staticmethod
    def _acs_pdf(out):
        """The print aliases return the PDF in ACSObjectOutput as
        {voucher: bytes}. .NET serialises byte[] as base64; accept a list of
        ints too. Verified on the first real print (plan Task 5)."""
        obj = out.get('ACSObjectOutput')
        values = []
        if isinstance(obj, dict):
            values = list(obj.values())
        elif isinstance(obj, list):
            for item in obj:
                values.extend(item.values() if isinstance(item, dict) else [item])
        elif obj:
            values = [obj]
        for value in values:
            if isinstance(value, str) and value.startswith('JVBER'):
                return base64.b64decode(value)
            if isinstance(value, list) and value and isinstance(value[0], int):
                return bytes(value)
        raise UserError(_('Η ACS δεν επέστρεψε PDF (κλειδιά: %s).', ', '.join(out.keys())))

    # ── interface ────────────────────────────────────────────────────────────
    def _acs_create(self, voucher):
        acc = self.sudo()
        cod = voucher.cod_amount > 0
        out = self._acs_call('ACS_Create_Voucher', {
            'Pickup_Date': voucher.pickup_date.isoformat(),
            'Sender': self.sender_name,
            'Recipient_Name': voucher.recipient_name,
            'Recipient_Address': voucher.street,
            'Recipient_Address_Number': voucher.street_number or None,
            'Recipient_Zipcode': (voucher.zip or '').replace(' ', ''),
            'Recipient_Region': voucher.city,
            'Recipient_Phone': voucher.phone or None,
            'Recipient_Cell_Phone': voucher.mobile,
            'Recipient_Floor': None,
            'Recipient_Company_Name': voucher.recipient_company or None,
            'Recipient_Country': voucher.country_code or 'GR',
            'Acs_Station_Destination': None,
            'Acs_Station_Branch_Destination': None,
            'Billing_Code': acc.acs_billing_code,
            'Charge_Type': 2 if self.default_charge_type == 'sender' else 4,
            'Cost_Center_Code': None,
            'Item_Quantity': voucher.item_quantity,
            'Weight': round(voucher.weight, 2),
            'Dimension_X_In_Cm': None,
            'Dimension_Y_in_Cm': None,
            'Dimension_Z_in_Cm': None,
            'Cod_Ammount': round(voucher.cod_amount, 2) if cod else None,
            'Cod_Payment_Way': 0 if cod else None,
            'Acs_Delivery_Products': 'COD' if cod else None,
            'Insurance_Ammount': None,
            'Delivery_Notes': voucher.notes or None,
            'Appointment_Until_Time': None,
            'Recipient_Email': voucher.email or None,
            'Reference_Key1': voucher.reference or None,
            'Reference_Key2': None,
            'With_Return_Voucher': None,
            'Content_Type_ID': None,
        })
        number = (self._acs_value(out).get('Voucher_No') or '').strip()
        if not number:
            raise UserError(_('Η ACS δεν επέστρεψε αριθμό voucher.'))
        return number

    def _acs_print(self, vouchers):
        out = self._acs_call('ACS_Print_Voucher', {
            'Voucher_No': ','.join(vouchers.mapped('name')),
            'Print_Type': 2,       # A4 laser, 3 labels per page
            'Start_Position': 1,
        })
        return self._acs_pdf(out)

    def _acs_cancel(self, voucher):
        out = self._acs_call('ACS_Delete_Voucher', {'Voucher_No': voucher.name})
        self._acs_value(out)

    def _acs_close_day(self, date):
        out = self._acs_call('ACS_Issue_Pickup_List', {
            'Pickup_Date': date.isoformat(), 'MyData': None})
        row = (out.get('ACSValueOutput') or [{}])[0] or {}
        if row.get('Unprinted_Found'):
            unprinted = ', '.join(r.get('Unprinted_Vouchers', '') for r in self._acs_table(out))
            raise UserError(_('Η ACS βρήκε ατύπωτα vouchers: %s. Τυπώστε ή ακυρώστε τα '
                              'και ξαναδοκιμάστε.', unprinted))
        list_no = self._acs_value(out).get('PickupList_No')
        if not list_no:
            raise UserError(_('Η ACS δεν επέστρεψε αριθμό λίστας παραλαβής.'))
        pdf_out = self._acs_call('ACS_Print_Pickup_List', {
            'Mass_Number': list_no, 'Pickup_Date': date.isoformat()})
        return str(list_no), self._acs_pdf(pdf_out)

    def _acs_track(self, voucher):
        out = self._acs_call('ACS_Trackingsummary', {'Voucher_No': voucher.name})
        rows = self._acs_table(out)
        if not rows:
            return False, voucher.tracking_status or ''
        row = rows[0]
        status = row.get('shipment_status')
        text = row.get('delivery_info') or ''
        if row.get('returned_flag') == 1 or status in ACS_RETURNED:
            return 'returned', text
        if status in ACS_DELIVERED:
            return 'delivered', text
        return False, text

    def _acs_tracking_url(self, number):
        return f'https://www.acscourier.net/el/track-and-trace?p_p_id=ACSCustomersAreaTrackTrace&generalCode={number}'
```

- [ ] **Step 3: Create `courier_vouchers/views/courier_acs_views.xml`**

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="courier_account_view_form_acs" model="ir.ui.view">
        <field name="name">courier.account.form.acs</field>
        <field name="model">courier.account</field>
        <field name="inherit_id" ref="courier_vouchers.courier_account_view_form"/>
        <field name="arch" type="xml">
            <xpath expr="//page[@name='credentials']" position="inside">
                <group invisible="courier != 'acs'" groups="base.group_system">
                    <field name="acs_api_key" password="True"/>
                    <field name="acs_company_id"/>
                    <field name="acs_company_password" password="True"/>
                    <field name="acs_user_id"/>
                    <field name="acs_user_password" password="True"/>
                    <field name="acs_billing_code"/>
                </group>
            </xpath>
        </field>
    </record>
</odoo>
```

- [ ] **Step 4: Verify locally**

```bash
cd /c/Users/User/Desktop/Odoo19/addons && python -m py_compile courier_vouchers/__manifest__.py courier_vouchers/models/*.py && python -c "import glob,xml.dom.minidom as m;[m.parse(f) for f in glob.glob('courier_vouchers/**/*.xml',recursive=True)];print('xml ok')"
```
Expected: `xml ok`.

- [ ] **Step 5: Hand over for install**

User uploads `courier_vouchers`, `docker restart odoo19`, upgrades `-u courier_vouchers`. Then the user creates the account «ACS» (Courier = ACS, sender name) and types the six credentials. Claude only checks the form shows the «Σύνδεση» tab with the password fields masked — never reads their values.

---

### Task 5: Real-account test round (browser, `test`)

**Files:** none unless a bug is found (then: fix, bump `courier_vouchers` to `1.2` with a Changelog line, redeploy).

Never press «Λίστα Παραλαβής Ημέρας» in this task.

- [ ] **Step 1: Standalone voucher** — Vouchers → New → recipient = the business's own contact, weight 0.5 → «Αποστολή στον Courier». Expect: number filled, state Τυπώθηκε, the A4 PDF opens in a new tab with the label. If the PDF step fails with «δεν επέστρεψε PDF (κλειδιά: …)», the error names the response keys — fix `_acs_pdf` from them.
- [ ] **Step 2: Cancel it** — «Ακύρωση» → state Ακυρώθηκε, chatter note. Expect no ACS error.
- [ ] **Step 3: From a delivery** — outgoing delivery → «Δημιουργία Voucher» → send. Expect `carrier_tracking_ref` on the delivery = the voucher number, smart button «Vouchers 1». Cancel → `carrier_tracking_ref` cleared.
- [ ] **Step 4: Cash on delivery** — tick «Αντικαταβολή» on a test sale order, voucher from its delivery → the label shows the COD amount. Cancel; untick.
- [ ] **Step 5: Validation errors** — a draft with an empty mobile → our «Λείπουν στοιχεία» message; a postcode `00000` → ACS's own message; the voucher stays draft in both.
- [ ] **Step 6: Wrong API key** — ask the user to change the key; expect «απέρριψε το API key (403)». User restores it.
- [ ] **Step 7: Confirm nothing is left at ACS** — every voucher from this round is Ακυρώθηκε.
- [ ] **Step 8: Report** — results table to the user; pickup list and tracking stay untested until the first real shipment.

---

## End of day

When the user asks: one commit of `courier_vouchers` and `docs/courier-acs-*.md`, message ending with the Co-Authored-By line; new bundle of unpushed commits. Update `PROJECT_STATUS.md` with a line for the courier work.
