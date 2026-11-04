# Gather World Phase 3 — Photo & Video Upload Update

This package builds on the full-screen Gather Moments update and adds actual photo/video upload controls.

## Where to upload
- Open `/feed` and use the **Upload Photo** or **Upload Video** control in the post composer.
- The `/moments` top bar has an **Upload** shortcut to the same composer.
- A local preview appears before publishing.

## Limits and formats
- Photos: JPG, JPEG, PNG, WEBP — maximum 10 MB.
- Videos: MP4, M4V, MOV, WEBM — maximum 32 MB.
- Request body limit is 34 MB to allow multipart overhead.

## Cloudinary setup
The project uses the Cloudinary environment variables already used for profile avatar uploads:

```env
CLOUDINARY_CLOUD_NAME=your_cloud_name
CLOUDINARY_API_KEY=your_api_key
CLOUDINARY_API_SECRET=your_api_secret
```

Keep these values in your private local `.env` only. Do not include `.env` in ZIPs or commit it to Git. Uploads are sent directly from Flask to Cloudinary; media files are not stored in the local project directory. The database stores the returned HTTPS media URL.

## Local test
1. Back up the current project and database.
2. Extract this ZIP and copy its contents into `E:\GatherWorld`, replacing matching files.
3. Keep your current `.env` and `.venv`.
4. Confirm the three Cloudinary variables are configured locally.
5. Restart Flask and open `http://127.0.0.1:5000/feed`.
6. Test photo and video previews, publish one of each, then confirm they appear in `/moments`.
7. Also test invalid file types and oversized files.

The package passed Python syntax, Jinja template parsing, JavaScript syntax, upload-wiring checks and ZIP integrity checks. Live Cloudinary uploads and Neon writes still need to be tested in your local environment.
