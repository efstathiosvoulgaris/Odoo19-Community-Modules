# SKARLAS Website — Odoo 19 Community

Standard website module (NOT a theme module — no theme_ prefix, so it shows in Apps normally).

## Install / upgrade from the old attempt
1. Remove the old module first if it got installed: Apps → theme_eskarlas → Uninstall.
   Then delete /mnt/extra-addons/theme_eskarlas.
2. Copy skarlas_website into /mnt/extra-addons, restart the container.
3. Apps → Update Apps List → search "SKARLAS Website" → Install.
   (Or CLI: odoo -d test -i skarlas_website --stop-after-init ... as before.)

## Pages created (published)
- /home-skarlas — set as homepage when happy (Website settings → Homepage URL)
- /services
- /psifiaki-ypografi
- /epikoinonia

All content sits in #wrap .oe_structure → editable with the website builder.
Menu items, logo, real photos (striped placeholders), and /shop (eCommerce app)
still need wiring by hand — see comments in the pages.
