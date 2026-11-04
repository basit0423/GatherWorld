GATHER WORLD — PHASE 9: PERFORMANCE & GLOBAL LAUNCH READINESS

Adds common query indexes, dynamic-page no-store headers, static asset caching, HSTS when running behind HTTPS in production, production configuration safeguards and an admin-only System Readiness dashboard at /admin/system.

Production environment settings: APP_ENV=production, FLASK_DEBUG=0, FLASK_SECRET_KEY=<long random private value>, COOKIE_SECURE=1. The app refuses to start in production if FLASK_SECRET_KEY is missing or shorter than 32 characters. Keep COOKIE_SECURE=0 for local HTTP testing.

The readiness dashboard displays only whether required settings exist; it never displays credential values. It checks database reachability and core Phase 7–8 tables. It does not replace a penetration test, formal security review, backup restore exercise, legal review, load test or production deployment checklist.

Before launch: configure HTTPS and domain, verify all environment variables, test restore from a Neon backup, run end-to-end tests on desktop/mobile, audit dependencies, confirm content/privacy/legal pages and monitoring/incident response.
