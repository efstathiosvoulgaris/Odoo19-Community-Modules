# -*- coding: utf-8 -*-
from . import models


def post_init_hook(env):
    """Create the Greek myDATA journals for companies that already run a chart.

    Companies with no chart yet are skipped on purpose: journals created into an
    empty company are exactly what the chart loader hijacks (it merges its own
    template journals onto existing ones). Those companies get their journals
    from the account.chart.template._load override instead — right after the
    chart lands, so the company's default sale journal is left untouched.
    """
    gr_companies = env['res.company'].search([
        ('account_fiscal_country_id.code', '=', 'GR'),
        ('chart_template', '!=', False),
    ])
    for company in gr_companies:
        env['account.journal'].with_company(company)._l10n_gr_prov_create_journals(company)
