# Part of Odoo. See LICENSE file for full copyright and licensing details.

from enum import Flag, auto

from odoo import _, api, models
from odoo.exceptions import ValidationError


def verify_final_consumer(vat):
    return vat == '9' * 13  # final consumer is identified with 9999999999999


class PartnerIdTypeEc(Flag):
    """
    Ecuadorian partner identification type/code for ATS and SRI.
    """
    MOVE_IN = auto()
    MOVE_OUT = ~MOVE_IN
    RUC = auto()
    CEDULA = auto()
    PASSPORT = auto()
    FOREIGN = auto()
    FINAL_CONSUMER = auto()

    def __str__(self):
        return {
            self.MOVE_IN & self.RUC: '01',
            self.MOVE_IN & self.CEDULA: '02',
            self.MOVE_IN & self.PASSPORT: '03',
            self.MOVE_OUT & self.RUC: '04',
            self.MOVE_OUT & self.CEDULA: '05',
            self.MOVE_OUT & self.PASSPORT: '06',
            # only for move_out:
            self.MOVE_OUT & self.FINAL_CONSUMER: '07',
            self.MOVE_OUT & self.FOREIGN: '08'
        }[self]

    @classmethod
    def get_ats_code_for_partner(cls, partner, move_type):
        """
        Returns ID code for move and partner based on subset of Table 2 of SRI's ATS specification
        """
        move_flag = cls.MOVE_IN if move_type.startswith('in_') else cls.MOVE_OUT
        partner_flag = partner._l10n_ec_get_identification_type()
        if partner_flag == cls.FOREIGN:
            partner_flag = cls.PASSPORT  # ATS does not distinguish between foreign & passport
        return move_flag & partner_flag


class ResPartner(models.Model):

    _inherit = "res.partner"

    @api.constrains("vat", "country_id", "l10n_latam_identification_type_id")
    def check_vat(self):
        it_ruc = self.env.ref("l10n_ec.ec_ruc", False)
        it_dni = self.env.ref("l10n_ec.ec_dni", False)
        ecuadorian_partners = self.filtered(
            lambda x: x.country_id == self.env.ref("base.ec")
        )
        for partner in ecuadorian_partners:
            if partner.vat:
                if partner.l10n_latam_identification_type_id.id in (
                    it_ruc.id,
                    it_dni.id,
                ):
                    if partner.l10n_latam_identification_type_id.id == it_dni.id and len(partner.vat) != 10:
                        raise ValidationError(_('If your identification type is %s, it must be 10 digits')
                                              % it_dni.display_name)
                    if partner.l10n_latam_identification_type_id.id == it_ruc.id and len(partner.vat) != 13:
                        raise ValidationError(_('If your identification type is %s, it must be 13 digits')
                                              % it_ruc.display_name)
                    if verify_final_consumer(partner.vat):  # final consumer is represented by a vat of 9999999999999
                        valid = True
                    else:
                        valid = self.is_valid_ruc_ec(partner.vat)
                    if not valid:
                        error_message = ""
                        if partner.l10n_latam_identification_type_id.id == it_dni.id:
                            error_message = _("VAT %s is not valid for an Ecuadorian DNI, "
                                              "it must be like this form 1234567897") % partner.vat
                        if partner.l10n_latam_identification_type_id.id == it_ruc.id:
                            error_message = _("VAT %s is not valid for an Ecuadorian company, "
                                              "it must be like this form 1234567897001") % partner.vat
                        raise ValidationError(error_message)
        return super(ResPartner, self - ecuadorian_partners).check_vat()

    def _l10n_ec_get_identification_type(self):
        """Maps Odoo identification types to Ecuadorian ones.
        Useful for document type domains, electronic documents, ats, others.
        """
        self.ensure_one()

        def id_type_in(*args):
            return any([self.l10n_latam_identification_type_id == self.env.ref(arg) for arg in args])

        if id_type_in('l10n_ec.ec_dni'):
            return PartnerIdTypeEc.CEDULA  # DNI
        elif id_type_in('l10n_ec.ec_ruc'):
            return PartnerIdTypeEc.RUC  # RUC
        elif id_type_in('l10n_latam_base.it_pass'):
            return PartnerIdTypeEc.PASSPORT  # Pasaporte
        elif id_type_in('l10n_latam_base.it_fid', 'l10n_latam_base.it_vat') \
                or self.l10n_latam_identification_type_id.country_id != self.env.ref('base.ec'):
            return PartnerIdTypeEc.FOREIGN  # Identificacion del exterior
