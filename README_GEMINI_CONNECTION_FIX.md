GATHER WORLD — GEMINI CONNECTION FIX

This update improves the Phase 7 Gather AI connection handling.

WHAT CHANGED
- Sends the Gemini API key in the x-goog-api-key request header instead of the URL query string.
- Keeps the key server-side; it is never sent to browser JavaScript.
- Gives separate, safe diagnostics for invalid keys (401), project/API permission (403), quota/rate limits (429), model/request errors (400/404), timeouts and temporary Google service errors (5xx).
- Does not log the API key, prompt, request URL or authorization header.
- Keeps GEMINI_MODEL default as gemini-3.8-flash.

INSTALL
1. Back up E:\GatherWorld.
2. Extract this ZIP to a temporary folder.
3. Copy the extracted project files into E:\GatherWorld, replacing matching files.
4. Keep your existing .env and .venv unchanged.
5. In the existing private .env, make sure you have:
   GEMINI_API_KEY=your_actual_key
   GEMINI_MODEL=gemini-3.8-flash
6. Do not include quotation marks or extra spaces around the value. Do not share the key.
7. Stop Flask with Ctrl+C, then restart:
   cd /d E:\GatherWorld
   .venv\Scripts\activate
   python app.py
8. Open /ai, create a new conversation and send a short test message.

HOW TO READ THE NEW ERROR
- Missing key: .env was not loaded, value is blank, or the variable name is wrong.
- HTTP 401: API key is invalid/expired.
- HTTP 403: Google denied API access; check project/key permissions, API access, region eligibility and billing status in Google AI Studio.
- HTTP 429: quota or request-rate limit reached.
- HTTP 400/404: verify model ID and model support for generateContent.
- HTTP 5xx: temporary Google service-side error.
- Network connection error: check internet/firewall access to generativelanguage.googleapis.com.

SECURITY
Never paste GEMINI_API_KEY in chat, screenshots, terminal logs or GitHub. Keep .env private.

TESTING LIMITATION
Python syntax compilation and ZIP integrity were checked. A real Gemini request cannot be verified without the user's private API key and local network/project access.
