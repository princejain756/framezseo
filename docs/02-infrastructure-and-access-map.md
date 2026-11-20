# 02 :  Infrastructure, Operations Server & Browser Access Map

> **Security Rule:** Never hardcode or commit raw API tokens, passwords, or OAuth secrets into repository files. Read credentials at runtime from `/root/websites/seogeoopt/.env` on the operations server or use the authenticated sessions inside `ego-browser`.

---

## 1. ADELEV8 Operations Server (`ssh root@72.61.173.127`)

Passwordless SSH key access is configured from this Mac:
```bash
ssh root@72.61.173.127
```

### Key Directories on `72.61.173.127`

| Server Path | Purpose |
| --- | --- |
| `/root/websites/seogeoopt/` | **ADELEV8 Growth OS** (`https://portal.adelev8.com`, Vite/React + Express on port `5182` via PM2 `adelev8-growth-os-api`). Holds `.env` (`CPANEL_HOST`, `CPANEL_USERNAME`, `CPANEL_API_TOKEN`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`) and `server/data/portal.json`. |
| `/root/websites/seogeoopt/Framez/` | Historical Framez audits, strategy plans, blog proposals, PDFs, `frameznewlogo.png`, and `HOW_TO_MAKE_WEBSITE_CHANGES.md`. |
| `/root/websites/seogeoopt/DocMaker/` | Markdown & Puppeteer PDF generators + annotated GSC/site evidence screenshots (`FRAMEZ_OCTOBER_NOVEMBER_2026_SEO_AEO_GEO_REPORT.md`, `render_consolidated_90day_pdf.js`, `FRAMEZ_GBP_CATEGORY_PROPOSAL.md`). |
| `/root/websites/seogeoopt/seo-jobs/framez/` | **Live Daily SEO Automation** (`framez_seo_cron.py`, `framez_onpage_fix.py`, `config.json`, `state.json`, `reports/`, `logs/`, `backups/`). |
| `/etc/cron.d/framez-seo` | Runs `framez_seo_cron.py all` daily at `19:30 UTC` (`03:30 SGT`) with `flock`. |
| `/root/websites/seogeoopt/scratch/` | Staging, backup snapshots, and deployment verification scripts for `framez.sg`. |
| `/root/websites/openseo/` | Self-hosted **OpenSEO** (`seo.prince.sh`) with DataForSEO + GSC/GA4 integrations. |

---

## 2. Logged-in Google & Analytics Accounts (`ego-browser`)

Google Search Console, Google Analytics 4, and Google Business Profile are logged in locally inside **`ego-browser`** (always run `ego-browser skill` before driving the browser).

| Google Session Slot | Account Email | Framez Access & Properties |
| --- | --- | --- |
| **`/u/0/`** *(Primary)* | `princejain756@gmail.com` | **Owner/Verified access** to:<br>• **Google Search Console:** Domain property `sc-domain:framez.sg` (`https://search.google.com/u/0/search-console?resource_id=sc-domain%3Aframez.sg`) :  *Note: use `sc-domain:framez.sg`, NOT `https://framez.sg/`!*<br>• **Google Analytics 4:** Account `402211702`, Property `547082278` (`https://analytics.google.com/analytics/web/#/a402211702p547082278/reports/intelligenthome`)<br>• **Google Business Profile:** Location ID `1064671895591739893` |
| `/u/1/` | `adelev8now@gmail.com` | ADELEV8 Google account (no direct `framez.sg` GSC property attached) |
| `/u/2/` | `doaakalad586@gmail.com` | Other brand (`sc-domain:blankar.com`) |
| `/u/3/` | `emon1395fast@gmail.com` | No `framez.sg` property |

---

## 3. Safe Production Deployment Workflow (`framez.sg`)

Website files live in `public_html/` on `https://framez.sg:2083` and are managed via **cPanel UAPI `Fileman`** (`get_file_content` / `save_file_content`) using credentials in `/root/websites/seogeoopt/.env` on `72.61.173.127`.

### Mandatory 4-Step Change Protocol
1. **Download & Back Up First:** Fetch the live file from `public_html` via cPanel UAPI and save a timestamped backup + SHA-256 hash before editing.
2. **Modify & Validate Locally:** Check HTML/PHP syntax, `<head>` tag balance, JSON-LD validity (`json.loads`), Turnstile keys/forms intact, and responsive CSS intact.
3. **Upload via cPanel UAPI:** Save to `public_html/<filename>` via `POST /execute/Fileman/save_file_content`.
4. **Read-Back & Live HTTP Verify:** Verify SHA-256/read-back match, live HTTP `200` (or `301`), canonical match, and expected DOM/schema output; push changed canonical URLs via IndexNow (`59951843f48f4e09a34b4f61a08fd59c`).

### Non-Negotiable Safeguards
- Never delete or expose `leads_log.json` or `leads_spam_log.json`.
- Never weaken Cloudflare Turnstile, honeypots, CSP, or `.htaccess` `POST` exclusions on `contact-submit.php` and `submit-demo.php`.
- Never invent fake reviews, star ratings, client testimonials, headcount, or unverified revenue/ROI claims (adhere strictly to ADELEV8 Reporting Integrity).
