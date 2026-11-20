# 01 :  Company Profile & Website Architecture (`framez.sg`)

## 1. Business Overview & Positioning

**Framez Events & Productions** (*Frame Events and Productions Private Limited*) is an enterprise B2B corporate event management, experiential marketing, and technical production agency operating across **Bangalore (India)** and **Singapore / APAC**.

### Core Commercial Pillars
1. **Corporate Event Management & Production:** End-to-end concept, stage/AV engineering, vendor management, artist/speaker logistics, and show-calling.
2. **Conferences, Tech Summits & MICE:** Large-scale B2B user conferences, partner summits, leadership offsites, and exhibitions/stalls.
3. **Product Launches & Brand Ceremonies:** Reveal engineering, press/analyst operations, live broadcast/hybrid integration.
4. **Employee Recognition & Culture Events:** Annual days, awards nights, festive galas (Diwali/year-end), and corporate family day carnivals.
5. **Experiential Marketing & Brand Activations:** Interactive installations, roadshows, dwell-time & lead-capture experiences.
6. **High-Security / Regulated Enterprise Delivery:** ISO 9001 & ISO 27001 certified workflows, CXO/boardroom summit protocols, PDPA (Singapore) & enterprise procurement compliance.

### Ideal Customer Profile (ICP)
- Enterprise procurement teams, Heads of Marketing / Brand / Field Marketing, HR & People Operations leaders, Internal Communications teams, and Regional APAC Event Directors in **Bangalore**, **pan-India**, and **Singapore**.

---

## 2. Live Website Stack & Hosting Architecture

- **Primary Canonical Domain:** `https://framez.sg` (non-`www`, HTTPS, extensionless URLs)
- **Hosting:** Shared Linux / Apache on cPanel (`https://framez.sg:2083`, document root `public_html/`)
- **Tech Stack:**
  - Static homepage (`public_html/index.html`) + PHP-templated subpages (`public_html/*.php`) sharing `header.php` and `footer.php`.
  - Pre-compiled static Tailwind / custom CSS + Bootstrap/custom assets, with automatic `.htaccess` AVIF and WebP content negotiation.
  - Machine-readable discovery files: `robots.txt`, `sitemap.xml` (27 URLs), `image-sitemap.xml`, `llms.txt`, `llms-full.txt`, and IndexNow key file (`59951843f48f4e09a34b4f61a08fd59c.txt`).
- **Lead Capture & Security Stack (7 Layers):**
  - Dual form endpoints: `contact-submit.php` and `submit-demo.php` → redirect `302` to `/thank-you` (`noindex`).
  - Cloudflare Turnstile verification + honeypot fields + rate-limiting (`.rate_limit.json`) + ModSecurity + HSTS + HTTP `403` deny rules protecting `leads_log.json` and `leads_spam_log.json`.
  - Instant email dispatch to `info@framez.sg` and `framez.events@gmail.com`.

---

## 3. Current 27-URL Sitemap Inventory (as of 2026-11-18)

### A. Core Commercial & Brand Pages (13 URLs)
| URL | Role | Words | Schema Types |
| --- | --- | ---: | --- |
| `https://framez.sg/` | Homepage | 1,583 | `Organization`, `WebSite`, `WebPage` |
| `https://framez.sg/corporate-event-management-company` | Primary commercial pillar | 2,183 | `WebPage`, `Service`, `FAQPage`, `BreadcrumbList`, `Organization` |
| `https://framez.sg/our-events-and-services` | Services hub | 2,035 | `WebPage`, `Service`, `FAQPage`, `BreadcrumbList`, `Organization` |
| `https://framez.sg/event-management-company-in-bangalore` | Bangalore geo money page | 1,792 | `WebPage`, `Service`, `FAQPage`, `BreadcrumbList`, `Organization` |
| `https://framez.sg/event-management-company-in-india` | India geo money page | 1,700 | `WebPage`, `Service`, `BreadcrumbList`, `Organization`, `WebSite` |
| `https://framez.sg/event-planner` | Event planner commercial page | 1,687 | `WebPage`, `Service`, `BreadcrumbList`, `Organization`, `WebSite` |
| `https://framez.sg/event-marketing-services` | Event marketing commercial page | 1,620 | `WebPage`, `Service`, `BreadcrumbList`, `Organization`, `WebSite` |
| `https://framez.sg/experiential-marketing-brand-activations` | Experiential & activations pillar | 1,512 | `WebPage`, `Service`, `BreadcrumbList`, `Organization`, `WebSite` |
| `https://framez.sg/about-us` | Company & credentials | 1,393 | `AboutPage`, `BreadcrumbList`, `Organization`, `WebSite` |
| `https://framez.sg/clientele` | Client logo portfolio | 1,169 | `CollectionPage`, `BreadcrumbList`, `Organization`, `WebSite` |
| `https://framez.sg/blog` | Knowledge & guides hub | 1,623 | `CollectionPage`, `BreadcrumbList`, `Organization`, `WebSite` |
| `https://framez.sg/get-in-touch` | Contact inquiry page | 1,268 | `ContactPage`, `BreadcrumbList`, `Organization`, `WebSite` |
| `https://framez.sg/book-a-demo` | Event brief / demo request | 1,209 | `ContactPage`, `BreadcrumbList`, `Organization`, `WebSite` |

