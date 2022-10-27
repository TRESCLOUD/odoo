# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models, _, api
from stdnum.ec import ci, ruc
from odoo.exceptions import ValidationError


class ResPartner(models.Model):
    _inherit = 'res.partner'

    def check_vat_ec(self, vat):
        return self.model_check_vat_ec(vat, self.l10n_latam_identification_type_id.id)

    @api.model
    def model_check_vat_ec(self, vat, l10n_latam_identification_type_id):
        vat_type = self.env['l10n_latam.identification.type'].browse(l10n_latam_identification_type_id)
        if not vat_type:
            raise ValidationError(_('Identification type is required in order to validate VAT'))
        if vat_type.is_vat:
            ruc_vat_type = self.env.ref('l10n_ec.ec_ruc')
            ced_vat_type = self.env.ref('l10n_ec.ec_dni')
            if vat_type in (ruc_vat_type, ced_vat_type):
                # temporal fix as stdnum.ec is allowing old format with a dash in between the number
                if not vat.isnumeric():
                    raise ValidationError(_('Ecuadorian VAT number must contain only numeric characters'))
            if vat_type == ced_vat_type:
                return ci.is_valid(vat)
            elif vat_type == ruc_vat_type and vat != '9999999999999':
                return ruc.is_valid(vat)
        return True

    def _get_complete_address(self):
        self.ensure_one()
        partner_id = self
        address = ""
        if partner_id.street:
            address += partner_id.street + ", "
        if partner_id.street2:
            address += partner_id.street2 + ", "
        if partner_id.city:
            address += partner_id.city + ", "
        if partner_id.state_id:
            address += partner_id.state_id.name + ", "
        if partner_id.zip:
            address += "(" + partner_id.zip + ") "
        if partner_id.country_id:
            address += partner_id.country_id.name
        return address
