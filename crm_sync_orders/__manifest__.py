{
    'name': "Sincronización de órdenes con CRM Piédica.",
    'summary': "Sincronización de las órdenes de ventas de CRM con Odoo",
    'description': "",
    'category': 'Uncategorized',
    'version': '14.0.1',
    'depends': ['base', 'sale', 'mrp'],
    'data': [
        'security/ir.model.access.csv',
        'views/sale_views.xml',
        'views/res_partner_views.xml',
        'views/crm_status_views.xml',
        'data/crm_status_data.xml'
    ]
}
