# Gather World — Phase 2: Security, Safety & Administration

This is a local-development update to the Phase 1 project. It adds security foundations, moderation tools, account administration and user privacy controls. It preserves the `gw_` schema and existing Phase 1 routes.

## Install safely
1. Back up `E:\GatherWorld`.
2. Extract this ZIP to a temporary folder.
3. Copy the project contents into `E:\GatherWorld`, replacing matching files.
4. Keep your existing `.env` and `.venv` unchanged. This ZIP intentionally contains no `.env` or `.venv`.
5. Add the admin identity setting described below to your private `.env`.

## Configure the first admin
Add ONE of these to `.env` (recommended: username):

```ini
ADMIN_USERNAMES=your_existing_username
# Alternatively, or for multiple trusted admins:
# ADMIN_EMAILS=verified_admin@example.com
```

Only existing accounts matching these environment values can open `/admin`. Do not expose admin credentials or let users choose their own admin role. Restart the Flask app after changing `.env`.

## Run locally
```bat
cd /d E:\GatherWorld
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

The startup `init_db()` creates new `gw_` tables and adds columns using `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`. Existing users, posts, follows, likes, comments, OTPs and reset records are not intentionally deleted. Existing user sessions will need to log in again after the session-version migration.

## Phase 2 features
- CSRF validation for all POST/PUT/PATCH/DELETE form submissions.
- Database-backed throttling for registration, login, OTP verification/resend, password reset, posting, commenting and reports.
- Session invalidation after password changes or admin suspension/restoration.
- Basic security response headers and 12-hour session lifetime.
- Admin dashboard at `/admin`, with member/post/report counts and recent account management.
- User report flows for posts and profiles.
- Admin moderation actions: dismiss report, remove reported post, suspend reported account.
- Admin action log in `gw_admin_actions`.
- User block/unblock and `/blocked` page; blocked users' posts are hidden from the viewer's feed.

## Important testing notes
- The admin account is configured through `ADMIN_USERNAMES` or `ADMIN_EMAILS`; there is no public admin signup.
- The rate limiter uses PostgreSQL and stores hashed bucket identifiers rather than raw IP addresses or email addresses.
- Admin dashboard currently lists the latest 50 accounts and up to 50 open reports.
- Reporting is a queue for human review; it is not automatic content classification.
- `FLASK_DEBUG=1` is the local default. Set `FLASK_DEBUG=0` outside local development. Set `COOKIE_SECURE=1` only when using HTTPS; keep it `0` for local `http://127.0.0.1`.
- Use a long, random `FLASK_SECRET_KEY` in `.env`. Do not send it in chat or commit `.env`.
- This is a Phase 2 development build, not a completed production security audit. Before launch, add automated tests, recovery procedures, monitoring, database backups, stronger moderator workflow and an independent security review.

## Scope boundary
This ZIP does not include Phase 3 features (notifications, bookmarks, reposts, advanced privacy settings) or any new affiliate/commerce features. Those remain in their original roadmap phases.


## Username / nickname editing update
- The Edit Profile page now allows a signed-in member to change their unique username (profile handle) as well as their display name.
- Usernames are normalized to lowercase and must be 3–30 characters containing letters, numbers or underscores.
- The new profile URL uses the new username. Existing follows, posts and comments remain linked by internal user IDs.
- If an administrator changes the username configured in `ADMIN_USERNAMES`, update that value in the private `.env` and restart Flask, or configure the administrator by verified email using `ADMIN_EMAILS`.
