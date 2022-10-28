# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models, api
from odoo.addons.l10n_ec.models.res_partner import verify_final_consumer

_DOCUMENTS_MAPPING = {
    "01": [
        'ec_dt_01',
        'ec_dt_02',
        'ec_dt_04',
        'ec_dt_05',
        'ec_dt_08',
        'ec_dt_09',
        'ec_dt_11',
        'ec_dt_12',
        'ec_dt_20',
        'ec_dt_21',
        'ec_dt_41',
        'ec_dt_42',
        'ec_dt_43',
        'ec_dt_45',
        'ec_dt_47',
        'ec_dt_48'
    ],
    "02": [
        'ec_dt_03',
        'ec_dt_04',
        'ec_dt_05',
        'ec_dt_09',
        'ec_dt_19',
        'ec_dt_41',
        'ec_dt_294',
        'ec_dt_344'
    ],
    "03": [
        'ec_dt_03',
        'ec_dt_04',
        'ec_dt_05',
        'ec_dt_09',
        'ec_dt_15',
        'ec_dt_19',
        'ec_dt_41',
        'ec_dt_45',
        'ec_dt_294',
        'ec_dt_344'
    ],
    "04": [
        'ec_dt_01',
        'ec_dt_04',
        'ec_dt_05',
        'ec_dt_41',
        'ec_dt_44',
        'ec_dt_47',
        'ec_dt_48',
        'ec_dt_49',
        'ec_dt_50',
        'ec_dt_51',
        'ec_dt_52',
        'ec_dt_370',
        'ec_dt_371',
        'ec_dt_372',
        'ec_dt_373'
    ],
    "05": [
        'ec_dt_01',
        'ec_dt_04',
        'ec_dt_05',
        'ec_dt_41',
        'ec_dt_44',
        'ec_dt_47',
        'ec_dt_48',
        'ec_dt_370',
        'ec_dt_371',
        'ec_dt_372',
        'ec_dt_373'
    ],
    "06": [
        'ec_dt_01',
        'ec_dt_04',
        'ec_dt_05',
        'ec_dt_41',
        'ec_dt_44',
        'ec_dt_47',
        'ec_dt_48',
        'ec_dt_370',
        'ec_dt_371',
        'ec_dt_372',
        'ec_dt_373'
    ],
    "07": [
        'ec_dt_01',
        'ec_dt_04',
        'ec_dt_05',
    ],
    "09": [
        'ec_dt_01',
        'ec_dt_04',
        'ec_dt_05',
        'ec_dt_15',
        'ec_dt_16',
        'ec_dt_41',
        'ec_dt_47',
        'ec_dt_48',
    ],
    "20": [
        'ec_dt_01',
        'ec_dt_04',
        'ec_dt_05',
        'ec_dt_15',
        'ec_dt_16',
        'ec_dt_41',
        'ec_dt_47',
        'ec_dt_48'
    ],
    "21": [
        'ec_dt_01',
        'ec_dt_04',
        'ec_dt_05',
        'ec_dt_15',
        'ec_dt_16',
        'ec_dt_41',
        'ec_dt_47',
        'ec_dt_48'
    ],
}


class AccountMove(models.Model):
    _inherit = "account.move"

    l10n_ec_sri_payment_id = fields.Many2one(
        comodel_name="l10n_ec.sri.payment",
        string="Payment Method (SRI)",
    )

    def _get_l10n_ec_ats_identification_type(self):
        # Helps filter out document types based on subset of Table 2 of SRI's ATS specification
        self.ensure_one()
        ec_ruc = self.env.ref("l10n_ec.ec_ruc", False)
        ec_dni = self.env.ref("l10n_ec.ec_dni", False)
        ec_passport = self.env.ref("l10n_ec.ec_passport", False)
        it_pass = self.env.ref("l10n_latam_base.it_pass", False) # Passport
        it_vat = self.env.ref("l10n_latam_base.it_vat", False)
        it_fid = self.env.ref("l10n_latam_base.it_fid", False) # Foreign ID
        # find partner identification type
        is_ruc = self.partner_id.l10n_latam_identification_type_id == ec_ruc
        is_dni = self.partner_id.l10n_latam_identification_type_id == ec_dni
        #TODO Joss, for "is_foreign", are we sure it_vat is intended to be a foreigner? it will affect the edi module in sister method _get_l10n_ec_edi_identification_type()
        is_foreign = self.partner_id.l10n_latam_identification_type_id in [ec_passport, it_pass, it_vat, it_fid]
        # map identification code considering sale or purchase as per table 2 of ATS
        identification_code = False
        if self.move_type in ("in_invoice", "in_refund"):
            if is_ruc: # includes final consumer
                identification_code = "01"
            elif is_dni:
                identification_code = "02"
            elif is_foreign: 
                identification_code = "03"
        elif self.move_type in ("out_invoice", "out_refund"):
            if is_ruc: # includes final consumer
                identification_code = "04"
            elif is_dni:
                identification_code = "05"
            elif is_foreign: #passport or foreign ID
                identification_code = "06"
        return identification_code

    _get_l10n_ec_identification_type = _get_l10n_ec_ats_identification_type #For backward compatibility, remove in master

    @api.model
    def _get_l10n_ec_documents_allowed(self, identification_code):
        documents_allowed = self.env['l10n_latam.document.type']
        for document_ref in _DOCUMENTS_MAPPING.get(identification_code, []):
            document_allowed = self.env.ref('l10n_ec.%s' % document_ref, False)
            if document_allowed:
                documents_allowed |= document_allowed
        return documents_allowed

    def _get_l10n_latam_documents_domain(self):
        self.ensure_one()
        domain = super(AccountMove, self)._get_l10n_latam_documents_domain()
        if self.country_code == 'EC' and self.journal_id.l10n_latam_use_documents:
            if self.debit_origin_id: # show/hide the debit note document type
                domain.extend([("internal_type", "=", 'debit_note')])
            elif self.move_type in ('out_invoice', 'in_invoice'):
                domain.extend([("internal_type", "=", 'invoice')])            
            allowed_documents = self._get_l10n_ec_documents_allowed(self._get_l10n_ec_ats_identification_type())
            if allowed_documents: #TODO Joss, Andres suggest to remove the condition, so that if no ID matches then no document is available
                domain.extend([("id", "in", allowed_documents.ids)])
        return domain

    def _get_ec_formatted_sequence(self, number=0):
        return "%s %s-%s-%09d" % (
            self.l10n_latam_document_type_id.doc_code_prefix,
            self.journal_id.l10n_ec_entity,
            self.journal_id.l10n_ec_emission,
            number,
        )

    def _get_starting_sequence(self):
        """If use documents then will create a new starting sequence using the document type code prefix and the
        journal document number with a 8 padding number"""
        if (
            self.journal_id.l10n_latam_use_documents
            and self.company_id.country_id.code == "EC"
        ):
            if self.l10n_latam_document_type_id:
                return self._get_ec_formatted_sequence()
        return super()._get_starting_sequence()

    def _get_last_sequence_domain(self, relaxed=False):
        where_string, param = super(AccountMove, self)._get_last_sequence_domain(relaxed)
        if self.country_code == "EC" and self.l10n_latam_use_documents:
            internal_type = self.l10n_latam_document_type_id.internal_type
            document_types = self.env['l10n_latam.document.type'].search([
                ('internal_type', '=', internal_type),
                ('country_id.code', '=', 'EC'),
            ])
            if document_types:
                where_string += """
                AND l10n_latam_document_type_id in %(l10n_latam_document_type_id)s
                """
                param["l10n_latam_document_type_id"] = tuple(document_types.ids)
        return where_string, param
