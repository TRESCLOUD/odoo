# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from openupgradelib import openupgrade


@openupgrade.logging()
def update_tax_factor_percent(env):
    env.cr.execute('''
        update account_tax_repartition_line set factor_percent=100 where factor_percent=12 and repartition_type='tax'
    ''')
    
def update_withhold_type(env):
    env.cr.execute('''
        update account_tax
        set tax_group_id=t.id from (select id from account_tax_group where l10n_ec_type='withhold_vat_sale') as t
        where account_tax.id in (select id from account_tax where tax_group_id in (select id from account_tax_group where l10n_ec_type='withhold_vat') and type_tax_use='sale')
    ''')
    env.cr.execute('''
        update account_tax
        set tax_group_id=t.id from (select id from account_tax_group where l10n_ec_type='withhold_vat_purchase') as t
        where account_tax.id in (select id from account_tax where tax_group_id in (select id from account_tax_group where l10n_ec_type='withhold_vat') and type_tax_use='purchase')
    ''')
    env.cr.execute('''
        update account_tax
        set tax_group_id=t.id from (select id from account_tax_group where l10n_ec_type='withhold_income_sale') as t
        where account_tax.id in (select id from account_tax where tax_group_id in (select id from account_tax_group where l10n_ec_type='withhold_income_tax') and type_tax_use='sale')
    ''')
    env.cr.execute('''
        update account_tax
        set tax_group_id=t.id from (select id from account_tax_group where l10n_ec_type='withhold_income_purchase') as t
        where account_tax.id in (select id from account_tax where tax_group_id in (select id from account_tax_group where l10n_ec_type='withhold_income_tax') and type_tax_use='purchase')
    ''')
    env.cr.execute('''
        delete from account_tax_group where l10n_ec_type in ('withhold_vat', 'withhold_income_tax')
    ''')
     
@openupgrade.migrate(use_env=True)
def migrate(env, version):
    update_tax_factor_percent(env)
    update_withhold_type(env)
    