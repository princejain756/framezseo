# 03 :  Live SEO, GSC & GA4 Baseline + Root-Cause Diagnosis (2026-11-18)

## 1. Historical Context (Jul 14  to  Nov 17, 2026)

1. **Jul 14  to  Aug 2026 (Emergency Rescue):**
   - Repaired broken enquiry forms (`ReferenceError: validateMessage` was dropping 100% of leads); deployed `contact-submit.php` + `submit-demo.php` + `leads_log.json`.
   - Took down hijacked `tallyprimelaunch.framez.sg` subdomain serving Indonesian `"toto868"` gambling spam.
   - Restored broken subpage CSS/JS assets, fixed 5 pages canonicalizing to `/blog`, connected GA4 + GSC + GBP.
2. **Sep 2026 (Security & Authority Handbooks):**
   - Deployed 7-layer bot defense (Cloudflare Turnstile, honeypots, rate limits, 403 on lead logs :  192+ bots blocked).
   - Published 8 long-form B2B handbooks (`TechArticle` + `FAQPage` + `HowTo`).
3. **Oct 26, 2026 (Major Search Growth Release):**
   - Deployed 27 files: overhauled 13 core pages, rewrote `/event-management-company-in-bangalore` away from legacy virtual-event copy, fixed mobile nav, published 4 new buyer-intent guides (Budget, Annual Day, ROI, Singapore Checklist), cleaned `robots.txt` + `llms.txt` + `sitemap.xml` (26 URLs).
4. **Nov 17, 2026 (Automated SEO Cron & On-Page Polish):**
   - Installed `/etc/cron.d/framez-seo` on `72.61.173.127`.
   - Reconciled `sitemap.xml` to **27 URLs** (repaired and added `/Framez-Public-Statement-on-Health-and-Safety-Commitment`), fixed missing `meta robots`, OG/Twitter tags, duplicate/empty image `alt` attributes, and tightened 15 page titles/descriptions.

---

## 2. Live Google Search Console Telemetry (`sc-domain:framez.sg`, pulled 2026-11-18)

### A. Overall Search Performance
| Window | Clicks | Impressions | Avg CTR | Avg Position | Total Distinct Queries |
| --- | ---: | ---: | ---: | ---: | ---: |
| **Last 3 Months** (Aug 16  to  Nov 15, 2026) | **246** | **25,300** | **1.0%** | **37.4** | 918 |
| **Last 28 Days** (Oct 19  to  Nov 15, 2026) | **83** | **7,830** | **1.1%** | **40.8** | 441 |

### B. Country Split (Last 28 Days :  Critical Finding!)
| Country | Clicks | Impressions | CTR | Diagnosis |
| --- | ---: | ---: | ---: | --- |
| **Singapore** | **1** | **4,577** | **0.02%** | **58.5% of all impressions, almost zero clicks!** `.sg` ccTLD gives automatic Singapore visibility, but Framez has **no dedicated commercial `/event-management-company-in-singapore` landing page**, and generic pages rank on Page 4 to 7 or show Bangalore-heavy copy. |
| **India** | **75** | **1,986** | **3.78%** | Strong brand CTR + rising Page-2 rankings for Bangalore commercial queries. |
| **United States** | 1 | 382 | 0.26% | Informational handbook impressions + bot/VPN impressions. |
| **United Kingdom** | 1 | 130 | 0.77% | Informational handbook impressions. |

### C. Top Pages (Last 28 Days)
| Page | Clicks | Impressions | Notes |
| --- | ---: | ---: | --- |
| `https://framez.sg/` | 62 | 722 | Brand query anchor (8.6% CTR) |
| `https://framez.sg/corporate-event-management-company` | 6 | **5,080** | **65% of all site impressions (0.12% CTR)** :  absorbs redirected virtual-event queries + Singapore/Bangalore head terms |
| `https://framez.sg/get-to-know-us` | 5 | 299 | **Legacy 2021 page** (excluded from sitemap, competing with `/about-us`!) |
| `https://framez.sg/our-events-and-services` | 4 | **1,942** | Absorbs redirected virtual-event platform queries + broad service queries |
| `https://framez.sg/our-team` | 2 | 52 | Legacy 2021 page |
| `https://framez.sg/get-in-touch` | 1 | 168 | Contact page |
| `https://nps2025.framez.sg/` | 1 | 51 | **Client event subdomain indexed in Google!** |
| `https://framez.sg/festive-corporate-gala-diwali-celebrations` | 1 | 31 | Seasonal guide traction |
| `https://framez.sg/experiential-brand-activations-framework` | 1 | 16 | Guide traction |
| `https://framez.sg/event-planner` | **0** | **1,205** | **Impressions up +105%** (flagged by GSC Insights), 0 clicks! |

### D. Query Anatomy (Last 28 Days :  Sorted by Impressions & Commercial Value)

#### 1. Commercial Target Queries Moving Toward Page 1 (High Priority!)
- `corporate event company` :  **Pos 15.3** (56 imp, 0 clicks :  striking distance of Page 1!)
- `corporate event management companies in bangalore` :  **Pos 19.4** (62 imp, 1 click :  **jumped from Pos 35.1 → 19.4** after Oct 26 release!)
- `conference management company` :  **Pos 26.1** (112 imp, 0 clicks)
- `exhibition management company` :  **Pos 30.4** (44 imp, 0 clicks)
- `corporate events agency` :  **Pos 32.4** (56 imp, 0 clicks)
- `corporate event management company in bangalore` :  **Pos 33.3** (15 imp, 1 click :  improved from Pos 40.9!)
- `conference event planning companies` :  **Pos 39.8** (117 imp, 0 clicks)

#### 2. Brand Queries (Healthy)
- `frames event management` :  Pos **1.3** (5 clicks / 22 imp, 22.7% CTR)
- `framez events` :  Pos **1.2** (4 clicks / 19 imp, 21.1% CTR)
- `framez` :  Pos **3.0** (2 clicks / 30 imp)
- `frame events` :  Pos **3.5** (1 click / 34 imp)
- `frame events and productions` :  Pos **6.5** (32 clicks / 141 imp, 22.7% CTR)

#### 3. Legacy "Virtual Event" Ghost Impressions Dragging Down CTR & Topical Authority
- `online event management companies` (595 imp, Pos 25.4), `virtual event management companies` (582 imp, Pos 43.6), `virtual event management services` (532 imp, Pos 69.6), `virtual event companies` (436 imp, Pos 69.9), `virtual event company` (353 imp, Pos 84.5), `virtual event company singapore` (255 imp, Pos 79.9).
- **Why this happens:** Old 2020 to 2021 virtual-event URLs 301-redirect into `/corporate-event-management-company` and `/our-events-and-services`, AND **20+ legacy virtual-event client subdomains** are still live and indexed under `*.framez.sg`.

---

## 3. Indexing, Sitemaps, Links & GA4 Health (2026-11-18)

### A. Page Indexing (`sc-domain:framez.sg`) :  **52 Indexed / 42 Not Indexed**
- **26 of 27 sitemap URLs are indexed** :  only **`https://framez.sg/event-marketing-services` is missing from the 52 indexed URLs**! (And `/event-management-company-in-india` hasn't been recrawled since **17 Jul 2026**!)
- **21 Subdomain / Junk URLs polluting the 52 Indexed count:**
  - `itdachieversaward.framez.sg/`, `nps2025.framez.sg/`, `nps2025.framez.sg/register.html`, `hvpartnersummit2024.framez.sg/`, `hvpartnersummit2022.framez.sg/`, `tctindia2021.framez.sg/`, `milestone.engage2021.framez.sg/`, `cloud4c-registration2.framez.sg/`, `cloud4c.framez.sg/`, `dvconindia.framez.sg/`, `dvconindia.framez.sg/pages/main`, `santhigram.framez.sg/`, `igniteaps2024.framez.sg/`, `edcastfow.framez.sg/`, `tssglobal.framez.sg/`, `tssglobal.framez.sg/?source=cms`, `suc.framez.sg/`, `iitbayarea.framez.sg/`, `netradynejamboree2023.framez.sg/`, `qr-registration.framez.sg/`, `warriorclub2023.framez.sg/`, plus malformed `https://framez.sg/framez-greetings.framez.sg/`.
- **3 Legacy 2021 Pages Indexed:** `/get-to-know-us`, `/our-team`, `/social-event`.
- **2 PDF Certificates Indexed:** `/FRAMEZ ISO 27001 Certificate.pdf`, `/FRAMEZ ISO 9001 Certificate.pdf`.
- **42 Not Indexed Breakdown:**
  - 11 `Crawled - currently not indexed` (includes `/event-marketing-services` and legacy variants)
  - 10 `Page with redirect`, 8 `Excluded by noindex`, 7 `Not found (404)`, 3 `Alternative page with proper canonical`, 1 `Redirect error`, 1 `Duplicate without user-selected canonical`, 1 `Discovered - currently not indexed`.

### B. Sitemaps & GSC Security Hygiene
- GSC has **4 sitemaps** listed: `https://framez.sg/sitemap.xml` (26 discovered, last read Nov 13), `https://framez.sg/image-sitemap.xml` (4 discovered, last read Nov 16), plus stale `https://www.framez.sg/sitemap.xml` (from 2024) and `http://framez.sg/sitemap.xml` (from 2020).
- GSC flags **21 unused ownership verification tokens** on `framez.sg` (leftover historical verification tags/files/DNS records).

### C. Backlink Profile (GSC Links + DataForSEO)
- **GSC External Links:** 326 total links (244 to `/`, 30 to `/our-events-and-services`, 25 to `/corporate-event-management-company`, 13 to `/event-planner`, 10 to `/blog`).
- **Top Linking Domains in GSC:** `tumblr.com` (57), `google.com` (44), `sitelike.org` (29), `mastodon.org.uk` (27), `linkedin.com` (20) :  **very weak editorial/local B2B authority** in Singapore and Bangalore.

### D. Google Analytics 4 (`p547082278`, Last 7 Days: Nov 11 to 17, 2026)
- **Active users:** 119 (+65.3%), **Views:** 155 (+38.4%), **Organic Search sessions:** 30 (+11.1%), **Organic Social:** 6 (+200%).
- **Key Events:** **`0`** :  GA4 conversion tracking (`generate_lead`, WhatsApp clicks, `tel:` clicks, `mailto:` clicks) is **not configured/marked as Key Events** in GA4 Admin!

---

## 4. Specific Technical & Strategic Gaps Identified Today

1. **Missing Singapore Commercial Money Page (Biggest Revenue Gap):**
   - `framez.sg` gets **4,577 impressions/month in Singapore with 1 click**, yet has no `/event-management-company-in-singapore` (or `/corporate-event-management-singapore`) service page with Prudential Tower address, `LocalBusiness` Singapore schema, Singapore venue/MICE proof, and internal links.
2. **21 Indexed Client Event Subdomains (`*.framez.sg`):**
   - Old 2020 to 2025 virtual/microsite subdomains are indexed in Google, bleeding crawl budget, reinforcing "virtual event platform" topical signals, and creating security/hijack surface. They need `X-Robots-Tag: noindex` (or archival/decommissioning where no longer active).
3. **Legacy Page Cannibalization (`/get-to-know-us`, `/our-team`, `/social-event`):**
   - `/get-to-know-us` (2021 template) still steals 299 impressions & 5 clicks from `/about-us`. Needs a clean decision (`301` → `/about-us`, etc.).
4. **Schema & On-Page Bugs on Live Site:**
   - `/Framez-Public-Statement-on-Health-and-Safety-Commitment` outputs invalid/mismatched `@type: "Product"` JSON-LD!
   - `/corporate-event-trends-singapore` lacks `Article` and `BreadcrumbList` JSON-LD.
   - 3 page `<title>` tags still exceed 60 chars (`corporate-event-planning-handbook-2027` = 63, `corporate-family-day-carnival-safety-logistics` = 61, `corporate-event-trends-singapore` = 61).
   - 5 core pages still use legacy `all,index,follow` instead of `index, follow, max-image-preview:large, max-snippet:-1, max-video-preview:-1` (including homepage missing `max-snippet:-1, max-video-preview:-1`).
5. **`.htaccess` Extensionless Redirect Gap:**
   - `.htaccess` only 301-redirects `.php` → extensionless for 16 slugs; the other 11 `.php` pages in the 27-URL sitemap can still serve HTTP 200 at `.php` if hit directly.
6. **`/event-marketing-services` Not Indexed & `/event-management-company-in-india` Stale Crawl (Jul 17):**
   - Both need internal link reinforcement from high-crawl pages (`/`, `/our-events-and-services`, `/corporate-event-management-company`) + GSC URL Inspection / Request Indexing.
7. **Cron & Portal GSC Integration Bug on `72.61.173.127`:**
   - `/root/websites/seogeoopt/seo-jobs/framez/config.json` has `"gsc_site": "https://framez.sg/"` instead of `"sc-domain:framez.sg"`, and `portal.json` OAuth token returns `invalid_grant`.
8. **Missing Commercial Cluster Pages & Proof Assets:**
   - High-impression non-brand queries (`conference management company` :  112 imp @ #26.1, `conference event planning companies` :  117 imp @ #39.8, `exhibition management company` :  44 imp @ #30.4) have no dedicated conference/MICE or exhibition service pages, and `/clientele` has logos without named case-study proof pages.
