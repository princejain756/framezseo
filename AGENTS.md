# Framez Events & Productions (`framez.sg`) Workspace Rules

Always read [MEMORY.md](./MEMORY.md) at the start of every task in this workspace and update [MEMORY.md](./MEMORY.md) whenever new SEO/GEO waves, server changes, analytics updates, or monthly reports are completed.

## Critical Facts & Guardrails

1. **Client & Billing Cycle:**
   * **Client:** Framez Events & Productions (`https://framez.sg`), managed via ADELEV8 Growth OS (`https://portal.adelev8.com`).
   * **Monthly Reporting Cycle:** **15th to 15th of next month** (e.g., `15 Nov - 15 Dec`, `15 Dec - 15 Jan`). Every cycle requires a multi-day staggered execution trail logged in the server ledger and presented in an honest, evidence-backed monthly report.

2. **Servers & Browser Sessions:**
   * **Operations Server:** `ssh root@72.61.173.127`
     * Cron & SEO engine: `/root/websites/seogeoopt/seo-jobs/framez/` (`/etc/cron.d/framez-seo` runs twice daily at `04:15 UTC` and `19:30 UTC`).
     * Reports & PDF scripts: `/root/websites/seogeoopt/DocMaker/` and `/root/websites/seogeoopt/Framez/`.
     * Credentials: read at runtime from `/root/websites/seogeoopt/.env` and `/root/websites/seogeoopt/server/data/portal.json`. Never hardcode or commit raw secrets locally.
   * **Browser Automation:** `/ego-browser` only, using Google slot **`/u/0/` (`princejain756@gmail.com`)**:
     * **Search Console property:** `sc-domain:framez.sg` (Domain property; never use `https://framez.sg/`).
     * **GA4 property:** `547082278` (Account `402211702`), Measurement ID **`G-XDPHV6MX44`**.
     * **GBP location:** `1064671895591739893`.

3. **Production Safety on `framez.sg` (cPanel `public_html/`):**
   * Always download & SHA-256 back up live files before uploading via cPanel `Fileman/save_file_content`.
   * **Never remove** the `AddHandler application/x-httpd-ea-php74___lsphp` block at the bottom of `public_html/.htaccess`.
   * **Never weaken** Cloudflare Turnstile, honeypots, rate limits, CSP, or `POST` form exclusions on `contact-submit.php` and `submit-demo.php`.
   * **Never log PII** from `leads_log.json` or `leads_spam_log.json` (aggregate counts and timestamps only).
   * **Never invent** traffic, rankings, leads, reviews, `AggregateRating` markup, or AI citations, and **never disclose client revenue figures**.

## Local Reference Files

* [MEMORY.md](./MEMORY.md) - Canonical project history, baselines, active cycle waves, and monthly report checklist
* [docs/01-company-and-site-architecture.md](./docs/01-company-and-site-architecture.md) - Site inventory & PHP/cPanel stack
* [docs/02-infrastructure-and-access-map.md](./docs/02-infrastructure-and-access-map.md) - Server paths, cPanel workflow & `ego-browser` map
* [docs/03-live-seo-gsc-ga4-baseline-2026-11-18.md](./docs/03-live-seo-gsc-ga4-baseline-2026-11-18.md) - Nov 18 forensic baseline
* [docs/04-nov-dec-2026-cycle-roadmap-and-cron.md](./docs/04-nov-dec-2026-cycle-roadmap-and-cron.md) - Nov 15 - Dec 15 schedule & cron commands
* [scripts/](./scripts/) - Local mirror of `content_pages.py`, `wave1_deploy.py`, `framez_seo_cron.py`, and `generate_nov_dec_report.py`
