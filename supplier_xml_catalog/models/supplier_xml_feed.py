# -*- coding: utf-8 -*-
import base64
import html
import io
import logging
import math
import time
from collections import OrderedDict

import requests

from lxml import etree
from PIL import Image, ImageOps

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools import float_compare

_logger = logging.getLogger(__name__)

# Per batch, well inside limit_time_cpu (60s) and limit_time_real (240s).
BATCH_CPU = 30
BATCH_WALL = 150
STAT_KEYS = ('created', 'updated', 'unchanged', 'out_of_stock', 'conflicts',
             'errors', 'images_downloaded')
IMAGE_MAX_PX = 1024
IMAGE_CACHE_SIZE = 100  # recent URLs; a small JPEG each, so a few MB at most


def _shrink_to_jpeg(data):
    """Downloaded image bytes → base64 JPEG of at most IMAGE_MAX_PX, or False
    when the bytes are not an image (an HTML error page, say), which Odoo
    would otherwise refuse with an exception."""
    try:
        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img)
        if img.mode in ('RGBA', 'LA', 'P'):
            img = img.convert('RGBA')
            background = Image.new('RGB', img.size, (255, 255, 255))
            background.paste(img, mask=img.getchannel('A'))
            img = background
        elif img.mode != 'RGB':
            img = img.convert('RGB')
        img.thumbnail((IMAGE_MAX_PX, IMAGE_MAX_PX))
        out = io.BytesIO()
        img.save(out, 'JPEG', quality=85)
        return base64.b64encode(out.getvalue())
    except Exception:
        return False


