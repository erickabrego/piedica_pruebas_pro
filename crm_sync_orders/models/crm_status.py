from odoo import models, fields, api

class CRMStatus(models.Model):
    _name = 'crm.status'
    _description = 'Estatus de CRM'
    _order = 'id desc'


    code = fields.Integer('Clave')
    name = fields.Char('Nombre')
