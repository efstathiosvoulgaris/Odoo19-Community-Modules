# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    skroutz_feed_token = fields.Char(
        string='Feed Token',
        config_parameter='skroutz.feed_token',
        help='Optional secret token to protect the feed URL. '
             'Access: /skroutz/feed?token=YOUR_TOKEN',
    )
    skroutz_default_availability = fields.Selection(
        selection=[
            ('In stock', 'In stock (Express)'),
            ('Delivery 1 to 3 days', 'Delivery 1 to 3 days'),
            ('Delivery 4 to 6 days', 'Delivery 4 to 6 days'),
            ('Delivery up to 12 days', 'Delivery up to 12 days'),
        ],
        string='Default Availability (out of stock)',
        config_parameter='skroutz.default_availability',
        default='Delivery 1 to 3 days',
        help='Availability shown for products with 0 stock quantity.',
    )
    skroutz_include_zero_stock = fields.Boolean(
        string='Include 0-stock products',
        config_parameter='skroutz.include_zero_stock',
        default=True,
        help='If enabled, products with 0 stock are still included in the feed '
             'with quantity=0. Skroutz recommends keeping them for reactivation.',
    )
    skroutz_feed_url = fields.Char(
        string='Feed URL',
        compute='_compute_skroutz_feed_url',
    )

    # ── Order Management (API) ────────────────────────────────────────────────

    skroutz_api_token = fields.Char(
        string='API Token',
        config_parameter='skroutz.api_token',
        help='Bearer token generated from your Skroutz merchant panel (Merchants > Services > Skroutz Marketplace).',
    )
    skroutz_webhook_secret = fields.Char(
        string='Webhook Secret',
        config_parameter='skroutz.webhook_secret',
        help='Optional secret token embedded in the webhook URL: /skroutz/webhook/<secret>. '
             'Register the full URL (including the secret) in your Skroutz merchant panel. '
             'Skroutz does not sign webhook requests, so the URL token is the authentication. '
             'Leave empty to accept calls on the plain /skroutz/webhook URL.',
    )
    skroutz_auto_create_sale_order = fields.Boolean(
        string='Auto-create Sale Order on Accept',
        config_parameter='skroutz.auto_create_sale_order',
        default=True,
        help='When an order is accepted, automatically create a linked Odoo Sale Order.',
    )

    def _get_public_base_url(self):
        """Return the public-facing base URL.

        web.base.url stores the last-seen internal URL, which on cloud/Odoo.sh
        databases is the container hostname (e.g. http://dev) rather than the
        real public domain. website.get_base_url() reads the website's domain
        field and always returns the correct public URL.
        """
        website = self.env['website'].sudo().search([], limit=1)
        if website:
            return website.get_base_url()
        return self.env['ir.config_parameter'].sudo().get_param('web.base.url', '')

    @api.depends('skroutz_feed_token')
    def _compute_skroutz_feed_url(self):
        base_url = self._get_public_base_url()
        for rec in self:
            if rec.skroutz_feed_token:
                rec.skroutz_feed_url = f"{base_url}/skroutz/feed?token={rec.skroutz_feed_token}"
            else:
                rec.skroutz_feed_url = f"{base_url}/skroutz/feed"

    def action_preview_skroutz_feed(self):
        base_url = self._get_public_base_url()
        token = self.env['ir.config_parameter'].sudo().get_param('skroutz.feed_token', '')
        url = f"{base_url}/skroutz/feed"
        if token:
            url += f"?token={token}"
        return {'type': 'ir.actions.act_url', 'url': url, 'target': 'new'}

    def action_download_skroutz_feed(self):
        base_url = self._get_public_base_url()
        token = self.env['ir.config_parameter'].sudo().get_param('skroutz.feed_token', '')
        url = f"{base_url}/skroutz/feed?download=1"
        if token:
            url += f"&token={token}"
        return {'type': 'ir.actions.act_url', 'url': url, 'target': 'new'}
