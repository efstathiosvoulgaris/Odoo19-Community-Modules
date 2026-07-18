# -*- coding: utf-8 -*-
from odoo import fields, models, _

from .gr_mydata import TAX_RENAME_MAP, TAX_ARCHIVE_TEMPLATES, gr_tax


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    l10n_gr_prov_provider = fields.Selection(
        related='company_id.l10n_gr_prov_provider', readonly=False)
    l10n_gr_prov_test_env = fields.Boolean(
        related='company_id.l10n_gr_prov_test_env', readonly=False)
    l10n_gr_prov_auto_send = fields.Boolean(
        related='company_id.l10n_gr_prov_auto_send', readonly=False)
    l10n_gr_prov_guard_tax = fields.Boolean(
        related='company_id.l10n_gr_prov_guard_tax', readonly=False)
    l10n_gr_prov_guard_island = fields.Boolean(
        related='company_id.l10n_gr_prov_guard_island', readonly=False)

    def action_l10n_gr_prov_tidy_taxes(self):
        """Give the GR chart taxes self-explanatory Greek names and archive the
        unused «EU Other» variants. Idempotent; archiving is reversible from
        the taxes list. Taxes are matched by chart xmlid, so re-running after a
        chart reload just reapplies the names."""
        self.ensure_one()
        company = self.company_id
        renamed = archived = 0
        for template_id, new_name in TAX_RENAME_MAP.items():
            tax = gr_tax(self.env, company, template_id)
            if not tax:
                continue
            for lang in [code for code, _n in self.env['res.lang'].get_installed()]:
                translated = tax.with_context(lang=lang)
                if translated.name != new_name:
                    translated.name = new_name
                    renamed += 1
        for template_id in TAX_ARCHIVE_TEMPLATES:
            tax = gr_tax(self.env, company, template_id)
            if not tax or not tax.active:
                continue
            # never archive a tax with accounting history
            if self.env['account.move.line'].search_count(
                    [('tax_ids', 'in', tax.id)], limit=1):
                continue
            tax.active = False
            archived += 1
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'message': _(
                    'Τακτοποίηση φόρων: %(renamed)s μετονομασίες, '
                    '%(archived)s αρχειοθετήσεις.',
                    renamed=renamed, archived=archived),
            },
        }
