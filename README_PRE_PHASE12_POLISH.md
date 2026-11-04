# Gather World — Pre-Phase 12 Polish Update

This update is based on the latest Phase 11 Gemini timeout / shopping SQL fix package. It does not remove Phase 1–11 features.

## Included
- A complete appearance selector with **System / Light / Dark** modes. The selected mode is stored in browser local storage. System mode follows the device preference.
- The same compact three-line menu on standard pages, the home page and Moments.
- Exactly three expandable navigation groups: **Explore & discover**, **Create & connect**, and **My space & tools**.
- A quick search field in the menu; `Ctrl+K` or `/` focuses it.
- Menu closes after navigation, outside click or Escape.
- Skip-to-content link, visible keyboard focus and reduced-motion support.
- Lazy/async image loading defaults, metadata-free Moments video preloading, reduced entrance animation and content-visibility for long lists.
- Updated asset version query so browsers fetch the new CSS and JavaScript.

## Install locally
1. Back up `E:\GatherWorld` and Neon.
2. Extract this ZIP to a temporary folder.
3. Copy its contents into `E:\GatherWorld`, replacing matching project files.
4. Keep your existing `.env` and `.venv` unchanged.
5. Run `python app.py` as usual.

## Test
- Open Home, Feed, Moments, Messages, Communities, AI, Shopping, Admin and Profile.
- Open each of the three menu groups; check every link.
- Cycle System → Light → Dark → System, refresh and verify persistence.
- Use `Ctrl+K`, `/`, Escape and outside-click behavior.
- Check mobile width and desktop width.
- Confirm images load lazily and Moments video starts only when visible.

No deployment is performed. This is a local UI/performance polish update, not a production security audit.
