# Gather World — Phase 11: Advanced Shopping Tools

This is a local-development update built on the Phase 10 Affiliate Readiness project. It adds shopping tools around approved affiliate product listings. It keeps the original 37-phase roadmap and focuses the product-management workflow on the first three partner targets: Daraz Pakistan, Amazon Associates and eBay Partner Network.

## Important operating model

Gather World is an affiliate discovery and referral platform, not the retailer. A customer may save products in a Gather cart, but checkout and payment happen on each retailer's own website. The Gather cart groups products by retailer for organization; it does NOT transfer a multi-item cart into a retailer checkout. The customer follows a tracked product link one item at a time.

A product is shown publicly only when all of the following are true:
- The product listing status is `published`.
- Its retailer partner status is `approved`.
- A product-specific HTTPS affiliate tracking URL has been entered by an administrator.

No partner approval, tracking link, product price, discount or inventory status is invented by this update. Daraz and Amazon remain `applied` as previously recorded; eBay remains `research` unless an administrator updates it based on a real application decision. Only use partner-issued tracking URLs and product imagery you are authorized to display.

## Included features

- Public shopping catalogue at `/shop` with search, category filters and sorting.
- Product detail pages at `/shop/product/<slug>`.
- Admin product catalogue at `/admin/shop-products`.
- Manual product listing creation and maintenance for the three initial retailer targets.
- Draft, published and paused listing states.
- Product-specific affiliate HTTPS URL validation.
- Gather cart at `/shop/cart`, with quantity limits and items grouped by retailer.
- Separate outbound handoff to each retailer at `/shop/out/<product_id>`; every outbound click is recorded.
- Product wishlist at `/shop/wishlist`.
- Product comparison at `/shop/compare`, up to four products.
- Deals at `/shop/deals`; a discount is shown only when the entered original price is greater than the current partner price.
- Price alerts at `/shop/price-alerts`; users receive an in-app notification when an administrator records a lower product price that reaches the user's target.
- Recently viewed products at `/shop/recently-viewed`.
- Admin click counts for each product listing.
- Navigation shortcuts to shopping tools.
- Existing Phase 10 Light/Dark theme preference is retained and shopping pages include both theme palettes.

## Routes

Public:
- `/shop`
- `/shop/product/<slug>`
- `/shop/deals`
- `/shop/compare`
- `/shop/recently-viewed`
- `/shop/out/<product_id>`

Sign-in required:
- `/shop/cart`
- `/shop/cart/add/<product_id>`
- `/shop/cart/update/<item_id>`
- `/shop/cart/remove/<item_id>`
- `/shop/wishlist`
- `/shop/wishlist/toggle/<product_id>`
- `/shop/price-alerts`
- `/shop/price-alerts/delete/<alert_id>`

Administrator only:
- `/admin/shop-products`

All state-changing POST forms include the existing CSRF token requirement. Cart additions are rate limited.

## Install locally

1. Back up `E:\GatherWorld`.
2. Back up the Neon database before running schema initialization.
3. Extract this ZIP into a temporary folder.
4. Copy the contents into `E:\GatherWorld`, replacing matching files.
5. Keep the existing private `.env` and `.venv` unchanged. Neither is included in this ZIP.
6. Run the app locally:

```bat
cd /d E:\GatherWorld
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

The local `init_db()` function creates the Phase 11 tables additively:
- `gw_shop_products`
- `gw_shop_cart_items`
- `gw_shop_wishlists`
- `gw_shop_price_alerts`
- `gw_shop_product_views`
- `gw_shop_product_clicks`

Existing users, posts, messages, communities and previous phase tables are not dropped.

## Add products safely

1. Keep Daraz, Amazon and eBay statuses accurate in `/admin/affiliate-partners`.
2. Until a partner approves the publisher account, add any catalogue entries as `Draft` only, or wait to add them.
3. Once approved, use a product-specific affiliate tracking URL issued by that partner.
4. Enter the product's HTTPS image URL only if the retailer/affiliate programme permits its use.
5. Publish only after the retailer is approved and the product-specific tracking link is valid.
6. Enter prices and original prices from a reliable, current partner source. Gather does not fetch live product feeds in this phase.

Do not create fake product offers, fake discounts or affiliate links by modifying ordinary shopping URLs.

## Feature limitations

- No Gather World payment checkout or payment processing. Retailers collect payment and fulfil orders.
- A Gather cart is an organizer, not a synchronized retailer cart. Users continue to the retailer per product.
- No real-time retailer product feeds, inventory APIs, price-history charts or automated partner commission imports.
- Price alerts are triggered only when an administrator manually records a lower price in the product catalogue; notifications are in-app only.
- Price comparison displays entered currencies as shown; it does not perform currency conversion.
- Product specifications are the description entered by an administrator; no technical-spec extraction is performed.
- Product click totals are recorded, but they are not confirmed sales or commissions.
- No shipping, refunds, customer service or returns are handled by Gather World.

## Local test checklist

See `PHASE11_LOCAL_TEST_CHECKLIST.txt`.

## Testing scope

Python compilation, Jinja template parsing, template endpoint references, POST form CSRF token presence and ZIP integrity were checked while preparing this package. This environment did not connect to the user's Neon database, perform browser interactions, verify partner approval, validate real affiliate conversions, or test the user's retailer credentials. Complete those tests locally before using this update beyond development.

## Scope

This package includes the Phase 10 project plus Phase 11 shopping tools. It does not change the original 37-phase roadmap and does not imply that Daraz, Amazon or eBay has approved Gather World. No deployment to GitHub or Vercel is performed.
