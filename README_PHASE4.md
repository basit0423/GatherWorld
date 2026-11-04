# Gather World — Phase 4: Communities

This update builds on the Phase 3 Photo/Video Upload Fix package.

## Included
- Compact three-line navigation menu. Discover groups Feed, Moments, People and Communities; My account groups Profile, Edit Profile and Blocked Members. Saved and Notifications are inside Discover. Admin appears for configured administrators.
- Community discovery/search and category filter.
- Public and private communities.
- Create community with owner membership.
- Join/leave public communities and request approval for private communities.
- Community home page, member directory preview, rules and discussions with optional Cloudinary photo/video attachments.
- Owner/admin settings, moderator roles and membership-request review.
- Community post announcements, delete and report controls.
- Basic upcoming community event creation for owner/admin/moderator.
- Neon PostgreSQL migration tables are created by `init_db()` when running `python app.py`.

## Local installation
1. Back up the existing `E:\GatherWorld` folder and Neon database.
2. Extract this ZIP to a temporary folder.
3. Copy the project files into `E:\GatherWorld`, replacing matching project files.
4. Keep your existing `.env` and `.venv` untouched.
5. Run:
   ```bat
   cd /d E:\GatherWorld
   .venv\Scripts\activate
   pip install -r requirements.txt
   python app.py
   ```
6. Test the menu at the top of every page and open `http://127.0.0.1:5000/communities`.

## Notes
- This package does not include `.env`, `.venv`, or secrets.
- Community discussions accept text plus optional JPG/PNG/WEBP photos or MP4/MOV/WEBM videos through the existing Cloudinary configuration (same 10 MB photo / 32 MB video limits as Phase 3).
- The global navigation is now a compact three-line menu on standard pages, the homepage and Moments. Select Discover in the menu to expand Feed, Moments, People and Communities.
- Community covers/icons currently use original CSS-generated artwork placeholders; external user-supplied community image upload can be added in a later refinement.
- Community discussions are separate from the global media feed; attached images/videos are stored in Cloudinary and their URLs in Neon.
- The event form stores the datetime with an explicit timezone; a timezone-free browser datetime is interpreted as UTC in this first version. Confirm the displayed event time in local testing.
- Database migration and real browser/database behavior must be verified locally against a backup before treating Phase 4 as complete.
- No GitHub or Vercel deployment is performed by this ZIP.
