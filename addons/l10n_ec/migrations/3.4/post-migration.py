# -*- coding: utf-8 -*-

from odoo import api, SUPERUSER_ID
  
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
    
def unlink_old_withhold_group(env):
    # TODO: José, borrarlo por python para que se borre tambien su XML_ID
    env.cr.execute('''
        delete from account_tax_group where l10n_ec_type in ('withhold_vat', 'withhold_income_tax')
    ''')
    
def update_vat_withhold_base_percent(env):
    # Fixes vat withhold base amount
    all_companies = env['res.company'].search([])
    ecuadorian_companies = all_companies.filtered(lambda r: r.country_code == 'EC')
    # TODO Jose, mejorar el SQL, poner con un left join un filtro solo a los impuestos cuyo grupo sea 
    # del tipo retencion IVA compras y retencion IVA ventas
    # y que sean del alguna de las compañías ecuatorianas, ecuadorian_companies.ids
    env.cr.execute('''
        update account_tax_repartition_line set factor_percent=100 where factor_percent=12 and repartition_type='tax'
    ''')

def migrate(cr, version):
    # For vat withhold taxes, replace factor_percent=12% with factor_percent=100%
    # For vat withhold taxes, replace factor_percent=12% with factor_percent=100%
    env = api.Environment(cr, SUPERUSER_ID, {})
    update_withhold_type(env)
    update_vat_withhold_base_percent(env)
    
