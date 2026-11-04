GATHER WORLD PHASE 11 — PSYCOPG SQL FIX

Fixes the PostgreSQL/Psycopg ProgrammingError:
"only '%s', '%b', '%t' are allowed as placeholders, got '%'"

Cause: shop_public_product_query() included a literal percent sign in a LIKE pattern
(affiliate_url LIKE 'https://%') and was later executed with Psycopg parameters.

Fix: escape the literal percent for Psycopg as LIKE 'https://%%'. This keeps the
intended SQL pattern (HTTPS URLs) while allowing Psycopg to parse the query.

Install: back up the project and database, extract this complete ZIP, copy files
into E:\GatherWorld replacing matching files, and preserve your existing .env
and .venv. Then restart Flask and test /shop, /shop/product/<slug>, /shop/cart,
/shop/wishlist, /shop/compare, /shop/deals, /shop/price-alerts and /shop/recently-viewed.

Python syntax compilation and source ZIP integrity passed. Live Neon/browser tests
remain to be performed locally. No credentials or .env file are included.
