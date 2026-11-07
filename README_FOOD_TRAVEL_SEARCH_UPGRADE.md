# Gather World — Food & Travel Search Discovery Upgrade

This update turns the existing Food and Travel directories into information pages designed to answer real visitor questions, for example:

- Is this restaurant worth considering?
- What cuisine, menu, price range, hours and contact details are available?
- What can I visit in this destination?
- When is a good season to visit, how can I get there, and what might a trip cost?
- Which restaurants or travel resources are listed in a particular area?

## What changed

### Restaurant and food pages
- Dedicated, server-rendered restaurant detail pages with descriptive titles, meta descriptions, canonical URLs and `Restaurant` JSON-LD.
- New fields for cuisine, opening hours, menu highlights, who the venue may suit, dietary/allergen/access notes, typical spend, phone and source URL.
- Member ratings and written reviews. Reviews start as `pending` and only appear after an administrator approves them.
- The page explains when feedback is too limited to draw a conclusion. It never invents ratings or claims a visit was verified.

### Travel and destination pages
- Destination detail pages with best season, access routes, attractions, daily budget range, currency, budget breakdown, sample itinerary, local tips and safety/access notes.
- A trip estimate calculator multiplies the submitted per-person daily range by trip duration and group size. It is labelled as an estimate, not a live quote.
- New location landing pages at `/travel/in/<location-slug>`.

### Local food discovery pages
- Location landing pages at `/food/in/<location-slug>` collect entries from the same area.
- Location pages are offered for indexing only when at least two detailed listings exist in that area.
- Listing detail URLs are included in the dynamic sitemap only after passing the page completeness checks.

### Search and trust
- Descriptive titles and meta descriptions tailored to each restaurant or destination.
- JSON-LD structured data: `Restaurant` pages include real aggregate ratings/reviews only after approved member reviews exist; destination pages use `TouristDestination`.
- Incomplete Food and Travel detail pages use `noindex,follow` and are excluded from the dynamic sitemap until they contain enough useful, sourced information.
- The pages clearly distinguish community submissions, approved community reviews, source links and contributor-entered estimates.

## Database migration — do this before deploying

The app has an additive `init_db()` migration. From the project folder, with the correct `.env` and `.venv` active, run:

```cmd
.venv\Scripts\python.exe -c "import app; app.init_db(); print('Gather World database migration completed')"
```

This connects to the `DATABASE_URL` in the local `.env`. Make sure it is the same Neon database used by the new Vercel project. The migration adds nullable/defaulted columns and a review table; it does not delete existing listings or users.

Manual alternative: run `migrations/20261107_food_travel_search_upgrade.sql` in the correct Neon SQL Editor, after confirming the existing `gw_directory_entries` and `gw_users` tables are present.

## Admin review moderation

After migration and deployment, administrators can open **My space & tools → Admin dashboard → Food & Travel reviews** or visit `/admin/directory-reviews`. Approve only relevant, genuine, non-abusive reviews. Rejected and pending reviews are not shown publicly and are not included in structured data.

## Publishing useful pages

A directory listing is not automatically eligible for indexing just because it exists. For Food pages, add a substantial description, location, cuisine or menu highlights, price or opening-hours information, and an official/provider source link. For Travel pages, add a substantial description, location, attractions, best season, a budget breakdown or itinerary/daily budget, and an official/provider source link.

The sitemap route `/sitemap.xml` is generated dynamically from complete active listings and qualifying location pages. The previous static `public/sitemap.xml` was removed so it cannot shadow the dynamic Flask route. `public/robots.txt` points crawlers to the correct new domain's sitemap.

## Important SEO limitation

This makes pages understandable, crawlable and information-rich, but it cannot guarantee that Google will index them, show rich results, rank them for a specific phrase, or display review stars. Indexing and ranking depend on Google's systems and the usefulness, originality, accuracy, authority and competition of each page. Submit the sitemap in the `gathercommunity.me` Search Console property and monitor indexing and performance there.

## Files changed

- `app.py`
- `templates/base.html`
- `templates/directory_home.html`
- `templates/directory_create.html`
- `templates/directory_edit.html`
- `templates/directory_detail.html`
- `templates/directory_location.html` (new)
- `templates/admin_directory_reviews.html` (new)
- `static/css/style.css`
- `robots.txt` and `public/robots.txt`
- `migrations/20261107_food_travel_search_upgrade.sql` (new)
- This README and Food/Travel phase notes

No `.env`, `.venv`, or production secrets are included in this archive.
