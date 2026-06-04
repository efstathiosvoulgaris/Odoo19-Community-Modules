from odoo import http
from odoo.http import request


class DirectPrintController(http.Controller):

    @http.route('/direct_print/log', type='json', auth='user')
    def log_print(self, document_name, job_type, printer_name, status,
                  copies=1, error_message=None):
        request.env['direct.print.log'].create({
            'document_name': document_name,
            'job_type': job_type,
            'printer_name': printer_name,
            'copies': copies,
            'status': status,
            'error_message': error_message,
        })
        return {'ok': True}

    @http.route('/direct_print/routes', type='json', auth='user')
    def get_routes(self):
        routes = request.env['direct.print.route'].search_read(
            [('active', '=', True)],
            ['report_name', 'printer_name', 'copies'],
        )
        return routes

    @http.route('/direct_print/config', type='json', auth='user')
    def get_config(self):
        get = request.env['ir.config_parameter'].sudo().get_param
        return {
            'agent_url': get('direct_print.agent_url', 'http://127.0.0.1:5000'),
        }
