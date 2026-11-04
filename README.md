GATHER WORLD — PHASES 12–17
================================

This cumulative local-development package builds on the latest Phase 11 project
and adds six simple, connected directory modules:

12. Services & Freelancing
13. Food & Local Commerce
14. Travel & Tourism
15. Education & Learning
16. Careers & Jobs
17. Events & Experiences

The new modules share one responsive, theme-aware interface and one PostgreSQL
listing model. They are designed to be simple to browse, search, create, edit,
and manage. They are not full payment, booking, delivery, learning-management,
or applicant-tracking systems.

INSTALLATION
------------
1. Back up E:\GatherWorld and take a Neon database backup.
2. Extract this ZIP to a temporary folder.
3. Copy its contents into E:\GatherWorld and replace matching project files.
4. Keep your existing private .env and .venv folders. They are not included.
5. In the existing activated virtual environment, run:
       pip install -r requirements.txt
       python app.py
6. The local init_db() routine creates the Phase 12–17 tables and indexes. Do not
   delete or reset existing database tables.

NEW PAGES
---------
Phase 12: /services, /services/create, /my-listings
Phase 13: /food, /food/create
Phase 14: /travel, /travel/create
Phase 15: /learn, /learn/create
Phase 16: /careers, /careers/post
Phase 17: /events, /events/create
Admin:    /admin/directory-listings

Each directory has detail pages at its matching /<section>/<slug> URL. Owners
can edit or hide their own listings from /my-listings. Service providers can
review inquiries sent through a listing. Event hosts can receive RSVPs and see
Going / Interested counts.

WHAT THE MODULES DO NOT DO YET
-----------------------------
- Gather World does not collect money or process checkout for these listings.
- Food ordering, accommodation booking and travel payments remain with the
  provider's official website.
- Job applications are handled by the employer's external application page or
  contact details; Gather World is not an employer or recruiter.
- Learning resources link to their provider; this is not yet a full LMS.
- Events have Gather RSVP tracking, but no ticket payments or venue services.
- Listings are community-submitted and labelled unverified. Admins can hide or
  restore them. Verify providers and information before relying on a listing.
- Images are optional HTTPS image URLs. The form does not upload these new
  directory images to Cloudinary; a Cloudinary secure URL can be entered.

SECURITY AND PRIVACY
--------------------
- New POST forms include the existing CSRF token mechanism.
- New listing links and image URLs must use HTTPS.
- New listings are rate-limited per account.
- SQL values are parameterized.
- No .env, API keys, database connection strings, or .venv are included.
- Do not share the contents of your private .env file.

TESTING STATUS
--------------
Static checks performed in the packaging environment:
- Python syntax compilation.
- Jinja parsing for every template.
- Static url_for endpoint reference check.
- ZIP archive integrity check.

Not performed here:
- Live Neon schema migration.
- Browser-based form, mobile layout, event RSVP, or service inquiry testing.
- External provider, affiliate, booking, job, or course link verification.

Run the included PHASE12_17_LOCAL_TEST_CHECKLIST.txt on your PC before moving
on to Phase 18 or deploying anything publicly.
