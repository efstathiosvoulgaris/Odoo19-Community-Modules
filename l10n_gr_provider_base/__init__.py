# -*- coding: utf-8 -*-
from . import models


def post_init_hook(env):
    """Create Greek myDATA journals for all existing Greek companies."""
    gr_companies = env['res.company'].search([('account_fiscal_country_id.code', '=', 'GR')])
    for company in gr_companies:
        env['account.journal'].with_company(company)._l10n_gr_prov_create_journals(company)
