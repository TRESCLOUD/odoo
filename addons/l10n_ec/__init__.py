# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
from . import models
from . import demo
from odoo import api, SUPERUSER_ID


def _post_install_hook_configure_ecuadorian(cr, registry):
    env = api.Environment(cr, SUPERUSER_ID, {})
    companies = env['res.company'].search([])
    for company in companies:
        if company.country_code == 'EC':
            env['account.chart.template']._l10n_ec_configure_ecuadorian_journal(company)
