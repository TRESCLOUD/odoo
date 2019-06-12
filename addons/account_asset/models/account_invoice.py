# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from datetime import datetime
from dateutil.relativedelta import relativedelta
from odoo import api, fields, models
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT as DF

import odoo.addons.decimal_precision as dp


class AccountInvoice(models.Model):
    _inherit = 'account.invoice'

    @api.model
    def _refund_cleanup_lines(self, lines):
        result = super(AccountInvoice, self)._refund_cleanup_lines(lines)
        for i, line in enumerate(lines):
            for name, field in line._fields.items():
                if name == 'asset_category_id':
                    result[i][2][name] = False
                    break
        return result

    @api.multi
    def action_cancel(self):
        res = super(AccountInvoice, self).action_cancel()
        self.env['account.asset.asset'].sudo().search([('invoice_id', 'in', self.ids)]).write({'active': False})
        return res

    # INICIO DEL CODIGO AGREGADO POR TRESCLOUD
    @api.model
    def _bypass_asset_create(self):
        """
        Bypass para impedir si se desea la creacion de activos al confirmar
        la factura
        """
        return False
    # FIN DEL CODIGO AGREGADO POR TRESCLOUD

    @api.multi
    def action_move_create(self):
        result = super(AccountInvoice, self).action_move_create()
        for inv in self:
            context = dict(self.env.context)
            # Within the context of an invoice,
            # this default value is for the type of the invoice, not the type of the asset.
            # This has to be cleaned from the context before creating the asset,
            # otherwise it tries to create the asset with the type of the invoice.
            context.pop('default_type', None)
            # INICIO DEL CODIGO MODIFICADO POR TRESCLOUD
            if not self._bypass_asset_create():
                # FIN DEL CODIGO MODIFICADO POR TRESCLOUD
                inv.invoice_line_ids.with_context(context).asset_create()
        return result


class AccountInvoiceLine(models.Model):
    _inherit = 'account.invoice.line'

    asset_category_id = fields.Many2one('account.asset.category', string='Asset Category')
    asset_start_date = fields.Date(string='Asset Start Date', compute='_get_asset_date', readonly=True, store=True)
    asset_end_date = fields.Date(string='Asset End Date', compute='_get_asset_date', readonly=True, store=True)
    asset_mrr = fields.Float(string='Monthly Recurring Revenue', compute='_get_asset_date', readonly=True, digits=dp.get_precision('Account'), store=True)

    @api.one
    @api.depends('asset_category_id', 'invoice_id.date_invoice')
    def _get_asset_date(self):
        self.asset_mrr = 0
        self.asset_start_date = False
        self.asset_end_date = False
        cat = self.asset_category_id
        if cat:
            months = cat.method_number * cat.method_period
            if self.invoice_id.type in ['out_invoice', 'out_refund']:
                self.asset_mrr = self.price_subtotal_signed / months
            if self.invoice_id.date_invoice:
                start_date = datetime.strptime(self.invoice_id.date_invoice, DF).replace(day=1)
                end_date = (start_date + relativedelta(months=months, days=-1))
                self.asset_start_date = start_date.strftime(DF)
                self.asset_end_date = end_date.strftime(DF)

    @api.one
    def asset_create(self):
        if self.asset_category_id:
            # INICIO DEL CODIGO MODIFICADO POR TRESCLOUD
            vals = self._prepare_asset_vals()
            # FIN DEL CODIGO MODIFICADO POR TRESCLOUD
            changed_vals = self.env['account.asset.asset'].onchange_category_id_values(vals['category_id'])
            vals.update(changed_vals['value'])
            asset = self.env['account.asset.asset'].create(vals)
            if self.asset_category_id.open_asset:
                asset.validate()
        return True

    # INICIO DEL CODIGO AGREGADO POR TRESCLOUD
    @api.multi
    def _prepare_asset_vals(self):
        """
        Hooks para futuras modificaciones y dar la posibilidad de modificar
        los valores de los campos al crear el activo
        """
        self.ensure_one()
        return {
            'name': self.name,
            'code': self.invoice_id.number or False,
            'category_id': self.asset_category_id.id,
            'value': self.price_subtotal_signed,
            'partner_id': self.invoice_id.partner_id.id,
            'company_id': self.invoice_id.company_id.id,
            'currency_id': self.invoice_id.company_currency_id.id,
            'date': self.invoice_id.date_invoice,
            'invoice_id': self.invoice_id.id,
        }
    # FIN DEL CODIGO AGREGADO POR TRESCLOUD

    @api.onchange('asset_category_id')
    def onchange_asset_category_id(self):
        if self.invoice_id.type == 'out_invoice' and self.asset_category_id:
            self.account_id = self.asset_category_id.account_asset_id.id
        elif self.invoice_id.type == 'in_invoice' and self.asset_category_id:
            self.account_id = self.asset_category_id.account_asset_id.id

    @api.onchange('uom_id')
    def _onchange_uom_id(self):
        result = super(AccountInvoiceLine, self)._onchange_uom_id()
        self.onchange_asset_category_id()
        return result

    @api.onchange('product_id')
    def _onchange_product_id(self):
        vals = super(AccountInvoiceLine, self)._onchange_product_id()
        if self.product_id:
            if self.invoice_id.type == 'out_invoice':
                self.asset_category_id = self.product_id.product_tmpl_id.deferred_revenue_category_id
            elif self.invoice_id.type == 'in_invoice':
                self.asset_category_id = self.product_id.product_tmpl_id.asset_category_id
        return vals

    def _set_additional_fields(self, invoice):
        if not self.asset_category_id:
            if invoice.type == 'out_invoice':
                self.asset_category_id = self.product_id.product_tmpl_id.deferred_revenue_category_id.id
            elif invoice.type == 'in_invoice':
                self.asset_category_id = self.product_id.product_tmpl_id.asset_category_id.id
            self.onchange_asset_category_id()
        super(AccountInvoiceLine, self)._set_additional_fields(invoice)
