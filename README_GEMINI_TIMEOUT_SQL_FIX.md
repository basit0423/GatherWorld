GATHER WORLD — GEMINI TIMEOUT + PHASE 11 SQL FIX

This update is based on the Phase 11 Psycopg SQL Fix project. It retains the
existing phases and the escaped literal percent in shop_public_product_query():
LIKE 'https://%%'. This prevents the Psycopg placeholder error in parameterized SQL.

Gemini changes:
- Uses x-goog-api-key request header; the key is not put in the request URL.
- Timeout is configurable with GEMINI_TIMEOUT_SECONDS (default 90, bounded 20–120).
- Catches socket read timeouts and displays a friendly explanation instead of Flask HTTP 500.
- Retries one transient HTTP 500/502/503/504 response after a short delay.
- Keeps useful HTTP categories for invalid credentials, request/model errors and quota.

Install by backing up E:\GatherWorld, extracting this ZIP to a temporary folder,
copying its contents over the project, and keeping the existing .env and .venv.
Add GEMINI_TIMEOUT_SECONDS=90 to the private .env if desired, then restart Flask.

This cannot guarantee that Google responds; it makes Gather World handle timeouts
and temporary service errors gracefully. Test /ai and /shop locally after installing.
Do not share GEMINI_API_KEY or commit .env.
