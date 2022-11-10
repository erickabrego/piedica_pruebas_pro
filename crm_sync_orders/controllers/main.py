from odoo import http, fields
from odoo.http import Controller, request, route, Response
from odoo.exceptions import UserError


class MainController(Controller):
    @route('/sync-orders', type='json', auth='none')
    def create_orders(self, **kwargs):
        sale_order_obj = request.env['sale.order'].sudo()
        result = sale_order_obj.create_crm_order(kwargs)

        return result


    @route('/sync-orders/<id>', type='json', auth='none')
    def edit_orders(self, id, **kwargs):
        if not str(id).isnumeric():
            return {
                'status': 'error',
                'message': 'El id de la orden de venta debe ser un valor numérico. Valor introducido: %s' % str(id)
            }

        order = request.env['sale.order'].sudo().search([('id', '=', id)])

        if not order:
            return {
                'status': 'error',
                'message': 'No se encontró la orden de venta con el id %d' % id
            }

        result = order.update_estatus_crm(kwargs)

        return result
