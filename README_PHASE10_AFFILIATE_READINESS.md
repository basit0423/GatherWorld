# Gather World — Phase 10 Preparation: Affiliate Readiness

This is the first Phase 10 preparation update, not the complete marketplace. It prepares the public information pages and a private partner-application tracker while Daraz and Amazon applications are awaiting decisions.

## Included
- Persistent Light/Dark theme toggle (saved in the browser for all pages).
- Dedicated About, Contact, Privacy, Terms and Affiliate Disclosure pages.
- Public Partners directory (shows only approved partners with an authorized tracking URL).
- Shopping pre-launch page at `/shop`; it does not show fake products or unapproved buy links.
- Admin-only Affiliate Partner Tracker at `/admin/affiliate-partners`.
- 11 partner programmes tracked: Daraz Pakistan and Amazon Associates preloaded as `Applied` based on the supplied status; eBay, CJ, Awin, Impact, Admitad, Namecheap, Hostinger, Envato Market and Booking.com are preloaded as `Research` candidates only. No affiliate tracking links are included.
- Admin dashboard shortcut to the private partner tracker.

## Safe installation
1. Back up `E:\GatherWorld` and your Neon database.
2. Extract this ZIP to a temporary folder.
3. Copy its contents into `E:\GatherWorld`, replacing matching files.
4. Keep your existing `.env` and `.venv` unchanged; neither is included.
5. Run `python app.py` so `init_db()` creates the additive `gw_affiliate_partners` table and seeds the two submitted programmes if they are not already present.

## Local test
- Open `/about`, `/contact`, `/privacy`, `/terms`, `/affiliate-disclosure`, `/partners` and `/shop`.
- Use the theme button in the menu; reload and confirm your choice remains saved.
- Sign in as the configured administrator and open `/admin/affiliate-partners`.
- Confirm Daraz Pakistan and Amazon Associates show `Applied`.
- Change a test partner status and save it.
- Do not add affiliate URLs until the relevant programme has actually approved the application and issued the approved tracking link.
- Confirm `/partners` only lists approved partners that have tracking URLs.

## Partner research checked on November 2, 2026
Official programme references: Daraz Pakistan affiliate entry page; Amazon Associates; eBay Partner Network; CJ publisher sign-up; Awin partner network; Impact publisher programme; Admitad publisher/creator sign-up; Namecheap affiliates; Hostinger affiliates; Envato Market affiliate programme; and Booking.com affiliate programme. Programme terms, region coverage, account eligibility, payment methods and advertiser-level approval must be checked before applying. A network account does not automatically approve an individual advertiser programme.

## Legal and programme note
The legal pages are practical drafts, not legal advice or a certification of compliance. Review them for the real operating entity, data retention, cookies, hosting providers, applicable jurisdictions and contact arrangements before public launch. Affiliate programme applications, contracts and payout arrangements must be handled by a person legally eligible to accept those terms.

## Scope
This update prepares Phase 10. It does not yet implement product catalogue feeds, checkout, shopping cart, commissions, or retailer API integrations. Those should be added only after actual affiliate approvals and link/feed documentation are available.
