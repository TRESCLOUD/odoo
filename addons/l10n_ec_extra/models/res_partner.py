# coding: utf-8
# Part of Odoo. See LICENSE file for full copyright and licensing details.
from odoo import models, api, fields


class ResPartner(models.Model):
    _inherit = 'res.partner'

    l10n_ec_bypass_vat_validation = fields.Boolean(
        string='Omitir validacion RUC/Ced',
        help=u'Algunas cédulas antiguas no cumplen el formato del registro civil, éste campo'
             u' permite ignorar la validación Ecuatoriana para el campo CI/RUC/Pass.'
    )

    @api.constrains('vat', 'country_id', 'l10n_latam_identification_type_id', 'l10n_ec_bypass_vat_validation')
    def check_vat(self):
        if self.sudo().env.ref('base.module_base_vat').state == 'installed':
            self = self.filtered(lambda partner: partner.country_id.code != "EC" or\
                                                 not partner.l10n_ec_bypass_vat_validation)
            return super(ResPartner, self).check_vat()
        else:
            return True
