# 04 :  Nov 15  to  Dec 15, 2026 Master SEO · GEO · AEO Execution & Automated Cron Plan

## 1. Billing & Reporting Cycle Parameters
- **Active Service Cycle:** **15 November 2026  to  15 December 2026** (15th to 15th monthly cadence)
- **Live Report Auto-Compiled To:** `/root/websites/seogeoopt/DocMaker/FRAMEZ_NOVEMBER_DECEMBER_2026_SEO_AEO_GEO_REPORT.md` on `root@72.61.173.127`
- **Immutable Cryptographic Ledger:** `/root/websites/seogeoopt/seo-jobs/framez/reports/cycle-2026-11-15-to-2026-12-15-ledger.jsonl`

---

## 2. Multi-Wave Execution Calendar (Continuous 30-Day Cadence)

Every wave is backed up prior to upload, verified via SHA-256 read-back + live HTTPS `200`/`301` checks + JSON-LD & GA4 validation, pushed to IndexNow (`59951843f48f4e09a34b4f61a08fd59c`), reconciled into `sitemap.xml`, and recorded in the immutable ledger:

| Date | Cycle Day | Wave | Shipped / Scheduled Deliverable | Target Outcome |
| --- | :---: | --- | --- | --- |
| **15 to 17 Nov** | Days 1 to 3 | **Foundation** | 7-layer Turnstile defense (4 bots blocked since Nov 15; 251 cumulative); `/etc/cron.d/framez-seo` installed; 15-page meta/OG/alt cleanup | Clean technical baseline & automated monitoring |
| **18 Nov** | Day 4 | **Wave 1 (LIVE)** | **24 files SHA-256 verified:**<br>• Launched `/event-management-company-in-singapore` (Prudential Tower SG commercial page)<br>• Rebuilt `/event-marketing-services`, `/event-management-company-in-india` & `/event-planner`<br>• Unified `G-XDPHV6MX44` GA4 across all 10 missing commercial/contact pages + instrumented `whatsapp_click`, `phone_click`, `email_click`, `cta_inquiry_click` & `generate_lead`<br>• Upgraded `header.php` & `index.html` with Dual-HQ (Singapore + Bengaluru) `Organization` schema + fixed Health & Safety `Product` schema bug<br>• Added `301` redirects (`/get-to-know-us`, `/our-team` → `/about-us`; `/social-event` → `/our-events-and-services`), universal `.php` → extensionless `301`, and `X-Robots-Tag: noindex, noarchive` on legacy microsite directories & cPanel subdomains<br>• Reconnected Google OAuth (`sc-domain:framez.sg` + GA4 `547082278`) | Capture 4,577/mo Singapore impressions, fix 100% GA4 blindspot on money pages, cure `/event-marketing-services` indexing hold, and strip legacy virtual-event bloat |
| **21 Nov** | Day 7 | **Wave 2 (Auto-Cron)** | Deploy `/conference-and-mice-event-management` (`conference-and-mice-event-management.php`) + auto-link in `blog.php`, `llms.txt`, `sitemap.xml` & IndexNow | Push `conference management company` (#26.1) & `conference event planning companies` (#39.8) toward Page 1 |
| **25 Nov** | Day 11 | **Wave 3 (Auto-Cron)** | Deploy `/exhibition-and-trade-show-management` (`exhibition-and-trade-show-management.php`) + auto-link & IndexNow | Capture `exhibition management company` (#30.4) & custom trade-show booth fabrication briefs in SG & BLR |
| **29 Nov** | Day 15 | **Wave 4 (Auto-Cron)** | Deploy `/year-end-corporate-town-hall-and-kickoff-guide` (`year-end-corporate-town-hall-and-kickoff-guide.php`) + Mid-Cycle GSC/GA4 telemetry snapshot | Capture Q4 town hall & Q1 Sales Kickoff (SKO) multi-hub planning demand |
| **03 Dec** | Day 19 | **Wave 5 (Auto-Cron)** | Deploy `/bangalore-corporate-event-venue-and-logistics-checklist` (`bangalore-corporate-event-venue-and-logistics-checklist.php`) + contextual links to BLR money pages | Push `corporate event management companies in bangalore` (#19.4) from Page 2 onto Page 1 |
| **07 Dec** | Day 23 | **Wave 6 (Auto-Cron)** | Deploy `/sustainable-corporate-events-esg-guide-singapore-india` (`sustainable-corporate-events-esg-guide-singapore-india.php`) + late-cycle CTR/query check | Address Singapore Green MICE & MNC ESG procurement RFP requirements |
| **11 to 15 Dec** | Days 27 to 31 | **Wave 7 & Cycle Close** | Full 30-day GSC (`sc-domain:framez.sg`) + GA4 (`547082278`) + Lead/Turnstile rollup auto-compiled into `FRAMEZ_NOVEMBER_DECEMBER_2026_SEO_AEO_GEO_REPORT.md` ready for PDF export & client presentation | Complete, evidence-backed Nov 15  to  Dec 15 client deliverable |

---

## 3. Automated Server Cron Configuration (`root@72.61.173.127`)

Installed at `/etc/cron.d/framez-seo` (guarded by `flock`):
1. **`04:15 UTC` (`12:15 SGT` / `09:45 IST`) Daily:** Executes `framez_seo_cron.py all` :  deploys any due scheduled wave (`STAGED_WAVES` in `content_pages.py`), reconciles `sitemap.xml`, validates all live URLs, pushes changed URLs to IndexNow, syncs GSC/GA4/lead counts, and updates `FRAMEZ_NOVEMBER_DECEMBER_2026_SEO_AEO_GEO_REPORT.md`.
2. **`19:30 UTC` (`03:30 SGT` / `01:00 IST`) Nightly:** Full technical crawl, sitemap verification, GSC/GA4/leads telemetry snapshot, and ledger append.

### Useful Commands on `72.61.173.127`
```bash
cd /root/websites/seogeoopt/seo-jobs/framez
python3 framez_seo_cron.py status       # View last run, deployed waves, GSC/GA4/leads status
python3 framez_seo_cron.py all          # Run full pipeline manually
python3 generate_nov_dec_report.py      # Regenerate Nov-Dec Markdown report immediately
```
