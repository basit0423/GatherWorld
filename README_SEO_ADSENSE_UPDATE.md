GATHER WORLD — VERCEL SEO DEPLOYMENT FIX
=======================================

Production domain: https://gathercommunity.me

SEO files are included in both the project root and Vercel's public/ directory.
Vercel serves public/ files from the URL root, so the following should be available:
- https://gathercommunity.me/ads.txt
- https://gathercommunity.me/robots.txt
- https://gathercommunity.me/sitemap.xml

The Flask app also retains /ads.txt, /robots.txt, and /sitemap.xml routes.
The sitemap includes only real top-level application routes present in this project.

Vercel project setup:
- This project should be the new GatherWorld Vercel project.
- Assign gathercommunity.me to this project only.
- Keep social.gathercommunity.me assigned to the separate old Gather project.
- Set PUBLIC_BASE_URL=https://gathercommunity.me in this project's Production environment.
- Ensure Root Directory is ./ and redeploy the Production deployment after committing these files.

Do not add the old social subdomain to this project. Each production domain should
belong to the project whose site it is meant to serve.
