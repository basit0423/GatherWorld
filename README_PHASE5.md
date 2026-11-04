GATHER WORLD — PHASE 5: MESSAGING & CONNECTIONS

This package builds on the Phase 4 project and adds:
- Private one-to-one conversations.
- Group conversations (up to 20 total members).
- Inbox with latest-message previews and unread counts.
- Message sending and notification integration.
- Membership checks for every conversation and message action.
- Block checks for new direct conversations and direct-message sending.
- Rate limits for starting conversations and sending messages.
- Group leave controls.

LOCAL INSTALL
1. Back up the entire E:\GatherWorld folder and your Neon database.
2. Extract this ZIP to a temporary folder.
3. Copy its contents into E:\GatherWorld and replace matching application files.
4. Keep your existing .env and .venv files unchanged.
5. Activate your existing virtual environment and run: python app.py
6. The normal init_db() startup adds the Phase 5 messaging tables and indexes.
7. Test /messages, /messages/new, one-to-one messages, group messages, unread counts, and blocking.

SECURITY / SCOPE NOTES
- Every message form uses the existing CSRF protection.
- Message bodies are plain text (max 4,000 characters); HTML is escaped by Jinja.
- This phase does not include end-to-end encryption, file attachments, voice/video calls, or message deletion/editing.
- This package does not send message contents by email. In-app notification rows are created for recipients.
- Back up Neon before running schema migrations. Test with two separate local user accounts.
- Do not include .env in GitHub commits or ZIPs.

No deployment is performed by this package. Local database and browser testing is still required.
