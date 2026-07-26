# -*- coding: utf-8 -*-
from odoo import models


class AccountChartTemplate(models.AbstractModel):
    _inherit = 'account.chart.template'

    def _load(self, template_code, company, install_demo, force_create=True):
        """Create the Greek myDATA journals right after the chart is loaded.

        Order matters: the chart loader merges its template journals onto
        journals that already exist, which used to hijack our ΤΙΜ journal
        (rewriting its name and dropping the myDATA type) whenever the module
        was installed before the chart. Creating ours afterwards leaves the
        company's own default sale journal untouched — it stays available for
        sales that have nothing to do with myDATA — and gives us a clean ΤΙΜ.
        """
        res = super()._load(template_code, company, install_demo, force_create)
        if company.account_fiscal_country_id.code == 'GR':
            self.env['account.journal'].with_company(company) \
                ._l10n_gr_prov_create_journals(company)
        return res
