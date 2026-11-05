import re
from datetime import datetime, time

import pytz
from markupsafe import Markup, escape

from odoo import _, api, fields, models
from odoo.exceptions import UserError

# Fewer digits than this match too many numbers to be useful.
MIN_DIGITS = 6
# Greek numbers are 10 digits; comparing the last 10 makes +30 / 0030 /
# spaces / dashes irrelevant on either side.
KEY_DIGITS = 10


def _phone_key(phone):
    digits = re.sub(r'\D', '', phone or '')
    return digits[-KEY_DIGITS:] if len(digits) >= MIN_DIGITS else ''


class CallIntakeWizard(models.TransientModel):
    _name = 'call.intake.wizard'
    _description = 'Νέο Τηλεφώνημα'

    phone = fields.Char(string='Τηλέφωνο')
    candidate_partner_ids = fields.Many2many(
        'res.partner', string='Επαφές με αυτό το τηλέφωνο',
        compute='_compute_candidate_partner_ids')
    partner_id = fields.Many2one('res.partner', string='Πελάτης')
    partner_name = fields.Char(
        string='Όνομα νέας επαφής',
        help='Αν ο αριθμός δεν ανήκει σε καμία επαφή: γράψτε όνομα και '
             'δημιουργείται νέα επαφή με αυτό το τηλέφωνο.')
    description = fields.Text(string='Τι ζητάει', required=True)
    user_id = fields.Many2one(
        'res.users', string='Σε ποιον πάει', required=True,
        default=lambda self: self.env.user,
        domain="[('share', '=', False)]")
    tag_ids = fields.Many2many('project.tags', string='Είδος')
    date_deadline = fields.Datetime(
        string='Προθεσμία', default=lambda self: self._default_deadline())
    open_task_ids = fields.Many2many(
        'project.task', string='Ανοιχτά αιτήματα του πελάτη',
        compute='_compute_open_task_ids')

    def _default_deadline(self):
        """End of today's working day in the user's timezone, as UTC."""
        tz = pytz.timezone(self.env.user.tz or 'Europe/Athens')
        local = tz.localize(datetime.combine(fields.Date.context_today(self), time(18, 0)))
        return local.astimezone(pytz.utc).replace(tzinfo=None)

    @api.depends('phone')
    def _compute_candidate_partner_ids(self):
        for wiz in self:
            wiz.candidate_partner_ids = wiz._find_partners(wiz.phone)

    def _find_partners(self, phone):
        key = _phone_key(phone)
        Partner = self.env['res.partner']
        if not key:
            return Partner
        # The Greek mobile lives in l10n_gr_partner's `kinito` (Odoo 19 has no
        # `mobile`); search it only where that module is installed.
        columns = ['phone'] + (['kinito'] if 'kinito' in Partner._fields else [])
        where = ' OR '.join(
            f"right(regexp_replace(coalesce({col}, ''), '\\D', '', 'g'), %(n)s) = %(key)s"
            for col in columns)
        self.env.cr.execute(
            f"SELECT id FROM res_partner WHERE active AND ({where}) LIMIT 20",
            {'n': len(key), 'key': key})
        ids = [row[0] for row in self.env.cr.fetchall()]
        # search() again so record rules apply to what the user is shown
        return Partner.search([('id', 'in', ids)])

    @api.onchange('phone')
    def _onchange_phone(self):
        candidates = self._find_partners(self.phone)
        if len(candidates) == 1:
            self.partner_id = candidates
        elif self.partner_id and self.partner_id not in candidates:
            self.partner_id = False

    @api.depends('partner_id')
    def _compute_open_task_ids(self):
        project = self.env.company._call_intake_project()
        for wiz in self:
            if not wiz.partner_id or not project:
                wiz.open_task_ids = False
                continue
            wiz.open_task_ids = self.env['project.task'].search([
                ('project_id', '=', project.id),
                ('partner_id', 'child_of', wiz.partner_id.commercial_partner_id.id),
                ('stage_id.fold', '=', False),
                ('state', 'not in', ['1_done', '1_canceled']),
            ], order='date_deadline asc, id desc', limit=10)

    def action_confirm(self):
        self.ensure_one()
        project = self.env.company._call_intake_project()
        if not project:
            raise UserError(_(
                'Δεν έχει οριστεί Έργο Αιτημάτων — Αιτήματα → Διαμόρφωση → '
                'Ρυθμίσεις.'))
        text = (self.description or '').strip()
        if not text:
            raise UserError(_('Γράψτε τι ζητάει ο πελάτης.'))
        partner = self.partner_id
        if not partner and self.partner_name:
            partner = self.env['res.partner'].create({
                'name': self.partner_name.strip(),
                'phone': (self.phone or '').strip() or False,
            })
        title = next(line.strip() for line in text.splitlines() if line.strip())
        body = Markup('<br/>').join(escape(line) for line in text.splitlines())
        if self.phone:
            body += Markup('<br/><br/>') + escape(_('Τηλέφωνο: %s', self.phone.strip()))
        stage = project.type_ids.sorted('sequence')[:1]
        # sudo: anyone answering the phone may log a request, whether or not
        # they have rights in the Project app; the uid stays theirs, so the
        # task is still created by them.
        task = self.env['project.task'].sudo().create({
            'project_id': project.id,
            'stage_id': stage.id,
            'name': title[:120],
            'description': body,
            'partner_id': partner.id,
            'user_ids': [(6, 0, self.user_id.ids)],
            'tag_ids': [(6, 0, self.tag_ids.ids)],
            'date_deadline': self.date_deadline,
        })
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'message': _('Καταχωρίστηκε: «%(title)s» → %(user)s',
                             title=task.name, user=self.user_id.name),
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }
