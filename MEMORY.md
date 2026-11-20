# Framez Events & Productions (`framez.sg`) - Master Project & Monthly Reporting Memory

Last verified: 2026-11-18
Billing & Reporting Cadence: **15th of each month to 15th of the next month** (retainer paid monthly; client report presented every cycle close around the 14th/15th).

## 1. Client Identity & Business Scope

* **Brand:** Framez Events & Productions
* **Legal Entities:** Frame Events and Productions Private Limited (India HQ) / Frame Events & Productions Pte. Ltd. (Singapore)
* **Canonical Website:** https://framez.sg (non-www, HTTPS, extensionless URLs)
* **Core Services:** B2B corporate event management, MICE (Meetings, Incentives, Conferences, Exhibitions), product launches, executive CXO summits, employee annual days & awards nights, corporate family day carnivals, exhibition stall fabrication, and experiential brand activations.
* **Certifications:** ISO 9001:2015 (Quality Management) and ISO 27001:2013 (Information Security).
* **Verified Offices:**
  * **Singapore Office:** 30 Cecil Street, #19-08 Prudential Tower, Singapore 049712
  * **India HQ (Bengaluru):** B/2, Ganga, 3rd Floor, 5th Block, KHB Colony, Koramangala, Bengaluru, Karnataka 560095
* **Lead Routing:** `info@framez.sg`, `framez.events@gmail.com`, `+91 94480 66560`, and floating WhatsApp sales widget (`footer.php` + `index.html`).

## 2. Infrastructure, Access & Credentials Map

* **Operations Server (SSH):** `ssh root@72.61.173.127` (passwordless SSH key configured on Mac).
  * **GitHub Repository:** `https://github.com/princejain756/framezseo` (public canonical repo tracking all SEO/GEO engine code, daily action logs, telemetry snapshots, and cycle reports; auto-committed and pushed after every cron run).
  * **Portal & Env Root:** `/root/websites/seogeoopt/` (`https://portal.adelev8.com`, PM2 service `adelev8-growth-os-api` on port `5182`).
  * **Runtime Secrets File:** `/root/websites/seogeoopt/.env` holds `CPANEL_HOST`, `CPANEL_USERNAME`, `CPANEL_API_TOKEN`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`. Never commit or print raw tokens into repo files.
  * **Portal OAuth Store:** `/root/websites/seogeoopt/server/data/portal.json` (Framez Brand ID: `brand-5c9dceab-e42e-48da-87e2-7e71216cb5cf`).
  * **Live Daily SEO & Cycle Cron:** `/root/websites/seogeoopt/seo-jobs/framez/` driven by `/etc/cron.d/framez-seo` twice daily (`04:15 UTC` / `12:15 SGT` and `19:30 UTC` / `03:30 SGT`, `flock`-locked).
  * **Client Reports & PDF Renderers:** `/root/websites/seogeoopt/DocMaker/` and `/root/websites/seogeoopt/Framez/`.
  * **Self-Hosted SERP/SEO Suite:** `/root/websites/openseo/` (`seo.prince.sh`).
* **Production Web Host (cPanel):** `https://framez.sg:2083` (`public_html/`), IP `158.106.136.106`, Apache/LiteSpeed with `ea-php74___lsphp` handler in `.htaccess` (CRITICAL: always preserve the cPanel `AddHandler` block at the bottom of `.htaccess`!).
* **Browser Access (`/ego-browser` ONLY):**
  * Google session **`/u/0/` (`princejain756@gmail.com`)** has verified owner access to:
    * **Google Search Console:** Domain property **`sc-domain:framez.sg`** (always query `sc-domain:framez.sg`, NOT `https://framez.sg/`).
    * **Google Analytics 4:** Account `402211702`, Property **`547082278`**, Measurement ID **`G-XDPHV6MX44`** (never use dead `UA-180350188-1` or old `G-R3EVYE346M`).
    * **Google Business Profile:** Location ID `1064671895591739893`.

## 3. Non-Negotiable Operational & Reporting Rules

1. **Zero Fabricated Metrics or Backdating:** Never invent traffic, rankings, leads, reviews, AggregateRating stars, client revenue, or AI citations. Distinguish technical delivery dates from measured search/lead outcomes.
2. **Never Disclose Client Revenue Figures:** Never include client revenue, ticket sales totals, or INR/USD income numbers in any report, case study, or page. Non-revenue operational metrics (impressions, clicks, active users, sessions, verified form leads, blocked bot counts, URLs indexed) are allowed.
3. **4-Step Safe cPanel Deployment:** (1) Download live file to timestamped backup with SHA-256 manifest -> (2) Modify & validate JSON-LD, HTML/PHP, title `<= 60`, description `<= 160`, single `G-XDPHV6MX44` -> (3) Upload via cPanel `Fileman/save_file_content` -> (4) Verify SHA-256 read-back + live HTTPS `200`/`301` + push changed URLs via IndexNow (`59951843f48f4e09a34b4f61a08fd59c`).
4. **Preserve Lead & Security Stack:** Never delete or expose `leads_log.json` or `leads_spam_log.json` (log aggregate counts only, zero PII in reports). Never weaken Cloudflare Turnstile (`0x4AAAAAAExBdPWHAqYTWVlc`), honeypot fields, rate-limiting, CSP headers, or `POST` exclusions on `contact-submit.php` and `submit-demo.php`.
5. **Continuous Multi-Wave Monthly Delivery (`15th to 15th`):** Every monthly cycle must show steady, verifiable work across all four weeks rather than a single one-day dump followed by idle weeks. Every cron run and wave deployment logs a timestamped cryptographic receipt in `reports/cycle-<START>_to_<END>-ledger.jsonl`.

## 4. Chronological History of Completed Cycles

### Cycle 1-3: 14 July 2026 to 14 November 2026 (Foundation & 90-Day Turnaround)
* **Jul-Aug 2026:** Fixed `ReferenceError: validateMessage` bug that was dropping 100% of form enquiries; built `contact-submit.php` + `submit-demo.php` + fail-safe `leads_log.json`; took down hijacked `tallyprimelaunch.framez.sg` subdomain serving Indonesian `"toto868"` gambling spam; restored broken subpage CSS/JS; fixed 5 pages canonicalizing to `/blog`.
* **Sep 2026:** Deployed 7-layer bot defense (Cloudflare Turnstile, honeypots, rate limits, HTTP 403 on logs, HSTS, CSP); published 8 enterprise B2B handbooks.
* **15 Oct - 14 Nov 2026 Cycle (Major Oct 26 Release):** Shipped 27 files: rewrote `/event-management-company-in-bangalore` away from virtual events, updated 13 core pages, fixed mobile header nav, published 4 practical guides (Budget, Annual Day, ROI, Singapore Checklist), cleaned `robots.txt` + `llms.txt` + `sitemap.xml` (26 URLs).
* **90-Day Verified Baseline (as of Oct 27):** 29,108 GSC impressions, 249 clicks, 1.31% 30d CTR, 1,240 GA4 active users, 12,450 GBP impressions (536 GBP actions: 84 calls, 142 directions, 310 website clicks), 12,067 LinkedIn organic impressions.

### Cycle 4 (Active): 15 November 2026 to 15 December 2026

#### Baseline Observed at Cycle Start (18 Nov 2026 Live Audit)
* **GSC 28d (`2026-10-20` to `2026-11-16`, `sc-domain:framez.sg`):** `81` clicks, `7,625` impressions, `1.06%` CTR, avg position `41.0` (`7d`: `22` clicks, `1,977` impressions, `1.11%` CTR, pos `39.8`).
* **Geographic Discovery:** Singapore generated **`4,471` impressions (`58.6%` of site total) with only `1` click (`0.02%` CTR, pos `50.0`)** because `framez.sg` lacked a dedicated Singapore commercial landing page. India generated `1,921` impressions and `73` clicks (`3.80%` CTR, pos `28.9`), with `corporate event management companies in bangalore` climbing from `#35.1` to **`#19.4`**.
* **GA4 Discovery (`547082278`):** `365` active users, `437` sessions (`113` Organic Search), `520` pageviews, `2` `generate_lead` events (`keyEvents` showed `0` because `generate_lead` was unstarred, and **10 core commercial/contact pages were missing `G-XDPHV6MX44`**!).
* **Leads & Bot Defense (as of 18 Nov):** `3` verified form leads in `leads_log.json`; `251` bot submissions blocked (`4` blocked since Nov 15).

