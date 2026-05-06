import re
from odoo import models

_non_ascii = re.compile(r'[^\x00-\x7F]')


def _ascii_entities(text):
    if not text:
        return text
    return _non_ascii.sub(lambda m: '&#%d;' % ord(m.group(0)), text)


class IrActionsReport(models.Model):
    _inherit = 'ir.actions.report'

    def _run_wkhtmltopdf(self, bodies, report_ref=False, header=None, footer=None,
                         landscape=False, specific_paperformat_args=None,
                         set_viewport_size=False):
        try:
            is_our_report = (
                report_ref and
                self._get_report(report_ref).report_name == 'service.report_service_receipt'
            )
        except Exception:
            is_our_report = False

        if is_our_report:
            bodies = [_ascii_entities(b) for b in bodies]
            header = _ascii_entities(header)
            footer = _ascii_entities(footer)

        return super()._run_wkhtmltopdf(
            bodies,
            report_ref=report_ref,
            header=header,
            footer=footer,
            landscape=landscape,
            specific_paperformat_args=specific_paperformat_args,
            set_viewport_size=set_viewport_size,
        )
