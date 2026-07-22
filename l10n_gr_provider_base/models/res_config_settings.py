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
        renamed = archived = activated = 0
        for template_id, new_name in TAX_RENAME_MAP.items():
            tax = gr_tax(self.env, company, template_id)
            if not tax:
                continue
            # the rename map IS the needed catalog — make sure it's active,
            # so the button always ends on a working tax set
            if not tax.active:
                tax.active = True
                activated += 1
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
        # Upstream l10n_gr bug: the chart attaches the island 24→17/13→9/6→4
        # remaps to the MAINLAND fiscal positions too, so mainland clients get
        # Aegean rates. Strip the island destinations from the non-Aegean FPs.
        fp_fixed = 0
        for fp_template in ('fiscal_position_template_domestic',
                            'fiscal_position_template_4'):
            fp = self.env.ref(
                f'account.{company.id}_{fp_template}', raise_if_not_found=False)
            if not fp:
                continue
            wrong = fp.tax_ids.filtered(
                lambda t: t.original_tax_ids and int(t.amount) in (17, 9, 4))
            if wrong:
                fp.tax_ids -= wrong
                fp_fixed += len(wrong)
        # also creates any missing GR journals (e.g. a DB where the chart
        # loaded before this module) — idempotent
        journal_counts = self.env['account.journal'] \
            ._l10n_gr_prov_create_journals(company)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'message': _(
                    'Τακτοποίηση: %(renamed)s μετονομασίες φόρων, %(activated)s '
                    'ενεργοποιήσεις, %(archived)s αρχειοθετήσεις, %(fp_fixed)s '
                    'διορθώσεις νησιωτικών ΦΠΑ σε ηπειρωτικά καθεστώτα, '
                    '%(created)s νέα ημερολόγια, %(refund_seq)s ημερολόγια '
                    'χωρίς πλέον ακολουθία πιστωτικών (R), %(accounts)s '
                    'προεπιλεγμένοι λογαριασμοί ημερολογίων, %(print_forms)s '
                    'ημερολόγια λιανικής σε φόρμα 80mm.',
                    renamed=renamed, activated=activated, archived=archived,
                    fp_fixed=fp_fixed, **journal_counts),
            },
        }
