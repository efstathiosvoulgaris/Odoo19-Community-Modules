import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..lib import pno

_logger = logging.getLogger(__name__)
REST_TIMEOUT = (10, 45)
ATHENS = ZoneInfo('Europe/Athens')
NO_FILE_HOURS = 30


class DiasFile(models.Model):
    _name = 'dias.file'
    _description = 'ΔΙΑΣ: αρχείο πληρωμών (PNO)'
    _order = 'id desc'

    name = fields.Char('Αρχείο', required=True, readonly=True)
    company_id = fields.Many2one('res.company', required=True, readonly=True)
    imported_at = fields.Datetime('Εισαγωγή', default=fields.Datetime.now, readonly=True)
    rows_total = fields.Integer('Γραμμές', readonly=True)
    rows_new = fields.Integer('Νέες πληρωμές', readonly=True)
    result = fields.Text('Αποτέλεσμα', readonly=True)

    _name_company_uniq = models.Constraint('unique(name, company_id)',
                                           'Το αρχείο έχει ήδη εισαχθεί.')

    @api.model
    def _dias_import(self, company, filename, content):
        """Καταχωρεί τις πληρωμές ενός αρχείου. Ίδιο RID = ίδια πληρωμή (και με το online)."""
        try:
            rows, skipped = pno.parse_pno(filename, content)
        except Exception as e:  # noqa: BLE001 — χαλασμένο/άγνωστο αρχείο: μήνυμα, όχι traceback
            raise UserError(_('Το αρχείο %(f)s δεν διαβάζεται: %(e)s', f=filename, e=e)) from e
        Payment = self.env['dias.payment'].sudo()
        env = company.sudo().dias_env
        to_process = Payment
        for r in rows:
            tst = str(r.get('_TstCode') or '').strip().upper()
            if tst and tst != env:
                skipped += 1  # αρχείο άλλου περιβάλλοντος (T/P)
                continue
            if str(r.get('Status') or '').strip() not in ('0', '1', '0.0', '1.0'):
                skipped += 1  # απορριφθείσες/επιστραφείσες
                continue
            ri = (r.get('RI_MID') or str(r.get('RemittanceInformation') or '')[:25] or '').strip()
            to_process |= Payment._dias_register(company, {
                'name': str(r['RID']).strip(),
                'ri_mid': ri,
                'amount': pno.to_float(r.get('PaidAmount')),
                'bk_date': pno.to_str_date(r.get('BkDate')),
                'payment_dt': str(r.get('PaymentDtTm') or ''),
                'debtor_name': r.get('DebtorName') or '',
                'debtor_bic': r.get('DebtorBankBIC') or '',
                'transaction_id': r.get('TransactionID') or '',
                'remittance': str(r.get('RemittanceInformation') or '')[:140],
                'source': 'file',
                'raw': str({k: v for k, v in r.items() if not k.startswith('_')}),
            }, confirmed=True)
        to_process._dias_process()
        problems = to_process.filtered(lambda p: p.state in ('unmatched', 'v13', 'error'))
        record = self.sudo().create({
            'name': filename, 'company_id': company.id, 'rows_total': len(rows),
            'rows_new': len(to_process),
            'result': _('%(t)s γραμμές, %(n)s νέες, %(s)s παραλείφθηκαν, %(p)s θέλουν χειρισμό.',
                        t=len(rows), n=len(to_process), s=skipped, p=len(problems)),
        })
        company.sudo().write({'dias_last_file_at': fields.Datetime.now(),
                              'dias_last_file_name': filename})
        return record

    # ── Λήψη μέσω File Transfer REST API (HTTPS) ─────────────────────────────

    @api.model
    def _cron_dias_fetch(self):
        companies = self.env['res.company'].sudo().search([
            ('dias_org_id', '!=', False), ('dias_ftp_password', '!=', False),
            ('dias_org_code', '!=', False)])
        for company in companies:
            try:
                self._fetch_company(company)
            except Exception as e:  # noqa: BLE001 — μια εταιρεία δεν σταματά τις άλλες
                _logger.exception('ΔΙΑΣ: αποτυχία λήψης για %s', company.name)
                self.env.cr.rollback()
                self._dias_fetch_failed(company, str(e))
            self._dias_check_silence(company)

    def _dias_fetch_failed(self, company, error):
        company = company.sudo()
        if company.dias_last_error != error:
            company.dias_last_error = error
            company._dias_notify_manager(_('ΔΙΑΣ: αποτυχία λήψης αρχείων'), error)

    def _dias_check_silence(self, company):
        """Εργάσιμη, μετά τον τελευταίο κύκλο (19:15), χωρίς αρχείο για πάνω από NO_FILE_HOURS:
        μία ειδοποίηση τη μέρα. Η ΔΙΑΣ βγάζει αρχείο μόνο όταν υπάρχουν πληρωμές, οπότε η
        ειδοποίηση λέει «ελέγξτε», όχι «χάλασε»."""
        company = company.sudo()
        now = datetime.now(ATHENS)
        if now.weekday() >= 5 or now.hour < 20:
            return
        last = company.dias_last_file_at
        if last and fields.Datetime.now() - last < timedelta(hours=NO_FILE_HOURS):
            return
        key = 'l10n_gr_dias_rf.silence_alert_%s' % company.id
        Param = self.env['ir.config_parameter'].sudo()
        today = now.date().isoformat()
        if Param.get_param(key) == today:
            return
        Param.set_param(key, today)
        company._dias_notify_manager(_('ΔΙΑΣ: κανένα αρχείο πληρωμών'), _(
            'Δεν κατέβηκε αρχείο πληρωμών από %s. Αν περιμένατε πληρωμές, ελέγξτε το ΔΙΑΣ Portal.',
            last or _('ποτέ')))

    def _file_org(self, company):
        """.XOO: ο 5ψήφιος κωδικός οργανισμού στο όνομα· CSV/XLSX: το OrgID."""
        company = company.sudo()
        return company.dias_org_code if (company.dias_pno_ext or 'xml') == 'xml' else company.dias_org_id

    def _fetch_company(self, company, manual=False):
        """manual = κουμπί «Λήψη τώρα»: μόνο σήμερα και χθες, χωρίς ενδιάμεσα commit (όλα ή
        τίποτα, μέσα στο ίδιο αίτημα). Από το cron: commit ανά αρχείο."""
        company = company.sudo()
        if not (company.dias_org_id and company.dias_ftp_password):
            raise UserError(_('Συμπληρώστε OrgID και κωδικό File Transfer.'))
        Cron = self.env['ir.cron']
        done = set(self.sudo().search([('company_id', '=', company.id)]).mapped('name'))
        names = [n for n in pno.pno_filenames(
            self._file_org(company), fields.Date.context_today(self), company.dias_pno_cycles,
            company.dias_pno_ext, company.dias_pno_lobid, days_back=1 if manual else 4)
            if n not in done]
        if not manual:
            Cron._commit_progress(remaining=len(names))
        imported = 0
        for name in names:
            content = self._download(company, name)
            if content is not None:
                with self.env.cr.savepoint():
                    self._dias_import(company, name, content)
                imported += 1
            if not manual and not Cron._commit_progress(1):
                break
        company.dias_last_error = False
        return imported

    def _download(self, company, filename):
        """POST multipart path=<OrgID>/IN/<αρχείο>, Basic Auth OrgID/κωδικός. None = δεν υπάρχει
        (ακόμα). Ό,τι άλλο πάει στραβά σηκώνει σφάλμα, για να φανεί."""
        import requests
        org = company.dias_org_id
        resp = requests.post(
            company.dias_rest_url or 'https://apps.dias.com.gr/dias-fti/rest/file/download',
            auth=(org, company.dias_ftp_password or ''),
            files={'path': (None, '%s/IN/%s' % (org, filename))}, timeout=REST_TIMEOUT)
        if resp.status_code in (401, 403):
            raise UserError(_('ΔΙΑΣ REST: άρνηση πρόσβασης (HTTP %s). Ελέγξτε OrgID/κωδικό.',
                              resp.status_code))
        if resp.status_code == 404:
            return None  # το αρχείο δεν υπάρχει (ακόμα)
        if resp.status_code != 200:
            raise UserError(_('ΔΙΑΣ REST: HTTP %(code)s για %(f)s.', code=resp.status_code, f=filename))
        if not resp.content:
            return None
        head = resp.content[:400]
        name = filename.lower()
        if name.endswith('.xoo'):
            valid = head.lstrip()[:1] == b'<'
        elif name.endswith('.csv'):
            valid = b'LobID' in head
        else:
            valid = head[:2] == b'PK'
        if not valid:
            if b'BEGIN PGP' in head or head[:1] in (b'\x85', b'\x84', b'\xc1'):
                raise UserError(_('Το αρχείο %s ήρθε κρυπτογραφημένο (PGP): στο ΔΙΑΣ Portal ορίστε '
                                  'αρχεία χωρίς κρυπτογράφηση.', filename))
            return None
        return resp.content


