# Gather World — Phase 3: Social Experience

This package builds on the latest Phase 2 username-edit update. It keeps the existing Flask app, Neon schema, admin tools, account verification, password reset, Cloudinary avatar support and existing assets.

## Phase 3 features
- In-app notifications for new followers, likes, comments, comment replies and reposts.
- Unread notification count in the navigation, notification list, mark-read and mark-all-read.
- Saved posts page and save/unsave controls.
- Reposts shown in the community feed with attribution. Duplicate reposts are prevented.
- Threaded replies to top-level comments.
- Share buttons copy a post's public URL.
- Full-screen Gather Moments experience for both photo and video posts, with vertical scroll snapping, creator profile/follow controls, likes, comments, saves, reposts and share actions. Videos autoplay muted only while visible, with play/pause and sound controls.
- Feed and profile post cards now show Phase 3 actions.

## Local installation
1. Back up your current `E:\GatherWorld` folder and Neon database.
2. Extract this ZIP to a temporary folder.
3. Copy the extracted project contents into `E:\GatherWorld`, replacing matching project files.
4. Keep your existing `.env` and `.venv` folders/files. Do not replace `.env` with `.env.example`.
5. In CMD:

```bat
cd /d E:\GatherWorld
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

`init_db()` adds the new Phase 3 tables and the nullable `parent_comment_id` column on startup. Existing posts, accounts, likes, follows and comments are retained.

## Routes
- `/feed` — community feed with like, save, repost, comment and share actions.
- `/saved` — your saved posts.
- `/notifications` — activity notifications.
- `/moments` — full-screen vertical photo and video discovery page (For You, Videos and Photos filters).
- `/posts/<id>` — post detail and comment replies.

## Video note
The Moments player expects a direct HTTPS video file URL (for example an `.mp4` URL) saved on a post with media type `video`. A normal YouTube watch-page URL is not a direct video file and may not play in the HTML video element. We can add authorized provider embeds or media hosting in a later phase.

## Testing status
Python syntax, Jinja template parsing, route endpoint references, CSRF form tokens and ZIP integrity are checked when this package is built. A live Neon migration and browser interaction test must still be completed on your PC.


## Gather Moments interface update
The Moments page uses an original Gather World interface with a full-screen vertical media feed inspired by common short-video browsing patterns. It is not an exact reproduction of another service's branding or assets. It includes full-bleed photo/video media, creator identity, follow action, action rail, comments link, save, repost, share, media filters and mobile viewport handling. Video autoplay is muted and restricted to the visible card; sound can be enabled by the visitor.

## Photo and video uploads (new update)
- The Feed composer now has separate **Upload Photo** and **Upload Video** controls with a local preview before publishing.
- The Moments top bar has an **Upload** shortcut that opens the Feed composer.
- Uploaded media is sent from Flask directly to Cloudinary; the app does not write uploaded files to the local project folder.
- Photos: JPG, JPEG, PNG or WEBP, up to 10 MB.
- Videos: MP4, M4V, MOV or WEBM, up to 32 MB.
- Cloudinary uses the existing private `.env` values: `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY` and `CLOUDINARY_API_SECRET`. If these are blank or incorrect, uploads will fail with a configuration message. Keep the API secret private.
- Existing direct HTTPS media URL posting remains available under “Or use an existing media URL”.

### Upload test
1. Confirm the three Cloudinary environment variables are configured in your local `.env`.
2. Restart Flask after changing `.env`.
3. Open `/feed`, choose **Upload Photo** or **Upload Video**, select a supported file, and check the preview.
4. Add a caption (optional when a media file is selected) and click **Share post**.
5. Open `/moments` to confirm the new media appears. The Moments **Upload** button takes you back to the upload composer.
6. Test an unsupported file and an oversized file; both should be rejected with a helpful message.
