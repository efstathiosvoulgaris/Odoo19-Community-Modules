from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    service_contract_count = fields.Integer(compute='_compute_service_contract_count')

    def _compute_service_contract_count(self):
        groups = self.env['service.contract']._read_group(
            [('partner_id', 'child_of', self.commercial_partner_id.ids)],
            ['partner_id'], ['__count'])
        counts = {}
        for partner, count in groups:
            commercial = partner.commercial_partner_id
            counts[commercial.id] = counts.get(commercial.id, 0) + count
        for partner in self:
            partner.service_contract_count = counts.get(partner.commercial_partner_id.id, 0)

    def action_view_service_contracts(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'maintenance_contracts.action_service_contract')
        action['domain'] = [('partner_id', 'child_of', self.commercial_partner_id.id)]
        action['context'] = {'default_partner_id': self.commercial_partner_id.id}
        return action
