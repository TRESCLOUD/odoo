# -*- encoding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2004-2010 Tiny SPRL (<http://tiny.be>).
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

import time
from datetime import datetime
from dateutil.relativedelta import relativedelta

from openerp.osv import fields, osv
import openerp.addons.decimal_precision as dp
from tools.translate import _
# TRESCLOUD, requerido para obtener el ultimo dia del mes
import calendar
import logging
_logger = logging.getLogger(__name__)


class account_asset_category(osv.osv):
    _name = 'account.asset.category'
    _description = 'Asset category'

    _columns = {
        'name': fields.char('Name', size=64, required=True, select=1),
        'note': fields.text('Note'),
        'account_analytic_id': fields.many2one('account.analytic.account', 'Analytic account'),
        'account_asset_id': fields.many2one('account.account', 'Asset Account', required=True, domain=[('type','=','other')]),
        'account_depreciation_id': fields.many2one('account.account', 'Depreciation Account', required=True, domain=[('type','=','other')]),
        'account_expense_depreciation_id': fields.many2one('account.account', 'Depr. Expense Account', required=True, domain=[('type','=','other')]),
        'journal_id': fields.many2one('account.journal', 'Journal', required=True),
        'company_id': fields.many2one('res.company', 'Company', required=True),
        'method': fields.selection([('linear','Linear'),('degressive','Degressive')], 'Computation Method', required=True, help="Choose the method to use to compute the amount of depreciation lines.\n"\
            "  * Linear: Calculated on basis of: Gross Value / Number of Depreciations\n" \
            "  * Degressive: Calculated on basis of: Residual Value * Degressive Factor"),
        'method_number': fields.integer('Number of Depreciations', help="The number of depreciations needed to depreciate your asset"),
        'method_period': fields.integer('Period Length', help="State here the time between 2 depreciations, in months", required=True),
        'method_progress_factor': fields.float('Degressive Factor'),
        'method_time': fields.selection([('number','Number of Depreciations'),('end','Ending Date')], 'Time Method', required=True,
                                  help="Choose the method to use to compute the dates and number of depreciation lines.\n"\
                                       "  * Number of Depreciations: Fix the number of depreciation lines and the time between 2 depreciations.\n" \
                                       "  * Ending Date: Choose the time between 2 depreciations and the date the depreciations won't go beyond."),
        'method_end': fields.date('Ending date'),
        'prorata':fields.boolean('Prorata Temporis', help='Indicates that the first depreciation entry for this asset have to be done from the purchase date instead of the first January'),
        'open_asset': fields.boolean('Skip Draft State', help="Check this if you want to automatically confirm the assets of this category when created by invoices."),
    }

    _defaults = {
        'company_id': lambda self, cr, uid, context: self.pool.get('res.company')._company_default_get(cr, uid, 'account.asset.category', context=context),
        'method': 'linear',
        'method_number': 5,
        'method_time': 'number',
        'method_period': 12,
        'method_progress_factor': 0.3,
    }

    def onchange_account_asset(self, cr, uid, ids, account_asset_id, context=None):
        res = {'value':{}}
        if account_asset_id:
           res['value'] = {'account_depreciation_id': account_asset_id}
        return res

account_asset_category()

