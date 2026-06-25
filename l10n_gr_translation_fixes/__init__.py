import hashlib
import logging
import os

from odoo import models
from odoo.modules.module import get_module_path
from odoo.tools.translate import code_translations

_logger = logging.getLogger(__name__)

FIXES_DIR = os.path.join(os.path.dirname(__file__), 'fixes')
HASH_PARAM = 'l10n_gr_translation_fixes.bundle_hash'


def _iter_fixes():
    if not os.path.isdir(FIXES_DIR):
        return
    for name in sorted(os.listdir(FIXES_DIR)):
        po = os.path.join(FIXES_DIR, name, 'el.po')
        if os.path.exists(po):
            yield name, po


def _bundle_hash():
    digest = hashlib.sha1()
    for name, po in _iter_fixes():
        digest.update(name.encode())
        with open(po, 'rb') as f:
            digest.update(f.read())
    return digest.hexdigest()


def _deploy_files():
    """Copy bundled POs into each target module's i18n_extra/el.po.

    Runs in the server process, so it has the service account's filesystem
    rights. Returns the modules whose file was created or updated.
    """
    changed = []
    for name, po in _iter_fixes():
        target_root = get_module_path(name, display_warning=False)
        if not target_root:
            continue
        dest = os.path.join(target_root, 'i18n_extra', 'el.po')
        with open(po, 'rb') as f:
            data = f.read()
        try:
            if os.path.exists(dest):
                with open(dest, 'rb') as f:
                    if f.read() == data:
                        continue
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, 'wb') as f:
                f.write(data)
            changed.append(name)
        except OSError:
            _logger.warning('cannot deploy translation fixes for %s to %s', name, dest, exc_info=True)
    if changed:
        # drop cached code translations so reloaded workers pick up the files
        code_translations.python_translations.clear()
        code_translations.web_translations.clear()
        _logger.info('Greek translation fixes deployed for: %s', ', '.join(changed))
    return changed


def _reload_db_terms(env):
    """Overwrite el_GR model terms from the (i18n + i18n_extra) PO files."""
    if 'el_GR' not in [code for code, _name in env['res.lang'].get_installed()]:
        return
    names = [name for name, _po in _iter_fixes()]
    modules = env['ir.module.module'].sudo().search(
        [('name', 'in', names), ('state', '=', 'installed')])
    if modules:
        modules._update_translations(filter_lang='el_GR', overwrite=True)
        _logger.info('Greek translation terms reloaded for: %s', ', '.join(modules.mapped('name')))


def _fix_gr_vat_label(env):
    gr = env.ref('base.gr', raise_if_not_found=False)
    if gr and gr.vat_label != 'ΑΦΜ':
        gr.sudo().write({'vat_label': 'ΑΦΜ'})


def post_init_hook(env):
    _deploy_files()
    _reload_db_terms(env)
    _fix_gr_vat_label(env)
    env['ir.config_parameter'].sudo().set_param(HASH_PARAM, _bundle_hash())


class L10nGrTranslationFixes(models.AbstractModel):
    _name = 'l10n.gr.translation.fixes'
    _description = 'Greek translation fixes deployer'

    def _register_hook(self):
        super()._register_hook()
        changed = _deploy_files()
        bundle = _bundle_hash()
        param = self.env['ir.config_parameter'].sudo()
        if changed or param.get_param(HASH_PARAM) != bundle:
            _reload_db_terms(self.env)
            param.set_param(HASH_PARAM, bundle)
        _fix_gr_vat_label(self.env)
