GATHER WORLD — PHASE 6: GLOBAL DISCOVERY & SEARCH

This package builds on Phase 5 and includes all earlier phases. It adds:
- Explore hub at /explore.
- Global search at /search across verified active members, public posts and discoverable communities.
- Trending hashtag topics derived from public posts from the last 30 days.
- Topic pages at /topics/<slug>.
- Suggested accounts, public communities and popular/recent posts.
- Explore and Search links inside the compact Discover navigation.
- Search input and responsive result cards.

TOPIC FORMAT
Add hashtags to the body/caption of public posts, e.g. #gaming #photography. Tags use letters, numbers and underscores and must be 2–30 characters. Trend aggregation is based on recent post text; there is no paid/promoted ranking in this phase.

LOCAL INSTALL
1. Back up E:\GatherWorld and your Neon database.
2. Extract the ZIP to a temporary folder.
3. Copy the extracted contents into E:\GatherWorld, replacing matching files.
4. Keep your existing .env and .venv unchanged.
5. Run the project locally: python app.py
6. Test /explore, /search?q=gaming and /topics/gaming.

SEARCH PRIVACY
- Suspended accounts are excluded from results.
- Private communities only appear to their current members.
- Users blocked in either direction are excluded from people/posts search results.
- The search is parameterized; search text is treated as data, not SQL.

This phase does not include AI ranking, geolocation search, search-engine indexing of private content, sponsored ranking, or external search providers. It does not alter payment, affiliate, marketplace or messaging flows.

No deployment is performed by this package. Local Neon and browser testing remains necessary.