class account_asset_asset(osv.osv):
    _name = 'account.asset.asset'
    _description = 'Asset'

    def unlink(self, cr, uid, ids, context=None):
        for asset in self.browse(cr, uid, ids, context=context):
            if asset.account_move_line_ids: 
                raise osv.except_osv(_('Error!'), _('You cannot delete an asset that contains posted depreciation lines.'))
        return super(account_asset_asset, self).unlink(cr, uid, ids, context=context)

    def _get_period(self, cr, uid, context=None):
        ctx = dict(context or {}, account_period_prefer_normal=True)
        periods = self.pool.get('account.period').find(cr, uid, context=ctx)
        if periods:
            return periods[0]
        else:
            return False

    def _get_last_depreciation_date(self, cr, uid, ids, context=None):
        """
        @param id: ids of a account.asset.asset objects
        @return: Returns a dictionary of the effective dates of the last depreciation entry made for given asset ids. If there isn't any, return the purchase date of this asset
        """
        # TRESCLOUD: El siguiente código fue modificado por que en la tabla de depreciaciones cuando se 
        # ejecutaba un depreciacion se generaba para el mismo periodo una copia en borrador
        if context is None:
            context = {}
        if context.get('posted'):
            cr.execute("""
                SELECT a.id as id, CAST(CAST(COALESCE(MAX(l.date),a.purchase_date) AS DATE) + CAST('1 month' AS INTERVAL) AS DATE) AS date
                FROM account_asset_asset a
                LEFT JOIN account_move_line l ON (l.asset_id = a.id)
                WHERE a.id IN %s
                GROUP BY a.id, a.purchase_date """, (tuple(ids),))
        else:
            cr.execute("""
                SELECT a.id as id, COALESCE(MAX(l.date),a.purchase_date) AS date
                FROM account_asset_asset a
                LEFT JOIN account_move_line l ON (l.asset_id = a.id)
                WHERE a.id IN %s
                GROUP BY a.id, a.purchase_date """, (tuple(ids),))
        return dict(cr.fetchall())

    def _compute_board_amount(self, cr, uid, asset, i, residual_amount, amount_to_depr, undone_dotation_number, posted_depreciation_line_ids, total_days, depreciation_date, context=None):
        #by default amount = 0
        amount = 0
        if i == undone_dotation_number:
            amount = residual_amount
        else:
            if asset.method == 'linear':
                amount = amount_to_depr / (undone_dotation_number - len(posted_depreciation_line_ids))
                # TRESCLOUD: Se verifica la fecha de depreciacion para el caso particular de que
                # se requiera prorratear pero a inicio de mes, este caso es como no hacer prorrateo
                if asset.prorata and depreciation_date.day != 1:
                    # TRESCLOUD: Al ser prorrateado se inicia la depreciacion 
                    # al dia de la fecha indicada en el campo purchase_date
                    # Para recalculo de depreciacion prorrateada cuando ya existen asientos se cumplen estas condiciones:
                    # 1) Se realizan las n depreciaciones indicadas + 1
                    # 2) Se calcula el valor restante dividiendo para el numero de cuotas enteras + la fraccion de mes que falta 
                    total_days = calendar.monthrange(depreciation_date.year,depreciation_date.month)[1]
                    days = total_days - depreciation_date.day + 1
                    if len(posted_depreciation_line_ids) == 0:
                        amount = amount_to_depr / asset.method_number
                        if i == 1:
                            amount = (amount_to_depr / asset.method_number) / total_days * days
                    else:
                        # TRESCLOUD: la porcion de dias debe calcularse a 31 por casos de prorrateo com el siguiente:
                        # depreciacion en 29, 30, 31 pero ultima depreciacion en febrero (28 dias)
                        total_days = 31
                        amount = amount_to_depr / ((asset.method_number - len(posted_depreciation_line_ids)) + (float(depreciation_date.day) / float(total_days)))
            elif asset.method == 'degressive':
                amount = residual_amount * asset.method_progress_factor
                if asset.prorata:
                    days = total_days - float(depreciation_date.strftime('%j'))
                    if i == 1:
                        amount = (residual_amount * asset.method_progress_factor) / total_days * days
                    elif i == undone_dotation_number:
                        amount = (residual_amount * asset.method_progress_factor) / total_days * (total_days - days)
        return amount

    def _compute_board_undone_dotation_nb(self, cr, uid, asset, depreciation_date, total_days, context=None):
        undone_dotation_number = asset.method_number
        if asset.method_time == 'end':
            end_date = datetime.strptime(asset.method_end, '%Y-%m-%d')
            undone_dotation_number = 0
            while depreciation_date <= end_date:
                depreciation_date = (datetime(depreciation_date.year, depreciation_date.month, depreciation_date.day) + relativedelta(months=+asset.method_period))
                undone_dotation_number += 1
        # TRESCLOUD: Verifico si la depreciacion prorrateada inicia en el
        # dia uno del mes, de ser el caso se le trata como una depreciacion
        # sin prorrateo
        #
        # Estas lineas verifica si en la lista de campos existe el denominado asset_type
        # Esto por que el campo esta en el modulo asset y por ahora se tendra dividido la funcionalidad
        # para manejar bienes de control
        asset_type = False
        if 'asset_type' in self._columns:
            asset_type = asset.asset_type
        #
        #
        if asset.prorata and depreciation_date.day != 1:
            if asset_type and asset_type == 'good_control':
                undone_dotation_number = 0 
            else:
                undone_dotation_number += 1
        return undone_dotation_number

    def compute_depreciation_board(self, cr, uid, ids, context=None):
        # TRESCLOUD: Se controla el context
        context = context or {}
        depreciation_lin_obj = self.pool.get('account.asset.depreciation.line')
        currency_obj = self.pool.get('res.currency')
        for asset in self.browse(cr, uid, ids, context=context):
            if asset.value_residual == 0.0:
                continue
            posted_depreciation_line_ids = depreciation_lin_obj.search(cr, uid, [('asset_id', '=', asset.id), ('move_check', '=', True)],order='depreciation_date desc')
            old_depreciation_line_ids = depreciation_lin_obj.search(cr, uid, [('asset_id', '=', asset.id), ('move_id', '=', False)])
            if old_depreciation_line_ids:
                depreciation_lin_obj.unlink(cr, uid, old_depreciation_line_ids, context=context)
            amount_to_depr = residual_amount = asset.value_residual
            module_ids = self.pool.get('ir.module.module').search(cr, uid, [('name','=','asset'), ('state','=','installed')], context=context)
            if module_ids:
                amount_to_depr = residual_amount = asset.value_residual
            if asset.prorata:
                # TRESCLOUD: El siguiente código fue modificado por que en la tabla de depreciaciones cuando se 
                # ejecutaba un depreciacion se generaba para el mismo perido una copia en borrador
                if posted_depreciation_line_ids:
                   context.update({'posted': True}) 
                depreciation_date = datetime.strptime(self._get_last_depreciation_date(cr, uid, [asset.id], context)[asset.id], '%Y-%m-%d')
            else:
                # depreciation_date = 1st January of purchase year
                purchase_date = datetime.strptime(asset.purchase_date, '%Y-%m-%d')
                #if we already have some previous validated entries, starting date isn't 1st January but last entry + method period
                if (len(posted_depreciation_line_ids)>0):
                    last_depreciation_date = datetime.strptime(depreciation_lin_obj.browse(cr,uid,posted_depreciation_line_ids[0],context=context).depreciation_date, '%Y-%m-%d')
                    depreciation_date = (last_depreciation_date+relativedelta(months=+asset.method_period))
                else:
                    # TRESCLOUD: La depreciacion se la realiza mensualmente y no anualmente
                    depreciation_date = datetime(purchase_date.year, purchase_date.month, 1)
            day = depreciation_date.day
            month = depreciation_date.month
            year = depreciation_date.year
            total_days = (year % 4) and 365 or 366
            # TRESCLOUD: Se lee la depreciacion acumulada por que en recalculos la tabla requiere retomar desde este valor
            accumulated_depreciation = asset.accumulated_depreciation
            undone_dotation_number = self._compute_board_undone_dotation_nb(cr, uid, asset, depreciation_date, total_days, context=context)
            for x in range(len(posted_depreciation_line_ids), undone_dotation_number):
                i = x + 1
                amount = self._compute_board_amount(cr, uid, asset, i, residual_amount, amount_to_depr, undone_dotation_number, posted_depreciation_line_ids, total_days, depreciation_date, context=context)
                # TRESCLOUD: Problemas con redondeo fallaba por 3 o 4 centavos en la cuota final
                amount_round = round(amount, self.pool.get('decimal.precision').precision_get(cr, uid, 'Account'))
                residual_amount -= amount_round
                vals = {
                     # TRESCLOUD: Se trabaja con valores redondeados
                     'amount': amount_round,
                     'asset_id': asset.id,
                     'sequence': i,
                     'name': str(asset.id) +'/' + str(i),
                     'remaining_value': residual_amount,
                     # TRESCLOUD: Para recalculos realizados la tabla debe reconstruirse desde el valor anterior depreciado
                     # o el valor de compra, sea que exista uno u otro. Sea por las linea de depreciacion existente
                     # o por las opciones avanzadas aplicadas.
                     'depreciated_value': accumulated_depreciation + (asset.value_residual or asset.purchase_value - asset.salvage_value) - (residual_amount + amount_round),
                     'depreciation_date': depreciation_date.strftime('%Y-%m-%d'),
                }
                depreciation_lin_obj.create(cr, uid, vals, context=context)
                # Considering Depr. Period as months
                depreciation_date = (datetime(year, month, day) + relativedelta(months=+asset.method_period))
                day = depreciation_date.day
                month = depreciation_date.month
                year = depreciation_date.year
        return True

    def validate(self, cr, uid, ids, context=None):
        if context is None:
            context = {}
        return self.write(cr, uid, ids, {
            'state':'open'
        }, context)

    def set_to_close(self, cr, uid, ids, context=None):
        return self.write(cr, uid, ids, {'state': 'close'}, context=context)

    def set_to_draft(self, cr, uid, ids, context=None):
        return self.write(cr, uid, ids, {'state': 'draft'}, context=context)

    def _amount_residual(self, cr, uid, ids, name, args, context=None):
        # TRESCLOUD: Para que el nuevo wizard que permite aumentar o disminuir el valor depreciado
        # afecte correctamente el campo amount residual es necesario que la sumatoria considere
        # todos los asientos con su signo, antes usaba el valor absoluto eliminando el signo.
        # Tambien hace falta que dependa del contexto ya se usa analisis_date como fecha de analisis
        context = context or {}
        analisis_date = datetime.now().strftime('%Y-%m-%d')
        sql = """SELECT
                l.asset_id as id, SUM(l.debit-l.credit) AS amount
            FROM
                account_move_line l
            WHERE
                l.asset_id IN %s """
        param = [tuple(ids)]
        if 'analisis_date' in context and context['analisis_date']:
            analisis_date = context['analisis_date']
            sql += """and l.date <= %s
            """
            param.append(analisis_date) 
        sql += "            GROUP BY l.asset_id"
        cr.execute(sql, tuple(param))
        res=dict(cr.fetchall())
        for asset in self.browse(cr, uid, ids, context):
            company_currency = asset.company_id.currency_id.id
            current_currency = asset.currency_id.id
            amount = self.pool['res.currency'].compute(cr, uid, company_currency, current_currency, res.get(asset.id, 0.0), context=context)
            res[asset.id] = asset.purchase_value - amount - asset.salvage_value
        for id in ids:
            res.setdefault(id, 0.0)
        return res

    def onchange_company_id(self, cr, uid, ids, company_id=False, context=None):
        val = {}
        if company_id:
            company = self.pool.get('res.company').browse(cr, uid, company_id, context=context)
            if company.currency_id.company_id and company.currency_id.company_id.id != company_id:
                val['currency_id'] = False
            else:
                val['currency_id'] = company.currency_id.id
        return {'value': val}
    
    def onchange_purchase_salvage_value(self, cr, uid, ids, purchase_value, salvage_value, context=None):
        val = {}
        for asset in self.browse(cr, uid, ids, context=context):
            if purchase_value:
                val['value_residual'] = purchase_value - salvage_value
            if salvage_value:
                val['value_residual'] = purchase_value - salvage_value
        return {'value': val}    

    _columns = {
        'account_move_line_ids': fields.one2many('account.move.line', 'asset_id', 'Entries', readonly=True, states={'draft':[('readonly',False)]}),
        'name': fields.char('Asset Name', size=64, required=True, readonly=True, states={'draft':[('readonly',False)]}),
        'code': fields.char('Reference', size=32, readonly=True, states={'draft':[('readonly',False)]}),
        'purchase_value': fields.float('Gross Value', required=True, readonly=True, states={'draft':[('readonly',False)]}),
        'currency_id': fields.many2one('res.currency','Currency',required=True, readonly=True, states={'draft':[('readonly',False)]}),
        'company_id': fields.many2one('res.company', 'Company', required=True, readonly=True, states={'draft':[('readonly',False)]}),
        'note': fields.text('Note'),
        'category_id': fields.many2one('account.asset.category', 'Asset Category', required=True, change_default=True, readonly=True, states={'draft':[('readonly',False)]}),
        'parent_id': fields.many2one('account.asset.asset', 'Parent Asset', readonly=True, states={'draft':[('readonly',False)]}),
        'child_ids': fields.one2many('account.asset.asset', 'parent_id', 'Children Assets'),
        'purchase_date': fields.date('Purchase Date', required=True, readonly=True, states={'draft':[('readonly',False)]}),
        'state': fields.selection([('draft','Draft'),('open','Running'),('close','Close')], 'Status', required=True,
                                  help="When an asset is created, the status is 'Draft'.\n" \
                                       "If the asset is confirmed, the status goes in 'Running' and the depreciation lines can be posted in the accounting.\n" \
                                       "You can manually close an asset when the depreciation is over. If the last line of depreciation is posted, the asset automatically goes in that status."),
        'active': fields.boolean('Active'),
        'partner_id': fields.many2one('res.partner', 'Partner', readonly=True, states={'draft':[('readonly',False)]}),
        'method': fields.selection([('linear','Linear'),('degressive','Degressive')], 'Computation Method', required=True, readonly=True, states={'draft':[('readonly',False)]}, help="Choose the method to use to compute the amount of depreciation lines.\n"\
            "  * Linear: Calculated on basis of: Gross Value / Number of Depreciations\n" \
            "  * Degressive: Calculated on basis of: Residual Value * Degressive Factor"),
        'method_number': fields.integer('Number of Depreciations', readonly=True, states={'draft':[('readonly',False)]}, help="The number of depreciations needed to depreciate your asset"),
        'method_period': fields.integer('Number of Months in a Period', required=True, readonly=True, states={'draft':[('readonly',False)]}, help="The amount of time between two depreciations, in months"),
        'method_end': fields.date('Ending Date', readonly=True, states={'draft':[('readonly',False)]}),
        'method_progress_factor': fields.float('Degressive Factor', readonly=True, states={'draft':[('readonly',False)]}),
        'value_residual': fields.function(_amount_residual, method=True, digits_compute=dp.get_precision('Account'), string='Residual Value'),
        'method_time': fields.selection([('number','Number of Depreciations'),('end','Ending Date')], 'Time Method', required=True, readonly=True, states={'draft':[('readonly',False)]},
                                  help="Choose the method to use to compute the dates and number of depreciation lines.\n"\
                                       "  * Number of Depreciations: Fix the number of depreciation lines and the time between 2 depreciations.\n" \
                                       "  * Ending Date: Choose the time between 2 depreciations and the date the depreciations won't go beyond."),
        'prorata':fields.boolean('Prorata Temporis', readonly=True, states={'draft':[('readonly',False)]}, help='Indicates that the first depreciation entry for this asset have to be done from the purchase date instead of the first January'),
        'history_ids': fields.one2many('account.asset.history', 'asset_id', 'History', readonly=True),
        'depreciation_line_ids': fields.one2many('account.asset.depreciation.line', 'asset_id', 'Depreciation Lines', readonly=True, states={'draft':[('readonly',False)],'open':[('readonly',False)]}),
        'salvage_value': fields.float('Salvage Value', digits_compute=dp.get_precision('Account'), help="It is the amount you plan to have that you cannot depreciate.", readonly=True, states={'draft':[('readonly',False)]}),
    }
    _defaults = {
        'code': lambda obj, cr, uid, context: obj.pool.get('ir.sequence').get(cr, uid, 'account.asset.code'),
        'purchase_date': lambda obj, cr, uid, context: time.strftime('%Y-%m-%d'),
        'active': True,
        'state': 'draft',
        'method': 'linear',
        'method_number': 5,
        'method_time': 'number',
        'method_period': 12,
        'method_progress_factor': 0.3,
        'currency_id': lambda self,cr,uid,c: self.pool.get('res.users').browse(cr, uid, uid, c).company_id.currency_id.id,
        'company_id': lambda self, cr, uid, context: self.pool.get('res.company')._company_default_get(cr, uid, 'account.asset.asset',context=context),
    }

    def _check_recursion(self, cr, uid, ids, context=None, parent=None):
        return super(account_asset_asset, self)._check_recursion(cr, uid, ids, context=context, parent=parent)

    def _check_prorata(self, cr, uid, ids, context=None):
        for asset in self.browse(cr, uid, ids, context=context):
            if asset.prorata and asset.method_time != 'number':
                return False
        return True

    _constraints = [
        (_check_recursion, 'Error ! You cannot create recursive assets.', ['parent_id']),
        (_check_prorata, 'Prorata temporis can be applied only for time method "number of depreciations".', ['prorata']),
    ]

    def onchange_category_id(self, cr, uid, ids, category_id, context=None):
        res = {'value':{}}
        asset_categ_obj = self.pool.get('account.asset.category')
        if category_id:
            category_obj = asset_categ_obj.browse(cr, uid, category_id, context=context)
            res['value'] = {
                            'method': category_obj.method,
                            'method_number': category_obj.method_number,
                            'method_time': category_obj.method_time,
                            'method_period': category_obj.method_period,
                            'method_progress_factor': category_obj.method_progress_factor,
                            'method_end': category_obj.method_end,
                            'prorata': category_obj.prorata,
            }
        return res

    def onchange_method_time(self, cr, uid, ids, method_time='number', context=None):
        res = {'value': {}}
        if method_time != 'number':
            res['value'] = {'prorata': False}
        return res

    def copy(self, cr, uid, id, default=None, context=None):
        if default is None:
            default = {}
        if context is None:
            context = {}
        default.update({'depreciation_line_ids': [], 'account_move_line_ids': [], 'history_ids': [], 'state': 'draft'})
        return super(account_asset_asset, self).copy(cr, uid, id, default, context=context)

    def _compute_entries(self, cr, uid, ids, period_id, context=None):
        if context is None:
            context = {}
        period_obj = self.pool.get('account.period')
        account_move_obj = self.pool.get('account.move')
        depreciation_obj = self.pool.get('account.asset.depreciation.line')
        period = period_obj.browse(cr, uid, period_id, context=context)
        context.update({'depreciation_date': period.date_stop})
        depreciation_ids = depreciation_obj.search(cr, uid, [('asset_id', 'in', ids), ('depreciation_date', '<=', period.date_stop), ('depreciation_date', '>=', period.date_start), ('move_check', '=', False)], context=context)
        if context.get('reproces_accounting_entry'):
            depreciation_ids = depreciation_obj.search(cr, uid, [('asset_id', 'in', ids), ('depreciation_date', '<=', period.date_stop), ('depreciation_date', '>=', period.date_start)], context=context)
            #Anulamos y eliminamos los apuntes contables existentes para que se vuelvan a generar
            for depreciation in depreciation_obj.browse(cr, uid, depreciation_ids, context=context):
                if depreciation.move_id:
                    account_move_obj.button_cancel(cr, uid, [depreciation.move_id.id], context=context)
                    account_move_obj.unlink(cr, uid, [depreciation.move_id.id], context=context)
        return depreciation_obj.create_move(cr, uid, depreciation_ids, context=context)

    def create(self, cr, uid, vals, context=None):
        asset_id = super(account_asset_asset, self).create(cr, uid, vals, context=context)
        self.compute_depreciation_board(cr, uid, [asset_id], context=context)
        return asset_id
    
    def open_entries(self, cr, uid, ids, context=None):
        if context is None:
            context = {}
        context.update({'search_default_asset_id': ids, 'default_asset_id': ids})
        return {
            'view_type': 'form',
            'view_mode': 'tree,form',
            'res_model': 'account.move.line',
            'view_id': False,
            'type': 'ir.actions.act_window',
            'context': context,
        }