#### Shipped & Scheduled Waves in Cycle 4 (15 Nov - 15 Dec 2026)
1. **15-17 Nov (Foundation):** Turnstile active screening; `/etc/cron.d/framez-seo` installed; 15-page meta/OG/alt repairs; Health & Safety page added to sitemap (`27` URLs).
2. **18 Nov (Wave 1 - LIVE & SHA-256 Verified, 24 files):**
   * Launched `/event-management-company-in-singapore` (`HTTP 200`, linked in homepage hero bar, sitewide footer, `blog.php`, `llms.txt`, `sitemap.xml` -> `28` URLs, `image-sitemap.xml` -> `7` images).
   * Rebuilt `/event-marketing-services` (was *Crawled - currently not indexed*), `/event-management-company-in-india` (removed 2020 filler & white-on-white HTML bug), and `/event-planner` (`+105%` impression surge page).
   * Unified `G-XDPHV6MX44` across all `28/28` sitemap pages + added `whatsapp_click`, `phone_click`, `email_click`, `cta_inquiry_click` listeners + starred **`generate_lead`** as a GA4 Key Event.
   * Removed policy-violating fake `Product`/`AggregateRating` schema on Health & Safety; added Dual-HQ (Singapore Prudential Tower + Bengaluru) `Organization` schema in `header.php` & `index.html`; fixed `footer.php` `"Bangalore Event Management"` anchor to point to `/event-management-company-in-bangalore`.
   * Added `301` redirects (`/get-to-know-us` -> `/about-us`, `/our-team` -> `/about-us`, `/social-event` -> `/our-events-and-services`), universal `.php` -> extensionless `301`, and `X-Robots-Tag: noindex, noarchive` on legacy microsite directories & cPanel subdomains (`nps2025.framez.sg`, `qr-registration.framez.sg`).
   * Reconnected Google OAuth on `portal.adelev8.com` (`gsc: ok`, `ga4: ok`), re-submitted `sitemap.xml` (`28` URLs) & `image-sitemap.xml` (`7` images) in GSC, pushed `28` URLs to IndexNow (`HTTP 200`), and requested GSC indexing for `/event-management-company-in-singapore` and `/event-marketing-services`.
   * **OpenDesign DeepSeek v4.1 Flash Normal Engine & Daily Automation Active:** Integrated `daily_actions.py` and `deepseek_daily_seo.py` powered by `opendesign/deepseek-v4.1-flash` (strictly normal edition, never eco; Base URL: `https://amr-link.open-design.ai/v1/chat/completions`, Key: `/root/.commandcode/opendesign-api-key.secret`). Executes a verified production deliverable on `framez.sg` every single day of the 30-day billing cycle (15 Nov to 15 Dec 2026): major content waves on wave dates (Nov 21, 25, 29, Dec 3, 7) and verified on-page micro-optimizations on all other dates (e.g. 20 Nov resolved thin content and added `FAQPage` schema on `/clientele.php`). Every change is backed up with SHA-256, verified HTTP 200, pushed to IndexNow, audited by OpenDesign DeepSeek v4.1 Flash, recorded in `reports/daily-action-log.jsonl` and the cycle ledger, and reflected in Section 2 of `FRAMEZ_NOVEMBER_DECEMBER_2026_SEO_AEO_GEO_REPORT.md`. Both `framez_seo_cron.py all` and standalone commands (`python3 framez_seo_cron.py daily_action`, `python3 framez_seo_cron.py deepseek`) are live and verified.
3. **21 Nov (Wave 2 - Auto-Cron):** `/conference-and-mice-event-management` targeting `conference management company` (`#26.1`) & `conference event planning companies` (`#39.8`).
4. **25 Nov (Wave 3 - Auto-Cron):** `/exhibition-and-trade-show-management` targeting `exhibition management company` (`#30.4`) & custom trade-show booth fabrication in SG & BLR.
5. **29 Nov (Wave 4 - Auto-Cron):** `/year-end-corporate-town-hall-and-kickoff-guide` targeting Q4 year-end town halls & Q1 Sales Kickoffs (SKOs).
6. **03 Dec (Wave 5 - Auto-Cron):** `/bangalore-corporate-event-venue-and-logistics-checklist` pushing Bangalore commercial keywords from Page 2 (`#19.4`) to Page 1.
7. **07 Dec (Wave 6 - Auto-Cron):** `/sustainable-corporate-events-esg-guide-singapore-india` targeting Singapore Green MICE & MNC ESG RFP criteria.
8. **14-15 Dec (Cycle 4 Closeout & Presentation):** Present compiled report from `/root/websites/seogeoopt/DocMaker/FRAMEZ_NOVEMBER_DECEMBER_2026_SEO_AEO_GEO_REPORT.md` (and render PDF via Puppeteer in `DocMaker/`), freeze Dec 15 baseline snapshot, and queue Cycle 5 (`15 Dec 2026 - 15 Jan 2027`) waves.

## 5. Monthly Report Compilation Checklist (Run Every 14th/15th)

1. SSH to `root@72.61.173.127` and run:
   ```bash
   cd /root/websites/seogeoopt/seo-jobs/framez
   python3 framez_seo_cron.py all
   python3 framez_seo_cron.py status
   ```
2. Verify `gsc: "ok"` and `ga4: "ok"`. If `reauth_required`, open `/ego-browser` (`/u/0/` `princejain756@gmail.com`) and re-authorize via `portal.adelev8.com` Google OAuth.
3. Inspect `/root/websites/seogeoopt/DocMaker/FRAMEZ_<CYCLE>_SEO_AEO_GEO_REPORT.md` and `reports/cycle-<START>_to_<END>-ledger.jsonl` to confirm all scheduled waves, GSC country/query deltas, GA4 organic sessions & key events (`generate_lead`, `whatsapp_click`, `phone_click`), and blocked-bot counts are up to date.
4. Export annotated GSC/GA4 screenshots via `/ego-browser` if visual appendix plates are needed, render the client PDF in `/root/websites/seogeoopt/DocMaker/`, sync local `MEMORY.md` + `docs/`, and stage the next 4-to-6 waves for the upcoming `15th -> 15th` cycle.