class SupplierXmlFeed(models.Model):
    _name = 'supplier.xml.feed'
    _description = 'Supplier XML Feed'
    _order = 'name'

    name = fields.Char(string='Όνομα Feed / Προμηθευτή', required=True)
    active = fields.Boolean(default=True)
    auto_sync = fields.Boolean(string='Αυτόματος Συγχρονισμός (Cron)', default=True)
    sync_requested = fields.Boolean(string='Σε ουρά συγχρονισμού', copy=False, readonly=True)
    sync_position = fields.Integer(string='Πρόοδος (προϊόντα)', copy=False, readonly=True)
    sync_run_start = fields.Datetime(copy=False, readonly=True)
    sync_file = fields.Binary(copy=False, attachment=True)
    sync_stats = fields.Json(copy=False)
    partner_id = fields.Many2one(
        'res.partner',
        string='Προμηθευτής (Επαφή)',
        help='Αν οριστεί, κάθε προϊόν του feed παίρνει γραμμή προμηθευτή '
             '(κωδικός και κόστος), ώστε να ξέρετε από πού να το παραγγείλετε.',
    )

    # Source
    feed_url = fields.Char(string='URL Feed')
    xml_file = fields.Binary(string='Αρχείο XML (Upload)')
    xml_filename = fields.Char(string='Όνομα Αρχείου XML')

    state = fields.Selection([
        ('draft', 'Πρόχειρο'),
        ('running', 'Σε εξέλιξη'),
        ('ready', 'Έτοιμο'),
        ('error', 'Σφάλμα'),
    ], string='Κατάσταση', default='draft')

    last_sync = fields.Datetime(string='Τελευταίος Συγχρονισμός', readonly=True)
    last_sync_message = fields.Text(string='Μήνυμα Συγχρονισμού', readonly=True)

    product_count = fields.Integer(
        string='Προϊόντα Feed',
        compute='_compute_product_count',
    )

    # 1. Pricing Policy
    pricing_type = fields.Selection([
        ('markup_pct', 'Ποσοστό Κέρδους (%)'),
        ('markup_fixed', 'Σταθερό Περιθώριο (€)'),
        ('both', 'Ποσοστό (%) + Σταθερό (€)'),
        ('as_is', 'Όπως είναι στο Feed (Χωρίς προσαύξηση)'),
    ], string='Πολιτική Τιμολόγησης', default='markup_pct', required=True)

    markup_percent = fields.Float(
        string='Ποσοστό Προσαύξησης (%)',
        default=20.0,
        help='Προστίθεται επί του κόστους του προμηθευτή.',
    )
    markup_fixed = fields.Float(
        string='Σταθερή Προσαύξηση (€)',
        default=0.0,
        help='Προστίθεται στο τελικό ποσό (π.χ. έξοδα διαχείρισης).',
    )
    price_round = fields.Selection([
        ('none', 'Καμία (Ακριβές 2 δεκαδικά)'),
        ('point_99', 'Σε .99 € (π.χ. 19.99)'),
        ('point_90', 'Σε .90 € (π.χ. 19.90)'),
        ('integer', 'Σε ακέραιο ευρώ (π.χ. 20.00)'),
    ], string='Στρογγυλοποίηση Τιμής', default='point_99')

    vat_included_in_feed = fields.Boolean(
        string='Η τιμή Feed περιλαμβάνει ΦΠΑ',
        default=True,
        help='Αν είναι ανενεργό, υπολογίζεται και προστίθεται ο συντελεστής ΦΠΑ παρακάτω.',
    )
    vat_rate = fields.Float(
        string='Συντελεστής ΦΠΑ (%)',
        default=24.0,
        help='Χρησιμοποιείται αν η τιμή του feed είναι καθαρή χονδρικής.',
    )

    # 2. Availability Policy
    stock_mode = fields.Selection([
        ('quantity', 'Αριθμητικό Απόθεμα'),
        ('status', 'Λεκτικό Διαθεσιμότητας / Flag'),
        ('always', 'Πάντα Διαθέσιμο'),
    ], string='Έλεγχος Διαθεσιμότητας', default='quantity', required=True)

    min_stock_threshold = fields.Float(
        string='Ελάχιστο Όριο Αποθέματος',
        default=1.0,
        help='Απόθεμα ίσο ή μεγαλύτερο θεωρείται διαθέσιμο.',
    )
    in_stock_text = fields.Char(
        string='Κείμενο "Σε Απόθεμα"',
        default='Διαθέσιμο από προμηθευτή (1–3 ημέρες)',
        required=True,
    )
    out_of_stock_action = fields.Selection([
        ('unpublish', 'Απόσυρση (Unpublish) από το eshop'),
        ('keep_note', 'Παραμονή δημοσιευμένου με ένδειξη έλλειψης'),
    ], string='Ενέργεια αν εξαντληθεί', default='unpublish', required=True)

    out_of_stock_text = fields.Char(
        string='Κείμενο "Εξαντλημένο"',
        default='Εξαντλημένο στον προμηθευτή',
        required=True,
    )

    # 3. Shipping Details
    shipping_lead_time = fields.Char(
        string='Χρόνος Παράδοσης',
        default='1-3 εργάσιμες ημέρες',
    )
    shipping_note = fields.Char(
        string='Σημείωση Μεταφορικών',
        default='Αποστολή με Courier',
    )

    # 4. Brand & Category Mapping
    auto_create_categories = fields.Boolean(
        string='Αυτόματη Κατηγοριοποίηση Eshop',
        default=False,
        help='Αντιστοιχίζει ή δημιουργεί δημόσιες κατηγορίες eshop από το XML. '
             'Εφαρμόζεται μόνο σε προϊόντα χωρίς κατηγορία eshop, ώστε να μη '
             'χάνεται η χειροκίνητη κατηγοριοποίηση. Προσοχή: δημιουργεί '
             'όσες κατηγορίες του προμηθευτή δεν υπάρχουν ήδη.',
    )
    auto_create_brands = fields.Boolean(
        string='Αυτόματη Σύνδεση Μάρκας (Brand)',
        default=True,
        help='Αντιστοιχίζει ή δημιουργεί μάρκες (εφόσον είναι εγκατεστημένο το website_sale_brand).',
    )

    max_images_per_sync = fields.Integer(
        string='Μέγιστες Νέες Εικόνες ανά Συγχρονισμό',
        default=50,
        help='Όριο λήψης νέων εικόνων ανά εκτέλεση (0 = χωρίς όριο) για αποφυγή timeouts.',
    )

    # 5. XML Tag Mapping
    tag_product = fields.Char(string='Tag Προϊόντος', default='product', required=True)
    tag_sku = fields.Char(string='Tag SKU/ID', default='id', required=True)
    tag_barcode = fields.Char(string='Tag Barcode/EAN', default='barcode')
    tag_mpn = fields.Char(string='Tag MPN', default='mpn')
    tag_name = fields.Char(string='Tag Τίτλου/Ονόματος', default='name', required=True)
    tag_price = fields.Char(string='Tag Τιμής / Κόστους', default='price', required=True)
    tag_cost = fields.Char(string='Tag Κόστους (αν διαφέρει)', default='')
    tag_quantity = fields.Char(string='Tag Αποθέματος', default='quantity')
    tag_availability = fields.Char(string='Tag Κατάστασης', default='availability')
    tag_category = fields.Char(string='Tag Κατηγορίας', default='category')
    tag_brand = fields.Char(string='Tag Μάρκας', default='brand')
    tag_image = fields.Char(string='Tag Εικόνας (URL)', default='image')
    tag_description = fields.Char(string='Tag Περιγραφής', default='description')

    def _compute_product_count(self):
        for feed in self:
            feed.product_count = self.env['product.template'].search_count([
                ('supplier_feed_id', '=', feed.id)
            ])

    def action_view_products(self):
        self.ensure_one()
        return {
            'name': _('Προϊόντα: %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'product.template',
            'view_mode': 'list,form',
            'domain': [('supplier_feed_id', '=', self.id)],
            'context': {
                'default_supplier_feed_id': self.id,
                'default_is_supplier_feed_product': True,
                'default_is_storable': False,
                'default_type': 'consu',
            },
        }

    # =========================================================================
    # Calculation Helpers
    # =========================================================================
    def _calculate_retail_price(self, raw_cost):
        self.ensure_one()
        try:
            cleaned = str(raw_cost or 0.0).replace(',', '.').strip()
            price = float(cleaned)
        except (ValueError, TypeError):
            return 0.0

        if price <= 0.0:
            return 0.0

        if not self.vat_included_in_feed and self.vat_rate > 0:
            price *= (1.0 + self.vat_rate / 100.0)

        if self.pricing_type in ('markup_pct', 'both'):
            price *= (1.0 + (self.markup_percent or 0.0) / 100.0)
        if self.pricing_type in ('markup_fixed', 'both'):
            price += (self.markup_fixed or 0.0)

        if self.price_round == 'point_99':
            price = math.floor(price) + 0.99
        elif self.price_round == 'point_90':
            price = math.floor(price) + 0.90
        elif self.price_round == 'integer':
            price = round(price)

        return max(round(price, 2), 0.0)

    def _evaluate_stock(self, qty_raw, avail_raw):
        self.ensure_one()
        if self.stock_mode == 'always':
            return True

        if self.stock_mode == 'quantity':
            try:
                cleaned = str(qty_raw or '0').replace(',', '.').strip()
                qty = float(cleaned)
                return qty >= self.min_stock_threshold
            except (ValueError, TypeError):
                pass

        status = str(avail_raw or qty_raw or '').strip().lower()
        positive_keywords = {
            '1', 'y', 'yes', 'true', 'in stock', 'διαθεσιμο',
            'διαθέσιμο', 'κατοπιν παραγγελιας', 'κατόπιν παραγγελίας', 'stock'
        }
        return status in positive_keywords

    def _download_image_b64(self, url, cache):
        """The image as a small JPEG, base64, or False.

        Odoo turns every image_1920 into four more sizes and recompresses
        each, ~2.2s CPU for a supplier's 1 MB PNG (profiled 2026-11-09).
        Shrinking to 1024px JPEG first cuts that several times; the eshop
        never shows anything larger. Suppliers reuse one picture for many
        products (Teleparts: 4,711 images for 8,737 products, often in a
        row), so recent URLs are kept in `cache` and fetched once."""
        if not url or not url.startswith(('http://', 'https://')):
            return False
        if url in cache:
            cache.move_to_end(url)
            return cache[url]
        result = False
        try:
            resp = requests.get(url, timeout=4, headers={'User-Agent': 'Mozilla/5.0'})
            if resp.status_code == 200 and resp.content:
                result = _shrink_to_jpeg(resp.content)
        except Exception as e:
            _logger.warning("Supplier feed [%s]: Image download failed from %s: %s", self.name, url, e)
        cache[url] = result
        if len(cache) > IMAGE_CACHE_SIZE:
            cache.popitem(last=False)
        return result

    def _extract_item_dict(self, elem):
        def get_tag_text(tag):
            if not tag:
                return ''
            tag_clean = tag.strip().lower()
            for child in elem:
                if not isinstance(child.tag, str):  # comment / PI
                    continue
                ctag = child.tag.split('}')[-1].lower()
                if ctag == tag_clean:
                    return (child.text or '').strip()
            if '/' in tag:
                node = elem.find(tag)
                if node is not None:
                    return (node.text or '').strip()
            return ''

        sku = get_tag_text(self.tag_sku)
        if not sku:
            for alt in ('id', 'code', 'sku', 'product_id', 'art_no'):
                val = get_tag_text(alt)
                if val:
                    sku = val
                    break

        return {
            'sku': sku,
            'barcode': get_tag_text(self.tag_barcode),
            'mpn': get_tag_text(self.tag_mpn),
            'name': get_tag_text(self.tag_name),
            'price': get_tag_text(self.tag_price),
            'cost': get_tag_text(self.tag_cost) or get_tag_text(self.tag_price),
            'quantity': get_tag_text(self.tag_quantity),
            'availability': get_tag_text(self.tag_availability),
            'category': get_tag_text(self.tag_category),
            'brand': get_tag_text(self.tag_brand),
            'image': get_tag_text(self.tag_image),
            'description': get_tag_text(self.tag_description),
        }

    # =========================================================================
    # Synchronization Execution
    #
    # A real feed (Teleparts: 27 MB, ~8,700 products) takes far longer than
    # a worker's CPU limit (limit_time_cpu = 60s, crons included). So a sync
    # is a *run* split into time-boxed batches: the file is downloaded once
    # per run and kept in `sync_file`, each batch skips what earlier batches
    # did (`sync_position`), stops after BATCH_CPU / BATCH_WALL seconds,
    # saves its place and re-triggers the queue cron.
    # =========================================================================
    def action_sync(self):
        self.write({'sync_requested': True})
        self.env.ref('supplier_xml_catalog.ir_cron_sync_requested_feeds')._trigger()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Συγχρονισμός Feed'),
                'message': _('Ο συγχρονισμός ξεκίνησε στο παρασκήνιο και τρέχει σε δόσεις. '
                             'Η πρόοδος φαίνεται στο Ιστορικό.'),
                'type': 'info',
                'sticky': False,
            }
        }

    @api.model
    def _cron_sync_feeds(self):
        """Scheduled run: queue the auto-sync feeds, the queue cron does the work."""
        feeds = self.search([('auto_sync', '=', True), ('sync_requested', '=', False)])
        if feeds:
            feeds.write({'sync_requested': True})
            self.env.ref('supplier_xml_catalog.ir_cron_sync_requested_feeds')._trigger()

    @api.model
    def _cron_sync_requested(self):
        cpu_end = time.process_time() + BATCH_CPU
        wall_end = time.monotonic() + BATCH_WALL
        for feed in self.search([('sync_requested', '=', True)]):
            if not feed._sync_batch(cpu_end, wall_end):
                self.env.ref('supplier_xml_catalog.ir_cron_sync_requested_feeds')._trigger()
                return  # out of time: the next trigger continues from here

    def _fetch_xml_bytes(self):
        self.ensure_one()
        if self.feed_url:
            _logger.info("Supplier Feed [%s]: downloading %s", self.name, self.feed_url)
            resp = requests.get(self.feed_url, timeout=120, headers={'User-Agent': 'Mozilla/5.0'})
            resp.raise_for_status()
            return resp.content
        if self.xml_file:
            return base64.b64decode(self.xml_file)
        raise UserError(_("Παρακαλώ συμπληρώστε ένα URL feed ή μεταφορτώστε ένα αρχείο XML."))

    def _load_lookup_maps(self):
        """Everything matching needs, in a few queries instead of several per item.

        Matching is limited to this feed's own products. Barcodes and
        internal references of all other products are loaded only to avoid
        clashing with them, never to adopt those products."""
        Template = self.env['product.template'].with_context(active_test=False)
        own = Template.search([('supplier_feed_id', '=', self.id)])
        sku_map = {p.supplier_sku: p for p in own if p.supplier_sku}
        barcode_map = {p.barcode: p for p in own if p.barcode}
        variants = self.env['product.product'].with_context(active_test=False).search_read(
            [('barcode', '!=', False)], ['barcode', 'product_tmpl_id'])
        all_barcodes = {v['barcode']: v['product_tmpl_id'][0] for v in variants}
        all_codes = set(Template.search([('default_code', '!=', False)]).mapped('default_code'))
        return sku_map, barcode_map, all_barcodes, all_codes, OrderedDict()

    def _save_progress(self, position, stats, seen_ids):
        """Checkpoint: mark products seen in this run and remember the place."""
        if seen_ids:
            self.env['product.template'].browse(seen_ids).write(
                {'supplier_last_sync': self.sync_run_start})
            seen_ids.clear()
        self.write({
            'sync_position': position,
            'sync_stats': dict(stats),
            'last_sync_message': f"Σε εξέλιξη: {position} προϊόντα επεξεργάστηκαν...",
        })
        self.env.cr.commit()

    def _sync_batch(self, cpu_end, wall_end):
        """Process one time-boxed batch. Returns True when the run is over
        (finished or failed), False when it stopped for time."""
        self.ensure_one()
        try:
            if not self.sync_position:
                # start of a run: download once, keep the bytes for the batches
                data = self._fetch_xml_bytes()
                self.write({
                    'state': 'running',
                    'sync_run_start': fields.Datetime.now(),
                    'sync_file': base64.b64encode(data),
                    'sync_stats': dict.fromkeys(STAT_KEYS, 0),
                })
                self.env.cr.commit()
            else:
                data = base64.b64decode(self.sync_file)

            stats = dict.fromkeys(STAT_KEYS, 0)
            stats.update(self.sync_stats or {})
            target_tag = (self.tag_product or 'product').strip().lower()
            maps = self._load_lookup_maps()
            sale_taxes = self.env.company.account_sale_tax_id
            seen_ids = []
            start_at = self.sync_position
            index = 0

            # No entity expansion and no network access: the feed is remote,
            # untrusted input.
            context = etree.iterparse(
                io.BytesIO(data), events=('end',), resolve_entities=False, no_network=True,
            )
            for _event, elem in context:
                if not isinstance(elem.tag, str):
                    continue
                if etree.QName(elem).localname.lower() != target_tag:
                    continue
                index += 1
                try:
                    if index > start_at:
                        item_data = self._extract_item_dict(elem)
                        if item_data.get('sku'):
                            self._process_feed_item(item_data, stats, maps, sale_taxes, seen_ids)
                        else:
                            stats['errors'] += 1
                except Exception as err:
                    stats['errors'] += 1
                    _logger.warning("Feed [%s] error on item %d: %s", self.name, index, err)
                finally:
                    # free the item and the already processed siblings
                    elem.clear()
                    while elem.getprevious() is not None:
                        del elem.getparent()[0]

                if index > start_at:
                    if time.process_time() > cpu_end or time.monotonic() > wall_end:
                        self._save_progress(index, stats, seen_ids)
                        _logger.info("Supplier Feed [%s]: paused at item %d", self.name, index)
                        return False
                    if index % 50 == 0:
                        self._save_progress(index, stats, seen_ids)

            self._save_progress(index, stats, seen_ids)
            self._finish_run(index, stats)
            return True

        except Exception as e:
            self.env.cr.rollback()
            err_msg = f"Σφάλμα συγχρονισμού: {e}"
            self.write({
                'state': 'error',
                'last_sync': fields.Datetime.now(),
                'last_sync_message': err_msg,
                'sync_requested': False,
                'sync_position': 0,
                'sync_file': False,
            })
            self.env.cr.commit()
            _logger.exception("Supplier Feed [%s] sync failed: %s", self.name, e)
            return True

    def _finish_run(self, total, stats):
        # An empty feed is far more likely a supplier glitch than a
        # supplier selling nothing, so it never unpublishes the catalogue.
        dropped = self._unpublish_dropped(self.sync_run_start) if total else 0
        msg = (
            f"Συγχρονισμός ολοκληρώθηκε: {total} προϊόντα διαβάστηκαν.\n"
            f"• Δημιουργήθηκαν: {stats['created']}\n"
            f"• Ενημερώθηκαν: {stats['updated']}\n"
            f"• Χωρίς αλλαγές: {stats['unchanged']}\n"
            f"• Εκτός αποθέματος: {stats['out_of_stock']}\n"
            f"• Αποσύρθηκαν (δεν υπάρχουν πια στο feed): {dropped}\n"
            f"• Παραλείφθηκαν (barcode ανήκει σε άλλο προϊόν): {stats['conflicts']}\n"
            f"• Νέες εικόνες: {stats['images_downloaded']}\n"
            f"• Σφάλματα/Παραλείψεις: {stats['errors']}"
        )
        if not total:
            msg += "\n⚠ Το feed δεν είχε κανένα προϊόν, οπότε δεν αποσύρθηκε τίποτα. Ελέγξτε το Tag Προϊόντος."
        self.write({
            'state': 'ready',
            'last_sync': fields.Datetime.now(),
            'last_sync_message': msg,
            'sync_requested': False,
            'sync_position': 0,
            'sync_file': False,
        })
        self.env.cr.commit()
        _logger.info("Supplier Feed [%s] sync finished: %s", self.name, msg.replace('\n', ' '))

    def _unpublish_dropped(self, run_start):
        """Products of this feed that were not in this run's file."""
        dropped = self.env['product.template'].search([
            ('supplier_feed_id', '=', self.id),
            '|', ('supplier_last_sync', '=', False), ('supplier_last_sync', '<', run_start),
            '|', ('is_published', '=', True),
            ('supplier_availability_text', '!=', self.out_of_stock_text),
        ])
        dropped.write({
            'is_published': False,
            'supplier_availability_text': self.out_of_stock_text,
        })
        return len(dropped)

    @staticmethod
    def _to_list_price(gross, taxes):
        """`gross` is the price the customer pays. A sale tax that is not
        price-included is added on top of list_price, so take it out, or
        the eshop charges VAT twice."""
        added = taxes.filtered(lambda t: not t.price_include)
        if not added or any(t.amount_type != 'percent' for t in added):
            return gross
        return gross / (1 + sum(added.mapped('amount')) / 100)

    @staticmethod
    def _changed_vals(product, vals):
        """Only the fields whose value differs, so a re-sync of an unchanged
        feed writes almost nothing."""
        out = {}
        for key, value in vals.items():
            current = product[key]
            if isinstance(current, models.BaseModel):
                current = current.id
            if isinstance(value, float):
                if float_compare(current or 0.0, value, precision_digits=2):
                    out[key] = value
            elif (current or False) != (value or False):
                out[key] = value
        return out

    def _process_feed_item(self, item, stats, maps, sale_taxes, seen_ids):
        sku_map, barcode_map, all_barcodes, all_codes, image_cache = maps
        sku = item['sku']
        barcode = (item.get('barcode') or '').strip()
        Template = self.env['product.template']

        # Only this feed's products are ever matched; see _load_lookup_maps.
        product = sku_map.get(sku) or (barcode and barcode_map.get(barcode)) or Template
        if barcode and all_barcodes.get(barcode, product.id) != product.id:
            if not product:
                # The barcode is one of your own (or another feed's)
                # products. Leave it alone rather than create a duplicate.
                stats['conflicts'] += 1
                return
            barcode = ''  # existing feed product: keep it, skip the barcode

        try:
            cost = float(str(item.get('cost') or 0.0).replace(',', '.').strip())
        except (ValueError, TypeError):
            cost = 0.0

        retail_price = self._calculate_retail_price(cost)
        is_in_stock = self._evaluate_stock(item.get('quantity'), item.get('availability'))
        if retail_price <= 0.0:
            is_in_stock = False

        if is_in_stock:
            avail_text = self.in_stock_text
            is_published = True
        else:
            stats['out_of_stock'] += 1
            avail_text = self.out_of_stock_text
            is_published = self.out_of_stock_action == 'keep_note'
        if product.supplier_manual_unpublish:
            is_published = False

        shipping_info = self.shipping_lead_time or ''
        if self.shipping_note:
            shipping_info = f"{shipping_info} ({self.shipping_note})" if shipping_info else self.shipping_note

        # Cost is stored net of VAT, like any other product cost.
        net_cost = cost
        if self.vat_included_in_feed and self.vat_rate > 0:
            net_cost = cost / (1 + self.vat_rate / 100.0)

        taxes = product.taxes_id if product else sale_taxes
        vals = {
            'name': item.get('name') or product.name or f"Προϊόν {sku}",
            'is_supplier_feed_product': True,
            'supplier_feed_id': self.id,
            'supplier_sku': sku,
            'supplier_cost': cost,
            'supplier_availability_text': avail_text,
            'supplier_shipping_text': shipping_info,
            'is_published': is_published,
            'list_price': round(self._to_list_price(retail_price, taxes), 4),
            'standard_price': net_cost,
            'is_storable': False,
            'type': 'consu',
            'sale_ok': True,
        }

        if 'qol_no_auto_publish' in Template._fields:
            vals['qol_no_auto_publish'] = True

        if not product and sku not in all_codes:
            vals['default_code'] = sku
            all_codes.add(sku)

        if barcode and barcode != product.barcode:
            vals['barcode'] = barcode

        if item.get('description') and not product.description_sale:
            vals['description_sale'] = item['description']

        if self.auto_create_brands and item.get('brand') and 'brand_id' in Template._fields:
            brand_id = self._get_or_create_brand(item['brand'])
            if brand_id:
                vals['brand_id'] = brand_id

        if product:
            vals = self._changed_vals(product, vals)

        # x2many and image values are only added when they really change
        if self.auto_create_categories and item.get('category') and not product.public_categ_ids:
            categ_id = self._get_or_create_category(item['category'])
            if categ_id:
                vals['public_categ_ids'] = [(6, 0, [categ_id])]

        image_url = item.get('image')
        if image_url:
            can_download = (
                self.max_images_per_sync <= 0 or
                stats['images_downloaded'] < self.max_images_per_sync
            )
            # supplier_image_url is only stored after a successful download,
            # so comparing it is enough (reading image_1920 would load every
            # image from the filestore on every sync)
            if product.supplier_image_url != image_url and can_download:
                img_b64 = self._download_image_b64(image_url, image_cache)
                if img_b64:
                    vals['image_1920'] = img_b64
                    vals['supplier_image_url'] = image_url
                    stats['images_downloaded'] += 1

        if self.partner_id:
            seller = product.seller_ids.filtered(lambda s: s.partner_id == self.partner_id)[:1]
            if not seller:
                vals['seller_ids'] = [(0, 0, {
                    'partner_id': self.partner_id.id, 'product_code': sku, 'price': net_cost})]
            elif seller.product_code != sku or float_compare(seller.price, net_cost, precision_digits=2):
                vals['seller_ids'] = [(1, seller.id, {'product_code': sku, 'price': net_cost})]

        if not product:
            vals['supplier_last_sync'] = self.sync_run_start
            product = Template.create(vals)
            stats['created'] += 1
            sku_map[sku] = product
        else:
            if vals:
                product.write(vals)
                stats['updated'] += 1
            else:
                stats['unchanged'] += 1
            # every existing product in the file, changed or not, is «seen»:
            # _unpublish_dropped withdraws the ones that are not
            seen_ids.append(product.id)
        if 'image_1920' in vals:
            # Odoo builds the image sizes lazily, at the next flush. Left to
            # the checkpoint commit, 48 of them cost ~105s CPU in one go and
            # the 60s worker limit killed every batch (2026-11-09). Paying
            # here keeps the cost inside this item, where the batch's time
            # check sees it.
            self.env.flush_all()
        if barcode:
            barcode_map[barcode] = product
            all_barcodes[barcode] = product.id

    def _get_or_create_category(self, cat_path):
        delimiter = '>' if '>' in cat_path else ('/' if '/' in cat_path else None)
        parts = [html.unescape(p).strip() for p in (cat_path.split(delimiter) if delimiter else [cat_path]) if p.strip()]
        if not parts:
            return False

        parent_id = False
        categ = False
        PublicCategory = self.env['product.public.category']
        for name in parts:
            categ = PublicCategory.search([('name', '=', name), ('parent_id', '=', parent_id)], limit=1)
            if not categ:
                categ = PublicCategory.create({'name': name, 'parent_id': parent_id})
            parent_id = categ.id
        return categ.id if categ else False

    def _get_or_create_brand(self, brand_name):
        name = brand_name.strip()
        if not name or 'product.brand' not in self.env:
            return False
        Brand = self.env['product.brand']
        brand = Brand.search([('name', '=ilike', name)], limit=1)
        if not brand:
            brand = Brand.create({'name': name})
        return brand.id