account_asset_asset()

class account_asset_depreciation_line(osv.osv):
    _name = 'account.asset.depreciation.line'
    _description = 'Asset depreciation line'

    def _get_move_check(self, cr, uid, ids, name, args, context=None):
        res = {}
        for line in self.browse(cr, uid, ids, context=context):
            res[line.id] = bool(line.move_id)
        return res

    _columns = {
        'name': fields.char('Depreciation Name', size=64, required=True, select=1),
        'sequence': fields.integer('Sequence', required=True),
        'asset_id': fields.many2one('account.asset.asset', 'Asset', required=True, ondelete='cascade'),
        'parent_state': fields.related('asset_id', 'state', type='char', string='State of Asset'),
        'amount': fields.float('Current Depreciation', digits_compute=dp.get_precision('Account'), required=True),
        'remaining_value': fields.float('Next Period Depreciation', digits_compute=dp.get_precision('Account'),required=True),
        'depreciated_value': fields.float('Amount Already Depreciated', digits_compute=dp.get_precision('Account'), required=True),
        'depreciation_date': fields.date('Depreciation Date', select=1),
        'move_id': fields.many2one('account.move', 'Depreciation Entry'),
        'move_check': fields.function(_get_move_check, method=True, type='boolean', string='Posted', store=True)
    }

    def create_move(self, cr, uid, ids, context=None):
        can_close = False
        if context is None:
            context = {}
        asset_obj = self.pool.get('account.asset.asset')
        period_obj = self.pool.get('account.period')
        move_obj = self.pool.get('account.move')
        move_line_obj = self.pool.get('account.move.line')
        currency_obj = self.pool.get('res.currency')
        created_move_ids = []
        asset_ids = []
        count = 0
        for line in self.browse(cr, uid, ids, context=context):
            count += 1
            progress = 'Procesando linea ' + str(count) +' de '+ str(len(ids)) + ' con line_id = ' + str(line.id)
            _logger.info(progress)
            depreciation_date = context.get('depreciation_date') or line.depreciation_date or time.strftime('%Y-%m-%d')
            ctx = dict(context, account_period_prefer_normal=True)
            period_ids = period_obj.find(cr, uid, depreciation_date, context=ctx)
            company_currency = line.asset_id.company_id.currency_id.id
            current_currency = line.asset_id.currency_id.id
            context.update({'date': depreciation_date})
            amount = currency_obj.compute(cr, uid, current_currency, company_currency, line.amount, round=False, context=context)
            sign = (line.asset_id.category_id.journal_id.type == 'purchase' and 1) or -1
            asset_name = "/"
            reference = line.asset_id.name
            move_vals = {
                'name': asset_name,
                'date': depreciation_date,
                'ref': reference,
                'period_id': period_ids and period_ids[0] or False,
                'journal_id': line.asset_id.category_id.journal_id.id,
                }
            move_id = move_obj.create(cr, uid, move_vals, context=context)
            journal_id = line.asset_id.category_id.journal_id.id
            partner_id = line.asset_id.partner_id.id
            move_line_obj.create(cr, uid, {
                'name': asset_name,
                'ref': reference,
                'move_id': move_id,
                'account_id': line.asset_id.category_id.account_depreciation_id.id,
                'debit': 0.0,
                'credit': amount,
                'period_id': period_ids and period_ids[0] or False,
                'journal_id': journal_id,
                'partner_id': partner_id,
                'currency_id': company_currency != current_currency and  current_currency or False,
                'amount_currency': company_currency != current_currency and - sign * line.amount or 0.0,
                'date': depreciation_date,
            })
            move_line_obj.create(cr, uid, {
                'name': asset_name,
                'ref': reference,
                'move_id': move_id,
                'account_id': line.asset_id.category_id.account_expense_depreciation_id.id,
                'credit': 0.0,
                'debit': amount,
                'period_id': period_ids and period_ids[0] or False,
                'journal_id': journal_id,
                'partner_id': partner_id,
                'currency_id': company_currency != current_currency and  current_currency or False,
                'amount_currency': company_currency != current_currency and sign * line.amount or 0.0,
                'analytic_account_id': line.asset_id.category_id.account_analytic_id.id,
                'date': depreciation_date,
                'asset_id': line.asset_id.id
            })
            self.write(cr, uid, line.id, {'move_id': move_id}, context=context)
            created_move_ids.append(move_id)
            asset_ids.append(line.asset_id.id)
        # we re-evaluate the assets to determine whether we can close them
        for asset in asset_obj.browse(cr, uid, list(set(asset_ids)), context=context):
            if currency_obj.is_zero(cr, uid, asset.currency_id, asset.value_residual):
                asset.write({'state': 'close'})
        return created_move_ids

