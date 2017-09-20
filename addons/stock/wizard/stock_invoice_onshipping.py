# -*- coding: utf-8 -*-
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

from openerp.osv import fields, osv

from openerp.tools.translate import _

class stock_invoice_onshipping(osv.osv_memory):

    def _get_journal(self, cr, uid, context=None):
        res = self._get_journal_id(cr, uid, context=context)
        if res:
            return res[0][0]
        return False

    def _get_journal_id(self, cr, uid, context=None):
        if context is None:
            context = {}

        model = context.get('active_model')
        if not model or 'stock.picking' not in model:
            return []

        model_pool = self.pool.get(model)
        journal_obj = self.pool.get('account.journal')
        res_ids = context and context.get('active_ids', [])
        vals = []
        browse_picking = model_pool.browse(cr, uid, res_ids, context=context)

        for pick in browse_picking:
            domain = [('type', 'in', ['sale', 'sale_refund', 'purchase', 'purchase_refund'])]
            if pick.move_lines:
                src_usage = pick.move_lines[0].location_id.usage
                dest_usage = pick.move_lines[0].location_dest_id.usage
                type = pick.type
                if type == 'out' and dest_usage == 'supplier':
                    journal_type = 'purchase_refund'
                elif type == 'out' and dest_usage == 'customer':
                    journal_type = 'sale'
                elif type == 'in' and src_usage == 'supplier':
                    journal_type = 'purchase'
                elif type == 'in' and src_usage == 'customer':
                    journal_type = 'sale_refund'
                else:
                    journal_type = 'sale'
                domain = [('type', '=', journal_type)]
            value = journal_obj.search(cr, uid, domain)
            #El siguiente codigo fue agregado por TRESCLOUD
            adjust_journal_accounting_stock = True
            adjust_journal_manufacture = True
            try:
                user = self.pool.get('res.users').browse(cr, uid, uid, context=context)
                obj, move_reason_id = self.pool.get('ir.model.data').get_object_reference(cr, uid, 'ecua_stock', 'move_reason_in_14')
                if journal_type == 'sale_refund':
                    journal_id = user.company_id.customer_credit_note_journal_id.id
                    if user.printer_id.journal_credit_notes_id:
                        journal_id = user.printer_id.journal_credit_notes_id.id
                    value = [journal_id] if journal_id else value
                if context.get('active_id'):
                    picking = self.pool.get(context.get('active_model')).browse(cr, uid, context.get('active_id'), context=context)
                    if picking.move_reason_id.id == move_reason_id:
                        if not user.company_id.adjust_journal_accounting_stock_id:
                            adjust_journal_accounting_stock = False
                        if not user.company_id.adjust_journal_manufacture_id:
                            adjust_journal_manufacture = False
                        if picking.manufacture:
                            value = [user.company_id.adjust_journal_manufacture_id.id]
                        else:
                            #En los ajustes de inv fisico se muestran los diarios de ajuste de inv contable y diario de ventas
                            value.append(user.company_id.adjust_journal_accounting_stock_id.id)
                            value.reverse()
            except:
                pass
            finally:
                if not adjust_journal_accounting_stock and not value[0]:
                    raise osv.except_osv(_(u'¡Error de Usuario!'),
                                         _(u'Por favor configure el diario de ajuste de inventario contable en la compañía.'))
                if not adjust_journal_manufacture and not value[0]:
                    raise osv.except_osv(_(u'¡Error de Usuario!'),
                                         _(u'Por favor configure el diario de ajuste de manufactura en la compañía.'))
            for jr_type in journal_obj.browse(cr, uid, value, context=context):
                t1 = jr_type.id,jr_type.name
                if t1 not in vals:
                    vals.append(t1)
        return vals

    _name = "stock.invoice.onshipping"
    _description = "Stock Invoice Onshipping"

    _columns = {
        'journal_id': fields.selection(_get_journal_id, 'Destination Journal',required=True),
        'group': fields.boolean("Group by partner"),
        'invoice_date': fields.date('Invoiced date'),
    }

    _defaults = {
        'journal_id' : _get_journal,
    }

    def view_init(self, cr, uid, fields_list, context=None):
        if context is None:
            context = {}
        res = super(stock_invoice_onshipping, self).view_init(cr, uid, fields_list, context=context)
        pick_obj = self.pool.get('stock.picking')
        count = 0
        active_ids = context.get('active_ids',[])
        for pick in pick_obj.browse(cr, uid, active_ids, context=context):
            if pick.invoice_state != '2binvoiced':
                count += 1
        if len(active_ids) == 1 and count:
            raise osv.except_osv(_('Warning!'), _('This picking list does not require invoicing.'))
        if len(active_ids) == count:
            raise osv.except_osv(_('Warning!'), _('None of these picking lists require invoicing.'))
        return res

    def open_invoice(self, cr, uid, ids, context=None):
        if context is None:
            context = {}
        invoice_ids = []
        data_pool = self.pool.get('ir.model.data')
        res = self.create_invoice(cr, uid, ids, context=context)
        invoice_ids += res.values()
        inv_type = context.get('inv_type', False)
        action_model = False
        action = {}
        if not invoice_ids:
            raise osv.except_osv(_('Error!'), _('Please create Invoices.'))
        if inv_type == "out_invoice":
            action_model,action_id = data_pool.get_object_reference(cr, uid, 'account', "action_invoice_tree1")
            #Este código fue modificado por TRESCLOUD
            ###################################################################################################
            if context.get('origin') == 'manual_adjustment':
                module_ids = self.pool.get('ir.module.module').search(cr, uid, [('name','=','invoiced_stock'), ('state','=','installed')], context=context)
                if module_ids:
                    obj, adjustment_journal_id = self.pool.get('ir.model.data').get_object_reference(cr, uid, 'invoiced_stock', 'journal_adjust_accounting_stock')
                    journal_id = context.get('journal_id')
                    #Para comparar convertirmos el journal al int pues llega como unicode
                    if journal_id and int(journal_id) == adjustment_journal_id:
                        action_model,action_id = data_pool.get_object_reference(cr, uid, 'invoiced_stock', "action_adjust_manual_accounting_stock")
            ####################################################################################################
        elif inv_type == "in_invoice":
            action_model,action_id = data_pool.get_object_reference(cr, uid, 'account', "action_invoice_tree2")
            #Este código fue modificado por TRESCLOUD
            ###################################################################################################
            if context.get('origin') == 'manual_adjustment':
                module_ids = self.pool.get('ir.module.module').search(cr, uid, [('name','=','invoiced_stock'), ('state','=','installed')], context=context)
                if module_ids:
                    obj, adjustment_journal_id = self.pool.get('ir.model.data').get_object_reference(cr, uid, 'invoiced_stock', 'journal_adjust_accounting_stock')
                    journal_id = context.get('journal_id')
                    #Para comparar convertirmos el journal al int pues llega como unicode
                    if journal_id and int(journal_id) == adjustment_journal_id:
                        action_model,action_id = data_pool.get_object_reference(cr, uid, 'invoiced_stock', "action_adjust_manual_accounting_stock")
            ####################################################################################################
        elif inv_type == "out_refund":
            action_model,action_id = data_pool.get_object_reference(cr, uid, 'account', "action_invoice_tree3")
        elif inv_type == "in_refund":
            action_model,action_id = data_pool.get_object_reference(cr, uid, 'account', "action_invoice_tree4")
        if action_model:
            action_pool = self.pool.get(action_model)
            action = action_pool.read(cr, uid, action_id, context=context)
            action['domain'] = "[('id','in', ["+','.join(map(str,invoice_ids))+"])]"
        return action

    def create_invoice(self, cr, uid, ids, context=None):
        if context is None:
            context = {}
        picking_pool = self.pool.get('stock.picking')
        onshipdata_obj = self.read(cr, uid, ids, ['journal_id', 'group', 'invoice_date'])
        if context.get('new_picking', False):
            onshipdata_obj['id'] = onshipdata_obj.new_picking
            onshipdata_obj[ids] = onshipdata_obj.new_picking
        context['date_inv'] = onshipdata_obj[0]['invoice_date']
        active_ids = context.get('active_ids', [])
        active_picking = picking_pool.browse(cr, uid, context.get('active_id',False), context=context)
        inv_type = picking_pool._get_invoice_type(active_picking)
        context['inv_type'] = inv_type
        if isinstance(onshipdata_obj[0]['journal_id'], tuple):
            onshipdata_obj[0]['journal_id'] = onshipdata_obj[0]['journal_id'][0]
        if active_picking.sale_id:
            force_vat = active_picking.sale_id.force_vat
        elif active_picking.purchase_id:
            force_vat = active_picking.purchase_id.force_vat
        else:
            force_vat = 'automatic'
        context.update({'force_vat': force_vat})
        res = picking_pool.action_invoice_create(cr, uid, active_ids,
              journal_id = onshipdata_obj[0]['journal_id'],
              group = onshipdata_obj[0]['group'],
              type = inv_type,
              context=context)
        return res

stock_invoice_onshipping()

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
