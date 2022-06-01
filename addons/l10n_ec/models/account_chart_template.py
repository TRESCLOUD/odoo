# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models


class AccountChartTemplate(models.Model):
    _inherit = "account.chart.template"

    def _prepare_all_journals(self, acc_template_ref, company, journals_dict=None):
        res = super(AccountChartTemplate, self)._prepare_all_journals(acc_template_ref, company, journals_dict=journals_dict)
        for r in res:
            if r.get('code') == 'INV':
                r.update({'name': '001-001 ' + r.get('name')})
        self._l10n_ec_configure_ecuadorian_journal(company)
        return res

    def _l10n_ec_configure_ecuadorian_journal(self, companies):
        ecuadorian_companies = companies.filtered(lambda r: r.country_code == 'EC')
        for company in ecuadorian_companies:
            self = self.with_company(company)
            new_journals = [
                {'code':'LIQCO', 'name':'001-001 Liquidación de compra'}
                ] #withhold journals will created in specific module
            for new_journal in new_journals:
                journal = self.env['account.journal'].search([
                    ('code', '=', new_journal['code']),
                    ('company_id', '=', company.id)])
                if not journal:
                    journal = self.env['account.journal'].create({
                        'name': new_journal['name'],
                        'code': new_journal['code'],
                        'l10n_latam_use_documents': True,
                        'type': 'purchase',
                        'company_id': company.id,
                        'show_on_dashboard': True,
                    })
    