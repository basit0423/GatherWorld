# Gather World Phase 3 — Full-screen Moments UI update

This update replaces the previous small, card-based Moments layout with a full-screen vertical media discovery experience for both images and videos. It uses Gather World branding, colors and controls, while following familiar short-form media browsing patterns. It does not copy another platform’s logo, name, icons or proprietary assets.

## What changed
- `/moments` now displays both image and video posts (up to 80 latest public media posts).
- One media item fills each viewport; scroll vertically with snap-to-item behavior.
- Videos autoplay muted only when the card is mostly visible, pause when off-screen, and loop. Visitors can pause/play and enable sound.
- Images fill the same full-screen media stage.
- For You / Videos / Photos filters.
- Creator avatar, display name, username and follow/unfollow control.
- Like, comments, save, repost and share controls on the right-side action rail.
- Home and Community navigation remains visible at the top.
- Responsive desktop and mobile layouts.

## Local install
1. Back up `E:\GatherWorld` and your Neon database.
2. Extract this ZIP to a temporary folder.
3. Copy its files into `E:\GatherWorld`, replacing matching files.
4. Keep your existing `.env` and `.venv`; do not replace them with `.env.example`.
5. Run:

```bat
cd /d E:\GatherWorld
.venv\Scripts\activate
python app.py
```

6. Open `http://127.0.0.1:5000/moments`.

No new environment variables or database tables are required for this UI update. The Moments route reads existing posts, likes, comments, bookmarks, reposts and follows.

## Media notes
- Uploaded or linked photos are displayed as full-screen cover images. Tall portrait photos will show best; wide photos may be cropped at the sides/top to fill the viewport.
- Videos must be direct HTTPS video-file URLs supported by the browser. A regular YouTube watch-page URL is not a direct video file.
- Autoplay starts muted because browsers commonly block autoplay with sound.

## Verification
Python syntax, Jinja template parsing, JavaScript syntax and ZIP integrity were checked. Live Neon database behavior and actual video playback must still be tested in the local browser with your own posts.
