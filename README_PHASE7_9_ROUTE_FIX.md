GATHER WORLD — PHASE 7–9 ROUTE FIX

This patch fixes missing Flask endpoints that caused Werkzeug BuildError for ai_home.
It adds the AI chat endpoints and supporting tables, creator and business directory routes,
creator profile routes, business page routes, and the admin system-readiness route.
It also removes duplicate Gather AI / Creators / Businesses navigation entries.

Files to replace: app.py and templates/base.html. The ZIP contains the complete project
for convenience, but keep your existing private .env and .venv unchanged.

Gemini configuration in your private .env:
GEMINI_API_KEY=your-private-key
GEMINI_MODEL=gemini-3.8-flash

If GEMINI_API_KEY is blank, the AI page still opens and displays an explanatory message
when a user tries to send a prompt. The Gemini key is read only by the server.
The code calls Google's supported generateContent REST endpoint. Google currently
recommends the Interactions API for new applications, but generateContent remains supported.

Local test:
  cd /d E:\GatherWorld
  .venv\Scripts\activate
  pip install -r requirements.txt
  python app.py

Then test /, /ai, /creators, /businesses and /admin/system (admin account required).
Run init_db through python app.py so the new tables are created. Back up Neon first.
No .env or .venv is included.
