import datetime

from odoo import models, fields, api
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    branch_id = fields.Many2one('res.partner', string='Sucursal')
    estatus_crm = fields.Many2one('crm.status', string='Estatus CRM', readonly=True)
    folio_pedido = fields.Char('Folio del pedido', readonly=True)
    crm_status_history = fields.One2many('crm.status.history', 'sale_order', string='Historial de estatus', readonly=True)


    def create_crm_order(self, args):
        args_status = self.validate_create_data(args)

        if args_status['status'] == 'error':
            return args_status

        data = args_status['content']
        order_line = data.pop('order_line')
        sale_order = self.with_context(lang='es_MX').create(data)
        order_line_status = sale_order.create_crm_order_line(order_line)

        if order_line_status['status'] == 'error':
            return order_line_status

        try:
            sale_order.action_confirm()
        except UserError as e:
            return  {
                'status': 'error',
                'message': e.args[0]
            }


        sale_order.create_estatus_crm()

        return {
            'status': 'success',
            'content': {
                'sale_order': sale_order.id
            }
        }



    def create_crm_order_line(self, products):
        self.ensure_one()
        sale_order_line_obj = self.env['sale.order.line']
        product_product_obj = self.env['product.product']

        for product_data in products:
            product = product_product_obj.search([('id', '=', product_data['id'])])

            line_data = {
                'name': product.name,
                'product_id': product.id,
                'product_uom': product.uom_id.id if product.uom_id else False,
                'order_id': self.id,
                'product_uom_qty': product_data['quantity']
            }

            sale_order_line_obj.create(line_data)

        return {
            'status': 'success'
        }


    def create_estatus_crm(self):
        self.ensure_one()
        self.write({
            'crm_status_history': [(0, 0, {
                'sale_order': self.id,
                'status': self.estatus_crm.id,
                'date': datetime.datetime.now()
            })]
        })


    def update_estatus_crm(self, args):
        self.ensure_one()
        args_status = self.validate_update_data(args)

        if args_status['status'] == 'error':
            return args_status

        data = args_status['content']
        self.write({'estatus_crm': self.env['crm.status'].search([('code', '=', data['estatus_crm'])])[0].id})
        self.create_estatus_crm()

        if data['estatus_crm'] == 4:
            self.update_manufacturing_order(data['products'])

        if data['estatus_crm'] == 6:
            self.update_delivery_order()

        return {
            'status': 'success'
        }


    def update_manufacturing_order(self, products):
        self.ensure_one()

        context = {
            'active_id': self.id,
            'active_ids': [self.id],
            'active_model': 'sale.order',
            'allowed_company_ids': [self.company_id.id]
        }

        mrp_orders = self.env['mrp.production'].with_context(context).search([('origin', '=', self.name)])
        product_product_obj = self.env['product.product']

        for mrp_order in mrp_orders:
            components_data = []

            for product in products:
                if product['id'] == mrp_order.product_id.id:
                    for component_data in product['components']:
                        component = product_product_obj.search([('id', '=', component_data['id'])])

                        components_data.append((0, 0, {
                            'name': component.name,
                            'product_id': component.id,
                            'product_uom': component.uom_id.id if component.uom_id else False,
                            'raw_material_production_id': mrp_order.id,
                            'product_uom_qty': component_data['quantity'],
                            'quantity_done': component_data['quantity'],
                            'company_id': self.company_id.id,
                            'location_id': mrp_order.location_src_id.id,
                            'location_dest_id': mrp_order.production_location_id.id
                        }))

            if not components_data:
                not_found_product = product_product_obj.search([('id', '=', product['id'])])

                return {
                    'status': 'error',
                    'message': 'No se encontró el producto %s en la orden %s' % (not_found_product.name, mrp_order.name)
                }

            mrp_order.write({'move_raw_ids': components_data})
            mrp_order.action_confirm()
            mrp_order.write({'qty_producing': mrp_order.product_qty})
            mrp_order.button_mark_done()


    def update_delivery_order(self):
        self.ensure_one()

        context = {
            'active_id': self.id,
            'active_ids': [self.id],
            'active_model': 'sale.order',
            'allowed_company_ids': [self.company_id.id]
        }

        delivery_orders = self.env['stock.picking'].with_context(context).search([('origin', '=', self.name)])

        for delivery_order in delivery_orders:
            for line in delivery_order.move_line_ids_without_package:
                line.write({'qty_done': line.product_uom_qty})

            try:
                delivery_order.p_button_validate()
            except UserError as e:
                return  {
                    'status': 'error',
                    'message': e.args[0]
                }



    def validate_create_data(self, args):
        product_product_obj = self.env['product.product'].sudo()

        customer = args.get('customer', None) # partner_id - Cliente
        branch = args.get('branch', None) # branch - Sucursal
        invoice_address = args.get('invoice_address', None) # partner_invoice_id - Dirección de factura
        delivery_address = args.get('delivery_address', None) # partner_shipping_id - Dirección de entrega
        pricelist = args.get('pricelist', None) # pricelist_id - Lista de precios
        payment_terms = args.get('payment_terms', None) # payment_term_id - Términos de pago
        tipo_pedido = args.get('tipo_pedido', None) # x_studio_selection_field_waqzv - Tipo de pedido
        estatus_crm = args.get('estatus_crm', None) # estatus_crm - Estatus CRM
        folio_pedido = args.get('folio_pedido', None) # folio_pedido - Folio pedido
        order_line = args.get('order_line', None) # order_line - Línea de la orden
        salesperson = args.get('salesperson', None) # user_id - Vendedor
        sales_team = args.get('sales_team', None) # team_id - Equipo de ventas
        company = args.get('company', None) # company_id - Empresa
        online_signature = args.get('online_signature', None) # require_signature - Firma en línea
        shipping_policy = args.get('shipping_policy', None) # picking_policy - Política de entrega

        missing_args = []

        # Comprueba que se hayan suplido todos los argumentos
        if not customer:
            missing_args.append('customer')
        else:
            if not isinstance(customer, int):
                return {
                    'status': 'error',
                    'message': 'El parámetro customer debe ser un valor numérico. Valor introducido: %s' % str(customer)
                }

            customer_record = self.env['res.partner'].search([('id', '=', customer)])

            if not customer_record:
                return {
                    'status': 'error',
                    'message': 'No se encontró el cliente con el id %s' % customer
                }

        if not branch:
            missing_args.append('branch')
        else:
            if not isinstance(branch, int):
                return {
                    'status': 'error',
                    'message': 'El parámetro branch debe ser un valor numérico. Valor introducido: %s' % str(customer)
                }

            branch_record = self.env['res.partner'].search([('id', '=', branch)])

            if not branch_record:
                return {
                    'status': 'error',
                    'message': 'No se encontró la sucursal con el id %s' % branch
                }

        if not invoice_address:
            missing_args.append('invoice_address')
        else:
            if not isinstance(invoice_address, int):
                return {
                    'status': 'error',
                    'message': 'El parámetro invoice_address debe ser un valor numérico. Valor introducido: %s' % str(invoice_address)
                }

            invoice_address_record = self.env['res.partner'].search([('id', '=', customer)])

            if not invoice_address_record:
                return {
                    'status': 'error',
                    'message': 'No se encontró la dirección de facturación con el id %s' % invoice_address_record
                }

        if not delivery_address:
            missing_args.append('delivery_address')
        else:
            if not isinstance(delivery_address, int):
                return {
                    'status': 'error',
                    'message': 'El parámetro delivery_address debe ser un valor numérico. Valor introducido: %s' % str(delivery_address)
                }

            delivery_address_record = self.env['res.partner'].search([('id', '=', delivery_address)])

            if not delivery_address_record:
                return {
                    'status': 'error',
                    'message': 'No se encontró la dirección de facturación con el id %s' % invoice_address_record
                }


        if not pricelist:
            missing_args.append('pricelist')
        else:
            if not isinstance(pricelist, int):
                return {
                    'status': 'error',
                    'message': 'El parámetro pricelist debe ser un valor numérico. Valor introducido: %s' % str(pricelist)
                }
            pricelist_record = self.env['product.pricelist'].search([('id', '=', pricelist)])

            if not pricelist_record:
                return {
                    'status': 'error',
                    'message': 'No se encontró la lista de precios con el id %s' % pricelist
                }

        if not payment_terms:
            missing_args.append('payment_terms')
        else:
            if not isinstance(payment_terms, int):
                return {
                    'status': 'error',
                    'message': 'El parámetro payment_terms debe ser un valor numérico. Valor introducido: %s' % str(payment_terms)
                }

            payment_terms_record = self.env['account.payment.term'].search([('id', '=', payment_terms)])

            if not payment_terms_record:
                return {
                    'status': 'error',
                    'message': 'No se encontró el término de pago con el id %s' % payment_terms
                }

        if not tipo_pedido:
            missing_args.append('tipo_pedido')
        else:
            if not isinstance(tipo_pedido, str):
                return {
                    'status': 'error',
                    'message': 'El parámetro tipo_pedido debe ser un string. Valor introducido: %s' % str(tipo_pedido)
                }

            tipo_pedido_val = dict(self._fields['x_studio_selection_field_waqzv'].selection).get(tipo_pedido, None)

            if not tipo_pedido_val:
                return {
                    'status': 'error',
                    'message': 'No se encontró el valor %s para el tipo de pedido' % tipo_pedido
                }


        if not estatus_crm:
            missing_args.append('estatus_crm')
        else:
            if not isinstance(estatus_crm, int):
                return {
                    'status': 'error',
                    'message': 'El parámetro estatus_crm debe ser un valor numérico. Valor introducido: %s' % str(estatus_crm)
                }

            estatus_crm_record = self.env['crm.status'].search([('id', '=', estatus_crm)])

            if not estatus_crm_record:
                return {
                    'status': 'error',
                    'message': 'No se encontró el estatus con el id %s' % estatus_crm
                }


        if not folio_pedido:
            missing_args.append('folio_pedido')
        else:
            if not isinstance(folio_pedido, str):
                return {
                    'status': 'error',
                    'message': 'El parámetro folio_pedido debe ser un string. Valor introducido: %s' % str(folio_pedido)
                }

        if not order_line:
            missing_args.append('order_line')
        else:
            if not isinstance(order_line, list):
                return {
                    'status': 'error',
                    'message': 'El parámetro order_line debe ser un array. Valor introducido: %s' % str(order_line)
                }

        if not salesperson:
            missing_args.append('salesperson')
        else:
            if not isinstance(salesperson, str):
                return {
                    'status': 'error',
                    'message': 'El parámetro salesperson debe ser un string. Valor introducido: %s' % str(salesperson)
                }

            salesperson_record = self.env['res.users'].search([('email', '=', salesperson)])

            if not salesperson_record:
                return {
                    'status': 'error',
                    'message': 'No se encontró el vendedor con el email %s' % salesperson
                }
            else:
                salesperson = salesperson_record.id

        if not sales_team:
            missing_args.append('sales_team')
        else:
            if not isinstance(sales_team, int):
                return {
                    'status': 'error',
                    'message': 'El parámetro sales_team debe ser un valor numérico. Valor introducido: %s' % str(sales_team)
                }

            sales_team_record = self.env['crm.team'].search([('id', '=', sales_team)])

            if not sales_team_record:
                return {
                    'status': 'error',
                    'message': 'No se encontró el equipo de ventas con el id %s' % sales_team
                }

        if not company:
            missing_args.append('company')
        else:
            if not isinstance(company, int):
                return {
                    'status': 'error',
                    'message': 'El parámetro company debe ser un valor numérico. Valor introducido: %s' % str(company)
                }

            company_record = self.env['res.company'].search([('id', '=', company)])

            if not company_record:
                return {
                    'status': 'error',
                    'message': 'No se encontró la compañía con el id %s' % company
                }

        if online_signature == None:
            missing_args.append('online_signature')
        else:
            if not isinstance(online_signature, bool):
                return {
                    'status': 'error',
                    'message': 'El parámetro online_signature debe ser un valor booleano. Valor introducido: %s' % str(online_signature)
                }

        if not shipping_policy:
            missing_args.append('shipping_policy')
        else:
            if not isinstance(shipping_policy, str):
                return {
                    'status': 'error',
                    'message': 'El parámetro shipping_policy debe ser un string. Valor introducido: %s' % str(shipping_policy)
                }

            shipping_policy_val = dict(self._fields['picking_policy'].selection).get(shipping_policy, None)

            if not shipping_policy_val:
                return {
                    'status': 'error',
                    'message': 'No se encontró el valor %s para shipping_policy' % shipping_policy
                }


        if missing_args:
            return {
                'status': 'error',
                'message': 'Faltan los siguientes argumentos: %s' % ', '.join(missing_args)
            }


        if len(order_line) == 0:
            return {
                'status': 'error',
                'message': 'La linea de la orden no tiene ningun producto asignado'
            }

        # Comprueba que los productos existan en Odoo
        for product_data in order_line:
            if not isinstance(product_data['id'], int):
                return {
                    'status': 'error',
                    'message': 'El id del producto debe ser un valor numérico. Valor introducido: %s' % str(product_data['id'])
                }

            if not isinstance(product_data['quantity'], int):
                return {
                    'status': 'error',
                    'message': 'La cantidad del producto debe ser un valor numérico. Valor introducido: %s' % str(product_data['quantity'])
                }

            product = product_product_obj.search([('id', '=', product_data['id'])])

            if not product:
                return {
                    'status': 'error',
                    'message': 'No se ha encontrado el producto con el id %d' % product_data['id']
                }


        return {
            'status': 'success',
            'content': {
                'partner_id': customer,
                'branch_id': branch,
                'partner_invoice_id': invoice_address,
                'partner_shipping_id': delivery_address,
                'pricelist_id': pricelist,
                'payment_term_id': payment_terms,
                'x_studio_selection_field_waqzv': tipo_pedido,
                'estatus_crm': estatus_crm,
                'folio_pedido': folio_pedido,
                'order_line': order_line,
                'user_id': salesperson,
                'team_id': sales_team,
                'company_id': company,
                'require_signature': online_signature,
                'picking_policy': shipping_policy
            }
        }


    def validate_update_data(self, args):
        product_product_obj = self.env['product.product'].sudo()
        missing_args = []
        data = {}

        estatus_crm = args.get('estatus_crm', None)

        # Comprueba que se hayan suplido todos los argumentos
        if not estatus_crm:
            missing_args.append('estatus_crm')
        else:
            if not isinstance(estatus_crm, int):
                return {
                    'status': 'error',
                    'message': 'El parámetro estatus_crm debe ser un valor numérico'
                }

            estatus_crm_record = self.env['crm.status'].search([('id', '=', estatus_crm)])

            if not estatus_crm_record:
                return {
                    'status': 'error',
                    'message': 'No se encontró el estatus con el id %s' % estatus_crm
                }

            data.update({'estatus_crm': estatus_crm})

        if estatus_crm == 4:
            products = args.get('products', None)

            if not products:
                missing_args.append('products')
            else:
                if not isinstance(products, list):
                    return {
                        'status': 'error',
                        'message': 'El parámetro products debe ser un array'
                    }

                data.update({'products': products})


        if estatus_crm == 4:
            if len(products) == 0:
                return {
                    'status': 'error',
                    'message': 'No se agregaron productos'
                }

            # Comprueba que los productos existan en Odoo
            for product_data in products:
                if not product_data.get('id', None):
                    missing_args.append('products.id')
                    break
                else:
                    if not isinstance(product_data['id'], int):
                        return {
                            'status': 'error',
                            'message': 'El id del producto debe ser un valor numérico. Valor introducido: %s' % str(product_data['id'])
                        }

                    product = product_product_obj.search([('id', '=', product_data['id'])])

                    if not product:
                        return {
                            'status': 'error',
                            'message': 'No se ha encontrado el producto con el id %d' % product_data['id']
                        }

                if not product_data.get('components', None):
                    missing_args.append('products.components')
                    break
                else:
                    if not isinstance(product_data['components'], list):
                        return {
                            'status': 'error',
                            'message': 'El parámetro products.components debe ser un array. Valor introducido: %s' % str(order_line)
                        }

                for component_data in product_data['components']:
                    if not component_data.get('id', None):
                        missing_args.append('products.components.id')
                        break
                    else:
                        if not isinstance(component_data['id'], int):
                            return {
                                'status': 'error',
                                'message': 'El id del componente debe ser un valor numérico. Valor introducido: %s' % str(component_data['id'])
                            }

                        component = product_product_obj.search([('id', '=', component_data['id'])])

                        if not component:
                            return {
                                'status': 'error',
                                'message': 'No se ha encontrado el componente con el id %d' % product_data['id']
                            }

                    if not component_data.get('quantity', None):
                        missing_args.append('products.components.quantity')
                        break
                    else:
                        if not isinstance(component_data['quantity'], int):
                            return {
                                'status': 'error',
                                'message': 'La cantidad del componente debe ser un valor numérico. Valor introducido: %s' % str(component_data['quantity'])
                            }


                if missing_args:
                    break


        if missing_args:
            return {
                'status': 'error',
                'message': 'Faltan los siguientes argumentos: %s' % ', '.join(missing_args)
            }


        return {
            'status': 'success',
            'content': data
        }