class DiasImportWizard(models.TransientModel):
    _name = 'dias.import.wizard'
    _description = 'ΔΙΑΣ: εισαγωγή αρχείου πληρωμών'

    company_id = fields.Many2one('res.company', required=True, default=lambda s: s.env.company)
    filename = fields.Char('Όνομα αρχείου')
    data = fields.Binary('Αρχείο (.XOO, .csv, .xlsx)', required=True)

    def action_import(self):
        import base64
        self.ensure_one()
        if not self.env.user.has_group('account.group_account_manager'):
            raise UserError(_('Μόνο ο υπεύθυνος λογιστηρίου.'))
        if self.env['dias.file'].sudo().search_count([
                ('name', '=', self.filename or ''), ('company_id', '=', self.company_id.id)]):
            raise UserError(_('Το αρχείο %s έχει ήδη εισαχθεί.', self.filename))
        started = self.env.cr.now()  # = create_date όσων δημιουργηθούν σε αυτή τη συναλλαγή
        self.env['dias.file']._dias_import(
            self.company_id, self.filename or '', base64.b64decode(self.data))
        return {
            'type': 'ir.actions.act_window', 'name': _('Πληρωμές ΔΙΑΣ'),
            'res_model': 'dias.payment', 'view_mode': 'list,form',
            'domain': [('company_id', '=', self.company_id.id), ('create_date', '>=', started)],
        }