### B. Long-Form Buyer Guides, Handbooks & Trust Pages (14 URLs)
| URL | Focus | Words | Schema Types |
| --- | --- | ---: | --- |
| `/corporate-event-budget-planning-guide` | Procurement & event budgeting (Oct 26) | 2,036 | `Article`, `WebPage`, `BreadcrumbList`, `FAQPage`, `Organization` |
| `/annual-day-and-awards-night-planning-guide` | HR & employee awards (Oct 26) | 1,950 | `Article`, `WebPage`, `BreadcrumbList`, `FAQPage`, `Organization` |
| `/corporate-event-roi-measurement-guide` | Event attribution & ROI (Oct 26) | 1,982 | `Article`, `WebPage`, `BreadcrumbList`, `FAQPage`, `Organization` |
| `/singapore-corporate-event-planning-checklist` | Singapore logistics & compliance (Oct 26) | 1,919 | `Article`, `WebPage`, `BreadcrumbList`, `FAQPage`, `Organization` |
| `/corporate-event-planning-handbook-2027` | APAC 2027 handbook | 2,465 | `TechArticle`, `FAQPage`, `BreadcrumbList`, `Organization`, `WebSite` |
| `/experiential-brand-activations-framework` | Experiential ROI framework | 2,331 | `TechArticle`, `FAQPage`, `BreadcrumbList`, `Organization`, `WebSite` |
| `/executive-offsite-retreat-blueprint` | Luxury CXO retreats (BLR/Coorg/SG) | 2,384 | `TechArticle`, `FAQPage`, `BreadcrumbList`, `Organization`, `WebSite` |
| `/b2b-event-agency-rfp-evaluation-guide` | Procurement RFP scoring | 2,416 | `TechArticle`, `FAQPage`, `BreadcrumbList`, `Organization`, `WebSite` |
| `/corporate-product-launch-event-architecture` | Enterprise product launches | 2,261 | `TechArticle`, `HowTo`, `FAQPage`, `BreadcrumbList`, `Organization` |
| `/high-security-cxo-board-summit-protocol` | Boardroom security & TSCM | 2,361 | `TechArticle`, `HowTo`, `FAQPage`, `BreadcrumbList`, `Organization` |
| `/festive-corporate-gala-diwali-celebrations` | Corporate Diwali & festive galas | 2,279 | `TechArticle`, `HowTo`, `FAQPage`, `BreadcrumbList`, `Organization` |
| `/corporate-family-day-carnival-safety-logistics` | Family day safety & crowd ops | 2,364 | `TechArticle`, `HowTo`, `FAQPage`, `BreadcrumbList`, `Organization` |
| `/corporate-event-trends-singapore` | Singapore MICE & experiential trends | 1,528 | `Organization`, `WebSite` *(missing `Article` / `BreadcrumbList`!)* |
| `/Framez-Public-Statement-on-Health-and-Safety-Commitment` | ISO & safety commitment | 1,522 | `Product` *(bug!)*, `Organization`, `WebSite` |

### C. Legacy / Excluded Pages & cPanel Subdomains
- **Legacy 2021 pages still returning HTTP 200 & indexed in Google (excluded from sitemap):**
  - `/get-to-know-us` (duplicate of `/about-us`, 299 impressions / 5 clicks in 28d)
  - `/our-team` (2021 template, linked twice internally, 52 impressions / 2 clicks in 28d)
  - `/social-event` (legacy layout, no canonical, indexed)
- **Active cPanel Subdomains (`*.framez.sg`):**
  - `qr-registration.framez.sg`, `event-api.framez.sg`, `event-hub.framez.sg`, `welcometohpe2020.framez.sg`, `virtual.framez.sg`, `testregistration.framez.sg`, `tctindia2020.framez.sg`, `virtual-event.framez.sg`, `sp.framez.sg`, `smartlaunch-altan.framez.sg`, `tvs.framez.sg`, `volvo.framez.sg`, `virtualexhibition-ukskills.framez.sg`, `seri-dsci.framez.sg`, `tallyprime-launch.framez.sg`, `opscrm.framez.sg`, `events.framez.sg`, `qr-code.framez.sg`, `nps2025.framez.sg`, `card.framez.sg` (plus DNS/historical client subdomains still indexed in Google).