account_asset_depreciation_line()

class account_move_line(osv.osv):
    _inherit = 'account.move.line'
    _columns = {
        'asset_id': fields.many2one('account.asset.asset', 'Asset', ondelete="restrict"),
        'entry_ids': fields.one2many('account.move.line', 'asset_id', 'Entries', readonly=True, states={'draft':[('readonly',False)]}),

    }
account_move_line()

class account_asset_history(osv.osv):
    _name = 'account.asset.history'
    _description = 'Asset history'
    _columns = {
        'name': fields.char('History name', size=64, select=1),
        'user_id': fields.many2one('res.users', 'User', required=True),
        'date': fields.date('Date', required=True),
        'asset_id': fields.many2one('account.asset.asset', 'Asset', required=True),
        'method_time': fields.selection([('number','Number of Depreciations'),('end','Ending Date')], 'Time Method', required=True,
                                  help="The method to use to compute the dates and number of depreciation lines.\n"\
                                       "Number of Depreciations: Fix the number of depreciation lines and the time between 2 depreciations.\n" \
                                       "Ending Date: Choose the time between 2 depreciations and the date the depreciations won't go beyond."),
        'method_number': fields.integer('Number of Depreciations', help="The number of depreciations needed to depreciate your asset"),
        'method_period': fields.integer('Period Length', help="Time in month between two depreciations"),
        'method_end': fields.date('Ending date'),
        'note': fields.text('Note'),
    }
    _order = 'date desc'
    _defaults = {
        'date': lambda *args: time.strftime('%Y-%m-%d'),
        'user_id': lambda self, cr, uid, ctx: uid
    }

account_asset_history()

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:

