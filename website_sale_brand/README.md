# website_sale_brand — Brands for eCommerce

**Version:** 1.0 | **Odoo:** 19 | **License:** LGPL-3

Adds a `product.brand` model and wires it through the eCommerce shop: a brand
page, a shop filter, and brand fields on the product form.

---

## Model

`product.brand` (inherits `image.mixin`)

| Field | Description |
|-------|-------------|
| `name` | Μάρκα — translatable, indexed |
| `description` | Html, translatable |
| `image_*` | Brand logo, via `image.mixin` |
| `website_published` | Default True; unpublished brands vanish from the site |
| `product_tmpl_ids` / `product_count` | The products carrying the brand |

`product.template.brand_id` is a Many2one with `ondelete='set null'` — deleting
a brand never takes products with it.

---

## Website

| Route | What |
|-------|------|
| `/brands` | Public page listing every published brand (in the sitemap) |
| `/shop?brands=1,5,9` | Shop filtered by brand |

The filter is kept in the session (`wsale_brand_ids`) and folded into
`_get_shop_domain`, so it survives paging and combines with the category,
attribute, price and search filters rather than replacing them. Passing no
`brands` parameter clears it.

The brand list offered in the shop sidebar is limited to published brands that
have at least one published product, and only appears when the current search
actually returned products.

---

## Import

`base_import` is a dependency so brands can be created and assigned in bulk from
a spreadsheet: import `product.brand` first, then `product.template` with a
`brand_id` column matched by name.

---

## Changelog

### 1.0
- Initial public release.
