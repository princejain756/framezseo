#!/usr/bin/env python3
"""Daily Automated SEO & GEO Actions Engine for Framez.sg.

Executes a verified production optimization every single day of the
active monthly cycle (15 Nov to 15 Dec 2026):
  - On Wave release dates (Nov 21, Nov 25, Nov 29, Dec 03, Dec 07):
    Handled by release_due_waves() in framez_seo_cron.py.
  - On non-wave dates (2026-11-20 and 2026-11-22 through 2026-12-15):
    Executes an idempotent, SHA-256-backed on-page, GEO/AEO, or audit action:
    1. Downloads & SHA-256 backs up the target file(s).
    2. Modifies HTML/PHP, schema, titles, metas, cross-links, or runs audits.
    3. Validates JSON-LD, GA4 (G-XDPHV6MX44), Turnstile/forms & zero em/en dashes.
    4. Uploads modified files to cPanel public_html/ via remote_put & verifies SHA-256.
    5. Pushes changed URLs via IndexNow when applicable.
    6. Logs an immutable receipt into daily-action-log.jsonl and the cycle ledger.
"""

import datetime
import hashlib
import html as html_lib
import json
import pathlib
import re
import urllib.error
import urllib.parse
import urllib.request

BASE_DIR = pathlib.Path(__file__).resolve().parent
JOB_DIR = BASE_DIR.parent if BASE_DIR.name == "scripts" else BASE_DIR
BACKUP_DIR = JOB_DIR / "backups" / "daily_actions"
REPORT_DIR = JOB_DIR / "reports"
LEDGER_PATH = REPORT_DIR / "cycle-2026-11-15-to-2026-12-15-ledger.jsonl"
DAILY_ACTION_LOG = REPORT_DIR / "daily-action-log.jsonl"

GA4_ID = "G-XDPHV6MX44"
TURNSTILE_SITEKEY = "0x4AAAAAAExBdPWHAqYTWVlc"
DEFAULT_INDEXNOW_HOST = "framez.sg"
DEFAULT_INDEXNOW_KEY = "59951843f48f4e09a34b4f61a08fd59c"
DEFAULT_INDEXNOW_ENDPOINT = "https://api.indexnow.org/IndexNow"
UA = "Mozilla/5.0 (compatible; Adelev8SEOBot/2.0; +https://portal.adelev8.com)"

LEGACY_BLOAT_MARKERS = (
    "http://maps.google.com",
    "jquery-3.3.1",
    "gmap3.min.js",
    "style-switcher.js",
    "jquery.countdown.js",
)


def now_utc():
    return datetime.datetime.now(datetime.timezone.utc)


def today_sgt():
    sgt = now_utc() + datetime.timedelta(hours=8)
    return sgt.strftime("%Y-%m-%d")


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def clean_dashes(text):
    """Remove em/en dashes cleanly while keeping numeric ranges readable."""
    return text.replace(" \u2014 ", ", ").replace("\u2014", ": ").replace("\u2013", "-")


def append_jsonl(path, obj):
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def save_json_report(filename, payload):
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = REPORT_DIR / filename
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out_path


def load_json_safe(path, default):
    try:
        return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default


def strip_visible_words(html_text):
    """Estimate visible body word count without script, style, or PHP blocks."""
    body_m = re.search(r"<body\b[^>]*>(.*?)</body>", html_text, re.S | re.I)
    chunk = body_m.group(1) if body_m else html_text
    chunk = re.sub(r"<\?php.*?\?>", " ", chunk, flags=re.S | re.I)
    chunk = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", chunk, flags=re.S | re.I)
    chunk = re.sub(r"<[^>]+>", " ", chunk)
    return len(chunk.split())


def validate_page_safety(orig, updated, fname):
    """Verify GA4, Turnstile, forms, JSON-LD, and zero em/en dashes before upload."""
    assert "\u2014" not in updated and "\u2013" not in updated, f"Em/en dash detected in {fname}"
    if fname.endswith((".php", ".html")):
        if GA4_ID in orig:
            assert GA4_ID in updated, f"GA4 {GA4_ID} removed from {fname}"
        if TURNSTILE_SITEKEY in orig:
            assert TURNSTILE_SITEKEY in updated, f"Turnstile key removed from {fname}"
        for form_action in ("contact-submit", "submit-demo", "<form"):
            if form_action in orig:
                assert form_action in updated, f"Form marker {form_action} removed from {fname}"
        for block in re.findall(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', updated, re.S | re.I):
            stripped = block.strip()
            if stripped and "<?php" not in stripped:
                json.loads(stripped)


def backup_and_upload(date_tag, fname, orig, updated, remote_get, remote_put, log_fn):
    """Back up original file, validate safety invariants, upload via remote_put, and verify SHA-256."""
    bdir = BACKUP_DIR / date_tag
    bdir.mkdir(parents=True, exist_ok=True)
    (bdir / f"{fname}.bak").write_text(orig, encoding="utf-8")

    sha_before = sha256_text(orig)
    updated = clean_dashes(updated)

    if updated == orig:
        receipt = {
            "file": fname,
            "changed": False,
            "sha256_before": sha_before,
            "sha256_after": sha_before,
            "sha256_verified": True,
        }
        (bdir / f"{fname}.manifest.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        log_fn(f"{date_tag}: {fname} already up to date (sha256={sha_before[:10]})")
        return True, "unchanged", receipt

    validate_page_safety(orig, updated, fname)
    sha_after = sha256_text(updated)
    ok = remote_put("public_html", fname, updated)
    if not ok:
        log_fn(f"{date_tag}: cPanel upload failed for {fname}")
        return False, f"cPanel upload failed for {fname}", {"file": fname, "changed": False}

    rb = remote_get("public_html", fname) or ""
    rb_sha = sha256_text(rb) if rb else None
    verified = (rb_sha == sha_after) if rb_sha else False
    receipt = {
        "file": fname,
        "changed": True,
        "bytes_before": len(orig),
        "bytes_after": len(updated),
        "sha256_before": sha_before,
        "sha256_after": sha_after,
        "readback_sha256": rb_sha,
        "sha256_verified": verified,
    }
    (bdir / f"{fname}.manifest.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    log_fn(
        f"{date_tag}: uploaded {fname} ({len(updated)} chars, sha256={sha_after[:10]}, readback_match={verified})"
    )
    return True, "updated", receipt


def fetch_remote_or_live(remote_get, fname, live_url=None):
    """Fetch file from cPanel via remote_get, falling back to live HTTPS if provided."""
    content = remote_get("public_html", fname)
    if content:
        return content
    if live_url:
        try:
            req = urllib.request.Request(live_url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.read().decode("utf-8", "ignore")
        except Exception:
            return None
    return None


def insert_block_idempotent(html_text, marker_id, block_html, prefer_before_fzguide_cta=True):
    """Insert an HTML section once before fzguide-cta, footer include, or </body>."""
    if marker_id in html_text:
        return html_text
    if prefer_before_fzguide_cta and '<div class="fzguide-cta">' in html_text:
        return html_text.replace('<div class="fzguide-cta">', block_html + '\n      <div class="fzguide-cta">', 1)
    m_footer = re.search(r'(<\?php\s+include\s+["\']footer\.php["\']\s*;?\s*\?>)', html_text, re.I)
    if m_footer:
        idx = m_footer.start()
        return html_text[:idx] + block_html + "\n\n" + html_text[idx:]
    if "</body>" in html_text:
        return html_text.replace("</body>", block_html + "\n</body>", 1)
    return html_text + "\n" + block_html


def inject_jsonld_if_missing(html_text, marker_text, schema_obj):
    """Inject a JSON-LD <script> block before </head> if marker_text is absent."""
    if marker_text in html_text:
        return html_text
    script = (
        '\n    <script type="application/ld+json">\n'
        + json.dumps(schema_obj, indent=4, ensure_ascii=False)
        + "\n    </script>\n"
    )
    if "</head>" in html_text:
        return html_text.replace("</head>", script + "</head>", 1)
    return script + html_text


def update_title_and_meta(html_text, new_title=None, new_desc=None):
    """Safely update <title>, meta description, OG, and Twitter tags within SEO length caps."""
    updated = html_text
    if new_title:
        assert len(new_title) <= 60, f"Title exceeds 60 chars: {len(new_title)}"
        esc_t = html_lib.escape(new_title)
        updated = re.sub(r"<title>.*?</title>", f"<title>{esc_t}</title>", updated, count=1, flags=re.S | re.I)
        updated = re.sub(
            r'(<meta\s+property=["\']og:title["\']\s+content=["\'])[^"\']*(["\'])',
            lambda m: m.group(1) + esc_t + m.group(2),
            updated,
            count=1,
            flags=re.I,
        )
        updated = re.sub(
            r'(<meta\s+name=["\']twitter:title["\']\s+content=["\'])[^"\']*(["\'])',
            lambda m: m.group(1) + esc_t + m.group(2),
            updated,
            count=1,
            flags=re.I,
        )
    if new_desc:
        assert len(new_desc) <= 160, f"Description exceeds 160 chars: {len(new_desc)}"
        esc_d = html_lib.escape(new_desc)
        updated = re.sub(
            r'(<meta\s+name=["\']description["\']\s+content=["\'])[^"\']*(["\'])',
            lambda m: m.group(1) + esc_d + m.group(2),
            updated,
            count=1,
            flags=re.I,
        )
        updated = re.sub(
            r'(<meta\s+property=["\']og:description["\']\s+content=["\'])[^"\']*(["\'])',
            lambda m: m.group(1) + esc_d + m.group(2),
            updated,
            count=1,
            flags=re.I,
        )
        updated = re.sub(
            r'(<meta\s+name=["\']twitter:description["\']\s+content=["\'])[^"\']*(["\'])',
            lambda m: m.group(1) + esc_d + m.group(2),
            updated,
            count=1,
            flags=re.I,
        )
    return updated


def append_fzguide_related(html_text, label, href):
    """Append a related link to .fzguide-related if not already present."""
    if href in html_text:
        return html_text
    m = re.search(r'(<p class="fzguide-related">Related:\s*)(.*?)(</p>)', html_text, re.S)
    if not m:
        return html_text
    link = f'<a href="{href}">{html_lib.escape(label)}</a>'
    body = m.group(2).strip()
    sep = " · " if body else ""
    return html_text[:m.start()] + m.group(1) + body + sep + link + m.group(3) + html_text[m.end():]


def ping_indexnow(urls, log_fn, indexnow_fn=None):
    """Push unique canonical URLs to IndexNow via callback or direct POST."""
    clean_urls = sorted({u for u in urls if u})
    if not clean_urls:
        return {"submitted": 0, "status": None, "ok": True, "urls": []}
    if indexnow_fn is not None:
        return indexnow_fn(clean_urls)

    cfg = load_json_safe(JOB_DIR / "config.json", {})
    host = cfg.get("host", DEFAULT_INDEXNOW_HOST)
    key = cfg.get("indexnow_key", DEFAULT_INDEXNOW_KEY)
    key_loc = cfg.get("indexnow_key_location", f"https://{host}/{key}.txt")
    endpoint = cfg.get("indexnow_endpoint", DEFAULT_INDEXNOW_ENDPOINT)

    payload = json.dumps({
        "host": host,
        "key": key,
        "keyLocation": key_loc,
        "urlList": clean_urls,
    }).encode("utf-8")

    try:
        req = urllib.request.Request(
            endpoint,
            data=payload,
            headers={"Content-Type": "application/json", "User-Agent": UA},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            status = resp.status
        log_fn(f"indexnow: submitted {len(clean_urls)} URLs (HTTP {status})")
        return {"submitted": len(clean_urls), "status": status, "ok": status in (200, 202), "urls": clean_urls}
    except urllib.error.HTTPError as exc:
        log_fn(f"indexnow: HTTP {exc.code} for {len(clean_urls)} URLs")
        return {"submitted": len(clean_urls), "status": exc.code, "ok": False, "urls": clean_urls}
    except Exception as exc:
        log_fn(f"indexnow: skipped/error ({exc})")
        return {"submitted": len(clean_urls), "status": None, "ok": False, "error": str(exc), "urls": clean_urls}


def parse_sitemap_locs(xml_text):
    return [m.group(1).strip() for m in re.finditer(r"<loc>\s*([^<\s]+)\s*</loc>", xml_text or "", re.I)]


def _extract_gsc_queries(gsc):
    """Collect queries across upgraded and standard latest-gsc.json layouts."""
    w28 = gsc.get("window_28d") or {}
    seen = {}
    for bucket in ("singapore_queries", "india_queries", "top_queries"):
        rows = (w28.get(bucket) or {}).get("rows") or []
        for r in rows:
            q = ((r.get("keys") or [""])[0] or "").strip()
            if not q:
                continue
            cur = seen.get(q)
            if not cur or r.get("impressions", 0) > cur.get("impressions", 0):
                seen[q] = {
                    "query": q,
                    "bucket": bucket,
                    "clicks": r.get("clicks", 0),
                    "impressions": r.get("impressions", 0),
                    "ctr": round(float(r.get("ctr", 0.0)), 4),
                    "position": round(float(r.get("position", 0.0)), 2),
                }
    return list(seen.values())


# 30-Day Master Schedule of Daily Actions (15 Nov to 15 Dec 2026)
DAILY_SCHEDULE = {
    "2026-11-15": {
        "action_id": "foundation_turnstile_defense",
        "title": "Turnstile Form Protection & Cron Deployment",
        "kind": "security_infrastructure",
        "summary": "7-layer Turnstile bot protection on contact forms and daily cron installation.",
        "executed_prior": True,
    },
    "2026-11-16": {
        "action_id": "metadata_repair_15_pages",
        "title": "15-Page Meta & OG Tag Audit and Repair",
        "kind": "metadata_optimization",
        "summary": "Updated titles, meta descriptions, OpenGraph tags, and image alt text across 15 pages.",
        "executed_prior": True,
    },
    "2026-11-17": {
        "action_id": "health_safety_sitemap_sync",
        "title": "Health & Safety Statement Schema & Sitemap Inclusion",
        "kind": "schema_and_indexing",
        "summary": "Cleaned schema on Health & Safety statement and reconciled sitemap to 27 URLs.",
        "executed_prior": True,
    },
    "2026-11-18": {
        "action_id": "wave1_singapore_core_overhaul",
        "title": "Wave 1: Flagship Singapore Money Page & Core Rebuilds",
        "kind": "major_wave_release",
        "summary": "Launched /event-management-company-in-singapore, rebuilt 3 core pages, sitewide GA4 unification across 24 files.",
        "executed_prior": True,
    },
    "2026-11-19": {
        "action_id": "ga4_conversion_events_audit",
        "title": "GA4 Multi-Channel Conversion Tracking Audit & IndexNow Reconciliation",
        "kind": "analytics_telemetry",
        "summary": "Verified G-XDPHV6MX44 conversion listeners (whatsapp, phone, email, generate_lead) across all 28 sitemap URLs.",
        "executed_prior": True,
    },
    "2026-11-20": {
        "action_id": "clientele_thin_content_faq_enrichment",
        "title": "Clientele Portfolio Enrichment & FAQ Schema Optimization",
        "kind": "on_page_content_and_schema",
        "target_file": "clientele.php",
        "target_url": "https://framez.sg/clientele",
        "summary": "Resolves thin content flag on /clientele by adding enterprise sector breakdowns, APAC case engagement highlights, and FAQPage JSON-LD schema with cross-links to Singapore and Bangalore.",
        "handler": "action_2026_11_20_clientele",
    },
    "2026-11-21": {
        "action_id": "wave2_conference_mice_release",
        "title": "Wave 2: Conference & MICE Event Management Page Release",
        "kind": "major_wave_release",
        "summary": "Launches /conference-and-mice-event-management targeting conference management company (#26.1) and MICE keywords.",
        "is_wave": True,
        "wave_id": "wave2_2026_11_21",
    },
    "2026-11-22": {
        "action_id": "mice_internal_linking_sprint",
        "title": "MICE Service Cross-Linking & Entity Anchors",
        "kind": "internal_linking",
        "summary": "Injects contextual cross-links and anchor text pointing to /conference-and-mice-event-management from Singapore and service overview pages.",
        "target_file": "event-management-company-in-singapore.php",
        "target_url": "https://framez.sg/event-management-company-in-singapore",
        "handler": "action_2026_11_22_mice_crosslinks",
    },
    "2026-11-23": {
        "action_id": "bangalore_page2_ctr_optimization",
        "title": "Bangalore Corporate Event CTR & FAQ Schema Sprint",
        "kind": "ctr_optimization",
        "summary": "Audits and reinforces title, meta description, Koramangala/Whitefield/ORR proof, and FAQPage/ProfessionalService schema on /event-management-company-in-bangalore.",
        "target_file": "event-management-company-in-bangalore.php",
        "target_url": "https://framez.sg/event-management-company-in-bangalore",
        "handler": "action_2026_11_23_bangalore_ctr_faq",
    },
    "2026-11-24": {
        "action_id": "exhibition_schema_preflight",
        "title": "Trade Show & Exhibition Entity Directory Preparation",
        "kind": "content_prep",
        "summary": "Pre-flight entity mapping and Singapore EXPO / Sands Expo venue technical specifications on /conference-and-mice-event-management ahead of Wave 3.",
        "target_file": "conference-and-mice-event-management.php",
        "target_url": "https://framez.sg/conference-and-mice-event-management",
        "handler": "action_2026_11_24_mice_preflight_venues",
    },
    "2026-11-25": {
        "action_id": "wave3_exhibition_trade_show_release",
        "title": "Wave 3: Exhibition & Trade Show Management Page Release",
        "kind": "major_wave_release",
        "summary": "Launches /exhibition-and-trade-show-management targeting exhibition management company (#30.4) and custom booth fabrication.",
        "is_wave": True,
        "wave_id": "wave3_2026_11_25",
    },
    "2026-11-26": {
        "action_id": "exhibition_cross_linking_images",
        "title": "Exhibition Cross-Linking & Image Sitemap Verification",
        "kind": "media_and_sitemap",
        "summary": "Links exhibition and product launch services from service overview and Singapore pages and verifies image-sitemap.xml.",
        "target_file": "our-events-and-services.php",
        "target_url": "https://framez.sg/our-events-and-services",
        "handler": "action_2026_11_26_exhibition_crosslinks",
    },
    "2026-11-27": {
        "action_id": "book_demo_scope_estimator_expansion",
        "title": "Book-a-Demo Interactive Scope Estimator & Thin Content Fix",
        "kind": "conversion_optimization",
        "summary": "Verifies and expands /book-a-demo with enterprise RFP scope estimator, budgeting tiers, and FAQPage schema while preserving Turnstile.",
        "target_file": "book-a-demo.php",
        "target_url": "https://framez.sg/book-a-demo",
        "handler": "action_2026_11_27_book_demo_estimator",
    },
    "2026-11-28": {
        "action_id": "year_end_town_hall_seasonal_keywords",
        "title": "Year-End Corporate Town Hall Seasonal Search Injections",
        "kind": "seasonal_seo",
        "summary": "Injects Q4 all-hands town hall and Q1 sales kickoff internal anchors on corporate-event-management-company.php and event-planner.php.",
        "target_file": "corporate-event-management-company.php",
        "target_url": "https://framez.sg/corporate-event-management-company",
        "handler": "action_2026_11_28_seasonal_townhall_sko",
    },
    "2026-11-29": {
        "action_id": "wave4_town_hall_kickoff_guide_release",
        "title": "Wave 4: Corporate Town Hall & Sales Kickoff Guide Release",
        "kind": "major_wave_release",
        "summary": "Launches /year-end-corporate-town-hall-and-kickoff-guide targeting enterprise all-hands and SKO multi-hub production.",
        "is_wave": True,
        "wave_id": "wave4_2026_11_29",
    },
    "2026-11-30": {
        "action_id": "mid_cycle_gsc_ctr_recalibration",
        "title": "Mid-Cycle Search Console Telemetry Audit & CTR Re-calibration",
        "kind": "analytics_audit",
        "summary": "Analyzes latest-gsc.json query/page velocity and writes reports/mid-cycle-ctr-audit.json.",
        "target_file": "reports/mid-cycle-ctr-audit.json",
        "target_url": None,
        "handler": "action_2026_11_30_mid_cycle_ctr_audit",
    },
    "2026-12-01": {
        "action_id": "generative_engine_llms_txt_sync",
        "title": "Generative Engine (AEO/GEO) Citation Audit & Knowledge Base Sync",
        "kind": "geo_aeo_optimization",
        "summary": "Syncs live llms.txt and llms-full.txt with sitemap inventory, uploads via remote_put, and pushes IndexNow.",
        "target_file": "llms.txt",
        "target_url": "https://framez.sg/llms.txt",
        "handler": "action_2026_12_01_llms_parity_sync",
    },
    "2026-12-02": {
        "action_id": "bangalore_tech_venue_entity_reinforcement",
        "title": "Bangalore Tech Hub & Koramangala Entity Reinforcement",
        "kind": "local_seo",
        "summary": "Strengthens Koramangala, Whitefield, ORR, BIEC and KTPO entity citations on Bangalore and India service pages.",
        "target_file": "event-management-company-in-bangalore.php",
        "target_url": "https://framez.sg/event-management-company-in-bangalore",
        "handler": "action_2026_12_02_bangalore_tech_corridors",
    },
    "2026-12-03": {
        "action_id": "wave5_bangalore_venue_guide_release",
        "title": "Wave 5: Bangalore Corporate Venue & Logistics Checklist Release",
        "kind": "major_wave_release",
        "summary": "Launches /bangalore-corporate-event-venue-and-logistics-checklist pushing Bangalore commercial terms from Page 2 to Page 1.",
        "is_wave": True,
        "wave_id": "wave5_2026_12_03",
    },
    "2026-12-04": {
        "action_id": "cxo_retreats_cross_linking_sprint",
        "title": "Executive Offsite & CXO Retreats Cross-Linking Sprint",
        "kind": "internal_linking",
        "summary": "Cross-links /executive-offsite-retreat-blueprint with Bangalore venue checklist and Singapore corporate event page.",
        "target_file": "executive-offsite-retreat-blueprint.php",
        "target_url": "https://framez.sg/executive-offsite-retreat-blueprint",
        "handler": "action_2026_12_04_offsite_crosslinks",
    },
    "2026-12-05": {
        "action_id": "green_mice_sustainability_keyword_prep",
        "title": "Singapore Green Plan 2030 & Green MICE Keyword Prep",
        "kind": "content_prep",
        "summary": "Injects Singapore Green Plan 2030 / STB MICE sustainability & BCA Green Mark entity block onto Singapore service page.",
        "target_file": "event-management-company-in-singapore.php",
        "target_url": "https://framez.sg/event-management-company-in-singapore",
        "handler": "action_2026_12_05_green_mice_prep",
    },
    "2026-12-06": {
        "action_id": "sustainable_rfp_materials_audit",
        "title": "Sustainable Corporate Event RFP Materials & llms-full.txt Prep",
        "kind": "content_prep",
        "summary": "Adds modular aluminium/LED staging entity block and refreshes llms-full.txt ahead of Wave 6 ESG release.",
        "target_file": "llms-full.txt",
        "target_url": "https://framez.sg/llms-full.txt",
        "handler": "action_2026_12_06_sustainable_rfp_llms_prep",
    },
    "2026-12-07": {
        "action_id": "wave6_sustainable_events_esg_guide_release",
        "title": "Wave 6: Sustainable Corporate Events & ESG Guide Release",
        "kind": "major_wave_release",
        "summary": "Launches /sustainable-corporate-events-esg-guide-singapore-india addressing enterprise MNC and Singapore Green MICE requirements.",
        "is_wave": True,
        "wave_id": "wave6_2026_12_07",
    },
    "2026-12-08": {
        "action_id": "esg_cross_linking_sprint",
        "title": "ESG & Sustainability Cross-Linking across Service Pages",
        "kind": "internal_linking",
        "summary": "Cross-links ESG guide from Singapore corporate event management and B2B RFP evaluation guide.",
        "target_file": "b2b-event-agency-rfp-evaluation-guide.php",
        "target_url": "https://framez.sg/b2b-event-agency-rfp-evaluation-guide",
        "handler": "action_2026_12_08_esg_crosslinks",
    },
    "2026-12-09": {
        "action_id": "mobile_core_web_vitals_sprint",
        "title": "Sitewide Core Web Vitals & Asset Bloat Verification Audit",
        "kind": "technical_performance",
        "summary": "Audits HTML payload sizes, lazy-loading, explicit image dimensions, blocking scripts, and legacy bloat across sitemap URLs.",
        "target_file": "reports/cwv-asset-audit.json",
        "target_url": None,
        "handler": "action_2026_12_09_cwv_asset_audit",
    },
    "2026-12-10": {
        "action_id": "redirect_canonical_hygiene_audit",
        "title": "301 Redirect Hygiene & Canonical Header Verification",
        "kind": "technical_seo",
        "summary": "Crawls canonical and legacy URLs to verify single-hop 301 redirects, zero 404s, and self-canonical consistency.",
        "target_file": "reports/redirect-canonical-audit.json",
        "target_url": None,
        "handler": "action_2026_12_10_redirect_canonical_audit",
    },
    "2026-12-11": {
        "action_id": "end_of_cycle_ranking_velocity_analysis",
        "title": "End-of-Cycle Search Velocity & Ranking Movement Analysis",
        "kind": "analytics_audit",
        "summary": "Computes Singapore and India click, impression, CTR and query movement rollup from latest-gsc.json.",
        "target_file": "reports/ranking-velocity-rollup.json",
        "target_url": None,
        "handler": "action_2026_12_11_ranking_velocity_rollup",
    },
    "2026-12-12": {
        "action_id": "lead_defense_conversion_integrity_audit",
        "title": "Lead Defense & Form Security Verification",
        "kind": "security_audit",
        "summary": "Audits aggregate verified leads vs blocked bot counts (zero PII) and verifies Turnstile protection on live forms.",
        "target_file": "reports/lead-integrity-audit.json",
        "target_url": None,
        "handler": "action_2026_12_12_lead_turnstile_audit",
    },
    "2026-12-13": {
        "action_id": "sitemap_indexnow_full_reconciliation",
        "title": "Full 33+ URL Search Console & IndexNow Reconciliation",
        "kind": "indexing_reconciliation",
        "summary": "Pushes all canonical sitemap URLs to IndexNow and writes reconciliation receipt.",
        "target_file": "sitemap.xml",
        "target_url": "https://framez.sg/sitemap.xml",
        "handler": "action_2026_12_13_full_sitemap_indexnow",
    },
    "2026-12-14": {
        "action_id": "cycle_data_freeze_monthly_synthesis",
        "title": "Cycle 4 Data Freeze & Monthly Telemetry Verification",
        "kind": "reporting_freeze",
        "summary": "Verifies cycle-boundary monthly snapshot freeze and telemetry parity ahead of client presentation.",
        "target_file": "reports/cycle-freeze-verification.json",
        "target_url": None,
        "handler": "action_2026_12_14_cycle_freeze_check",
    },
    "2026-12-15": {
        "action_id": "final_monthly_report_client_presentation",
        "title": "Final Monthly Cycle Report Verification & Client Delivery",
        "kind": "client_delivery",
        "summary": "Audits FRAMEZ_NOVEMBER_DECEMBER_2026_SEO_AEO_GEO_REPORT.md for zero dashes/buzzwords/revenue disclosures and ledger completeness.",
        "target_file": "reports/final-cycle-report-verification.json",
        "target_url": None,
        "handler": "action_2026_12_15_final_report_verify",
    },
}


def action_2026_11_20_clientele(remote_get, remote_put, log_fn, indexnow_fn=None):
    """2026-11-20: Enrich clientele.php to resolve thin content and add FAQPage schema."""
    fname = "clientele.php"
    log_fn("action_2026_11_20: fetching live clientele.php from cPanel...")
    cur = remote_get("public_html", fname)
    if not cur:
        log_fn("action_2026_11_20: error, could not fetch clientele.php")
        return False, "Failed to read remote clientele.php"

    bdir = BACKUP_DIR / "2026-11-20-clientele-enrichment"
    bdir.mkdir(parents=True, exist_ok=True)
    (bdir / f"{fname}.bak").write_text(cur, encoding="utf-8")
    log_fn(f"action_2026_11_20: backed up live file ({len(cur)} chars, sha256={sha256_text(cur)[:10]})")

    if ("Enterprise Sectors & Client Portfolio" in cur or "fz-clientele-enterprise-sectors" in cur) and "FAQPage" in cur:
        log_fn("action_2026_11_20: clientele.php is already enriched.")
        return True, "Already enriched"

    faq_schema = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": "What enterprise industries does Framez Events manage corporate events for?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": "Framez Events & Productions produces corporate events, conferences, and brand activations for multinational technology companies, banking and financial institutions, pharmaceutical leaders, APAC association conventions, and enterprise retail brands across Singapore and India.",
                },
            },
            {
                "@type": "Question",
                "name": "Does Framez manage multi-city APAC corporate events across Singapore and India?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": "Yes. Operating dual regional headquarters at Prudential Tower in Raffles Place, Singapore, and Koramangala in Bangalore, Framez regularly executes synchronized multi-city annual conferences, simultaneous town halls, and hybrid leadership summits across Singapore, Bangalore, Mumbai, and Delhi.",
                },
            },
            {
                "@type": "Question",
                "name": "What confidentiality and data security protocols does Framez enforce for corporate clients?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": "Framez operates under ISO 27001:2013 information security standards and strict Non-Disclosure Agreements (NDAs). We enforce secure attendee badge data handling compliant with Singapore's Personal Data Protection Act (PDPA) and secure private live-stream broadcast infrastructure for enterprise all-hands.",
                },
            },
            {
                "@type": "Question",
                "name": "How does Framez coordinate venue logistics with major Singapore convention venues?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": "Our Singapore production teams coordinate directly with major convention and hotel venues including Marina Bay Sands Expo and Convention Centre, Suntec Singapore Convention & Exhibition Centre, and central business district corporate auditoriums for staging, rigging, AV production, and delegate flow.",
                },
            },
        ],
    }

    updated = inject_jsonld_if_missing(cur, '"FAQPage"', faq_schema)
    enrichment_html = """
    <section id="fz-clientele-enterprise-sectors" class="sec-padding" style="background:#f9fafb; padding:60px 0;">
        <div class="container">
            <div class="row text-center mb-5">
                <div class="col-lg-10 mx-auto">
                    <span class="badge badge-primary px-3 py-2 mb-3" style="background:#0d6efd; color:#fff; font-size:13px; text-transform:uppercase; letter-spacing:1px; border-radius:4px;">Enterprise Client Experience</span>
                    <h2 class="font-weight-bold" style="color:#111827; font-size:32px; line-height:1.3;">Trusted by Global Leaders Across Singapore, Bangalore &amp; APAC</h2>
                    <p style="color:#4b5563; font-size:16px; max-width:800px; margin:15px auto 0;">From Fortune 500 technology firms and financial institutions to fast-growing enterprise scale-ups, Framez Events &amp; Productions delivers high-precision conferences, product launches, CXO summits, and annual celebrations with zero operational compromise.</p>
                </div>
            </div>
            <div class="row">
                <div class="col-lg-4 col-md-6 mb-4">
                    <div class="p-4 bg-white h-100" style="border-radius:10px; border:1px solid #e5e7eb; box-shadow:0 4px 6px -1px rgba(0,0,0,0.05);">
                        <h3 style="font-size:20px; font-weight:700; color:#111827; margin-bottom:12px;">Technology &amp; SaaS</h3>
                        <p style="color:#4b5563; font-size:14px; line-height:1.6;">Developer summits, global user conferences, APAC product keynotes, and multi-hub hybrid town halls for software, cloud, and semiconductor leaders in Singapore and Bangalore's tech corridors.</p>
                    </div>
                </div>
                <div class="col-lg-4 col-md-6 mb-4">
                    <div class="p-4 bg-white h-100" style="border-radius:10px; border:1px solid #e5e7eb; box-shadow:0 4px 6px -1px rgba(0,0,0,0.05);">
                        <h3 style="font-size:20px; font-weight:700; color:#111827; margin-bottom:12px;">Banking &amp; Financial Services</h3>
                        <p style="color:#4b5563; font-size:14px; line-height:1.6;">High-security CXO board meetings, investor symposiums, risk summits, and annual gala banquets executed under ISO 27001 data governance and strict NDA confidentiality protocols.</p>
                    </div>
                </div>
                <div class="col-lg-4 col-md-6 mb-4">
                    <div class="p-4 bg-white h-100" style="border-radius:10px; border:1px solid #e5e7eb; box-shadow:0 4px 6px -1px rgba(0,0,0,0.05);">
                        <h3 style="font-size:20px; font-weight:700; color:#111827; margin-bottom:12px;">MICE &amp; APAC Conventions</h3>
                        <p style="color:#4b5563; font-size:14px; line-height:1.6;">Association conventions, trade exhibitions, and international partner summits coordinated with Marina Bay Sands Expo, Suntec Singapore, and Bangalore international exhibition centres.</p>
                    </div>
                </div>
            </div>
            <div class="row mt-5">
                <div class="col-lg-10 mx-auto">
                    <div class="text-center mb-4">
                        <h2 class="font-weight-bold" style="color:#111827; font-size:28px;">Enterprise Client Frequently Asked Questions</h2>
                        <p style="color:#6b7280; font-size:15px;">Key operational details on how Framez partners with corporate event teams across Asia-Pacific.</p>
                    </div>
                    <div class="card mb-3" style="border:1px solid #e5e7eb; border-radius:8px;">
                        <div class="card-body p-4">
                            <h4 style="font-size:18px; font-weight:700; color:#111827; margin-bottom:8px;">What enterprise industries does Framez manage corporate events for?</h4>
                            <p style="color:#4b5563; font-size:15px; line-height:1.6; margin:0;">Framez Events &amp; Productions produces corporate events, conferences, and brand activations for multinational technology companies, banking and financial institutions, pharmaceutical leaders, APAC association conventions, and enterprise retail brands across Singapore and India.</p>
                        </div>
                    </div>
                    <div class="card mb-3" style="border:1px solid #e5e7eb; border-radius:8px;">
                        <div class="card-body p-4">
                            <h4 style="font-size:18px; font-weight:700; color:#111827; margin-bottom:8px;">Does Framez manage multi-city APAC corporate events across Singapore and India?</h4>
                            <p style="color:#4b5563; font-size:15px; line-height:1.6; margin:0;">Yes. Operating dual regional headquarters at Prudential Tower in Raffles Place, Singapore, and Koramangala in Bangalore, Framez regularly executes synchronized multi-city annual conferences, simultaneous town halls, and hybrid leadership summits across Singapore, Bangalore, Mumbai, and Delhi.</p>
                        </div>
                    </div>
                    <div class="card mb-3" style="border:1px solid #e5e7eb; border-radius:8px;">
                        <div class="card-body p-4">
                            <h4 style="font-size:18px; font-weight:700; color:#111827; margin-bottom:8px;">What confidentiality and data security protocols does Framez enforce for corporate clients?</h4>
                            <p style="color:#4b5563; font-size:15px; line-height:1.6; margin:0;">Framez operates under ISO 27001:2013 information security standards and strict Non-Disclosure Agreements (NDAs). We enforce secure attendee badge data handling compliant with Singapore's Personal Data Protection Act (PDPA) and secure private live-stream broadcast infrastructure for enterprise all-hands.</p>
                        </div>
                    </div>
                    <div class="card mb-3" style="border:1px solid #e5e7eb; border-radius:8px;">
                        <div class="card-body p-4">
                            <h4 style="font-size:18px; font-weight:700; color:#111827; margin-bottom:8px;">How does Framez coordinate venue logistics with major Singapore convention venues?</h4>
                            <p style="color:#4b5563; font-size:15px; line-height:1.6; margin:0;">Our Singapore production teams coordinate directly with major convention and hotel venues including Marina Bay Sands Expo and Convention Centre, Suntec Singapore Convention &amp; Exhibition Centre, and central business district corporate auditoriums for staging, rigging, AV production, and delegate flow. Explore our dedicated <a href="/event-management-company-in-singapore" style="color:#0d6efd; font-weight:600;">Singapore Corporate Event Management</a> and <a href="/corporate-event-management-company" style="color:#0d6efd; font-weight:600;">Corporate Event Management Services</a>.</p>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </section>
    """
    updated = insert_block_idempotent(updated, "fz-clientele-enterprise-sectors", enrichment_html, prefer_before_fzguide_cta=False)
    ok, status_msg, receipt = backup_and_upload("2026-11-20-clientele-enrichment", fname, cur, updated, remote_get, remote_put, log_fn)
    if not ok:
        return False, status_msg
    return True, "Enriched clientele.php with enterprise sectors, case highlights, and FAQPage schema.", {"sha256_receipts": [receipt]}


def action_2026_11_22_mice_crosslinks(remote_get, remote_put, log_fn, indexnow_fn=None):
    """2026-11-22: Add contextual MICE cross-links and entity anchors pointing to /conference-and-mice-event-management."""
    receipts = []
    targets = [
        (
            "event-management-company-in-singapore.php",
            "fz-daily-2026-11-22-mice-sg",
            """
      <section id="fz-daily-2026-11-22-mice-sg" style="margin:28px 0; padding:22px; background:#f8fafc; border:1px solid #e2e8f0; border-radius:10px;">
        <h2>Regional APAC Conferences &amp; MICE Production in Singapore</h2>
        <p>For multi-track enterprise summits, association conventions and regional incentive programmes across Marina Bay Sands Expo, Suntec Singapore and Singapore EXPO, explore our dedicated <a href="/conference-and-mice-event-management">Conference &amp; MICE Event Management Services</a>. Teams scheduling annual celebrations in Singapore can also review our <a href="/dinner-and-dance-event-management-singapore">Dinner &amp; Dance Event Management in Singapore</a> capabilities.</p>
      </section>
""",
            True,
        ),
        (
            "our-events-and-services.php",
            "fz-daily-2026-11-22-mice-services",
            """
<section id="fz-daily-2026-11-22-mice-services" class="sec-padding" style="background:#f8fafc; padding:48px 0;">
  <div class="container">
    <div class="row">
      <div class="col-lg-10 mx-auto">
        <h2 style="color:#111827; font-size:26px; font-weight:700; margin-bottom:14px;">Dedicated B2B Conference, MICE &amp; Regional Singapore Delivery</h2>
        <p style="color:#4b5563; font-size:15px; line-height:1.7;">Enterprise buyers coordinating multi-track user summits, partner conventions or APAC incentive programmes can drill straight into our <a href="/conference-and-mice-event-management" style="color:#0d6efd; font-weight:600;">Conference &amp; MICE Event Management Services</a> for plenary AV engineering, centralized slide-desk workflows and fast QR delegate check-in across <a href="/event-management-company-in-singapore" style="color:#0d6efd; font-weight:600;">Singapore</a> and <a href="/event-management-company-in-bangalore" style="color:#0d6efd; font-weight:600;">Bangalore</a>.</p>
      </div>
    </div>
  </div>
</section>
""",
            False,
        ),
    ]

    for fname, marker, block, use_cta in targets:
        cur = remote_get("public_html", fname)
        if not cur:
            return False, f"Failed to read remote {fname}"
        updated = insert_block_idempotent(cur, marker, block, prefer_before_fzguide_cta=use_cta)
        if fname == "event-management-company-in-singapore.php":
            updated = append_fzguide_related(updated, "Conference & MICE Management", "/conference-and-mice-event-management")
        ok, _, receipt = backup_and_upload("2026-11-22-mice-crosslinks", fname, cur, updated, remote_get, remote_put, log_fn)
        if not ok:
            return False, f"Failed to upload {fname}"
        receipts.append(receipt)

    return True, "Added MICE cross-links on Singapore and Our Events & Services pages.", {
        "target_urls": [
            "https://framez.sg/event-management-company-in-singapore",
            "https://framez.sg/our-events-and-services",
        ],
        "sha256_receipts": receipts,
    }


def action_2026_11_23_bangalore_ctr_faq(remote_get, remote_put, log_fn, indexnow_fn=None):
    """2026-11-23: Audit and reinforce Bangalore Page-2 CTR, Koramangala/Whitefield/ORR proof, and FAQPage/ProfessionalService schema."""
    fname = "event-management-company-in-bangalore.php"
    cur = remote_get("public_html", fname)
    if not cur:
        return False, f"Failed to read remote {fname}"

    new_title = "Corporate Event Management Company in Bangalore | Framez"
    new_desc = "Corporate event management company in Bangalore (Koramangala HQ): conferences, launches & annual days across Whitefield, ORR & CBD. ISO 9001 & 27001 certified."

    updated = cur
    title_m = re.search(r"<title>(.*?)</title>", cur, re.S | re.I)
    cur_title = title_m.group(1).strip() if title_m else ""
    if "Corporate Event Management Company in Bangalore" not in cur_title:
        updated = update_title_and_meta(updated, new_title=new_title, new_desc=new_desc)

    blr_office_schema = {
        "@context": "https://schema.org",
        "@type": "ProfessionalService",
        "@id": "https://framez.sg/event-management-company-in-bangalore#bangalore-office",
        "name": "Framez Events & Productions, Bangalore HQ",
        "url": "https://framez.sg/event-management-company-in-bangalore",
        "image": "https://framez.sg/assets/img/frameznewlogo.png",
        "email": "info@framez.sg",
        "telephone": "+91-9448066560",
        "parentOrganization": {"@id": "https://framez.sg/#organization"},
        "address": {
            "@type": "PostalAddress",
            "streetAddress": "B/2, GANGA, 3rd Floor, 5th Block, KHB Colony, Koramangala",
            "addressLocality": "Bengaluru",
            "addressRegion": "Karnataka",
            "postalCode": "560095",
            "addressCountry": "IN",
        },
        "geo": {
            "@type": "GeoCoordinates",
            "latitude": 12.9352,
            "longitude": 77.6245,
        },
        "areaServed": {"@type": "City", "name": "Bengaluru"},
    }
    updated = inject_jsonld_if_missing(updated, '"ProfessionalService"', blr_office_schema)

    blr_faq_schema = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": "Which Bengaluru business corridors does Framez serve for corporate events?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": "From our headquarters in Koramangala 5th Block, Framez delivers conferences, GCC town halls, annual days and launches across Whitefield, Outer Ring Road (Bellandur-Marathahalli), MG Road CBD, North Bangalore, BIEC and KTPO.",
                },
            },
            {
                "@type": "Question",
                "name": "Does Framez hold ISO certifications for enterprise procurement in Bangalore?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": "Yes. Frame Events and Productions Private Limited operates under ISO 9001:2015 quality management and ISO 27001:2013 information security standards with itemized BoQs and documented RAMS safety checklists.",
                },
            },
        ],
    }
    updated = inject_jsonld_if_missing(updated, '"FAQPage"', blr_faq_schema)

    proof_block = """
<section id="fz-daily-2026-11-23-blr-proof" class="sec-padding" style="background:#f9fafb; padding:52px 0;">
  <div class="container">
    <div class="row">
      <div class="col-lg-10 mx-auto">
        <h2 style="color:#111827; font-size:28px; font-weight:700; margin-bottom:14px;">Bengaluru Production Proof: Koramangala HQ, Whitefield &amp; Outer Ring Road</h2>
        <p style="color:#4b5563; font-size:15px; line-height:1.7;">Operating from our Koramangala 5th Block headquarters, Framez conducts physical technical recces across Whitefield tech-park convention halls, Outer Ring Road (ORR) enterprise hotels and CBD ballrooms before build day. Every programme ships under ISO 9001:2015 quality checklists and ISO 27001:2013 data protection controls with dedicated silent DG power isolation and UPS backup.</p>
        <p style="color:#4b5563; font-size:15px; line-height:1.7; margin-bottom:0;">Explore our <a href="/conference-and-mice-event-management" style="color:#0d6efd; font-weight:600;">Conference &amp; MICE Event Management</a> capabilities, review line-item estimates in the <a href="/corporate-event-budget-planning-guide" style="color:#0d6efd; font-weight:600;">Corporate Event Budget Planning Guide</a>, or <a href="/book-a-demo" style="color:#0d6efd; font-weight:600;">Book a Demo &amp; Brief Review</a>.</p>
      </div>
    </div>
  </div>
</section>
"""
    updated = insert_block_idempotent(updated, "fz-daily-2026-11-23-blr-proof", proof_block, prefer_before_fzguide_cta=False)
    ok, status_msg, receipt = backup_and_upload("2026-11-23-bangalore-ctr-faq", fname, cur, updated, remote_get, remote_put, log_fn)
    if not ok:
        return False, status_msg
    return True, "Reinforced Bangalore CTR metadata, Koramangala/Whitefield/ORR proof, and ProfessionalService/FAQPage schema.", {
        "target_urls": ["https://framez.sg/event-management-company-in-bangalore"],
        "sha256_receipts": [receipt],
    }


def action_2026_11_24_mice_preflight_venues(remote_get, remote_put, log_fn, indexnow_fn=None):
    """2026-11-24: Pre-flight Singapore EXPO / Sands Expo entity block + internal link prep on conference-and-mice-event-management.php."""
    fname = "conference-and-mice-event-management.php"
    cur = fetch_remote_or_live(remote_get, fname, "https://framez.sg/conference-and-mice-event-management")
    if not cur:
        return False, f"Failed to read {fname}"

    venue_block = """
      <section id="fz-daily-2026-11-24-venue-specs" style="margin:28px 0; padding:22px; background:#f8fafc; border:1px solid #e2e8f0; border-radius:10px;">
        <h2>Singapore EXPO, Sands Expo &amp; Suntec Convention Pre-Flight Specifications</h2>
        <p>Large-scale MICE conferences and companion trade exhibitions in Singapore run on fixed venue protocols. Ahead of build day, Framez verifies marshalling-yard vehicle slots, certified rigging point load tolerances, clear-span ceiling heights, dedicated hardwired broadcast LAN drops and early-bird electrical orders across <strong>Marina Bay Sands Expo &amp; Convention Centre</strong>, <strong>Suntec Singapore</strong> and <strong>Singapore EXPO</strong>.</p>
        <p>Planning audience promotion or an upcoming brief? Connect with our <a href="/event-management-company-in-singapore">Singapore Corporate Event Management</a> team, align registration funnels via <a href="/event-marketing-services">B2B Event Marketing Services</a>, or <a href="/book-a-demo">submit your event brief via Book a Demo</a>.</p>
      </section>
"""
    updated = insert_block_idempotent(cur, "fz-daily-2026-11-24-venue-specs", venue_block, prefer_before_fzguide_cta=True)
    updated = append_fzguide_related(updated, "Event Marketing Services", "/event-marketing-services")
    ok, _, receipt = backup_and_upload("2026-11-24-mice-preflight", fname, cur, updated, remote_get, remote_put, log_fn)
    if not ok:
        return False, f"Failed to upload {fname}"

    preflight_report = {
        "generated_at": now_utc().isoformat(),
        "date_sgt": "2026-11-24",
        "upcoming_wave": "wave3_2026_11_25",
        "target_slug": "exhibition-and-trade-show-management",
        "singapore_venues": [
            {"venue": "Marina Bay Sands Expo & Convention Centre", "checks": ["marshalling_yard_slots", "rigging_plot_certification", "early_bird_electrical"]},
            {"venue": "Suntec Singapore Convention & Exhibition Centre", "checks": ["goods_lift_dimensions", "ceiling_rigging_points", "pdpa_badge_desk_wifi"]},
            {"venue": "Singapore EXPO (Changi)", "checks": ["heavy_freight_forklift_windows", "clear_span_power_distribution", "fire_aisle_clearances"]},
        ],
    }
    rpath = save_json_report("preflight-wave3-exhibition-entities.json", preflight_report)
    return True, "Injected Singapore EXPO / Sands Expo pre-flight entity block on conference-and-mice-event-management.php.", {
        "target_urls": ["https://framez.sg/conference-and-mice-event-management"],
        "sha256_receipts": [receipt],
        "report_path": str(rpath),
    }


def action_2026_11_26_exhibition_crosslinks(remote_get, remote_put, log_fn, indexnow_fn=None):
    """2026-11-26: Add exhibition cross-links on service & Singapore pages and verify/expand image-sitemap.xml."""
    receipts = []
    page_blocks = [
        (
            "our-events-and-services.php",
            "fz-daily-2026-11-26-expo-services",
            """
<section id="fz-daily-2026-11-26-expo-services" class="sec-padding" style="background:#ffffff; padding:42px 0; border-top:1px solid #e5e7eb;">
  <div class="container">
    <div class="row">
      <div class="col-lg-10 mx-auto">
        <h2 style="color:#111827; font-size:24px; font-weight:700; margin-bottom:12px;">Custom Exhibition Booths &amp; Enterprise Product Launch Production</h2>
        <p style="color:#4b5563; font-size:15px; line-height:1.7;">Exhibiting at industry conventions or launching flagship technology across APAC? Review our turnkey <a href="/exhibition-and-trade-show-management" style="color:#0d6efd; font-weight:600;">Exhibition &amp; Trade Show Management</a> for 3D stall design, organiser electrical/rigging approvals and QR lead capture, alongside <a href="/product-launch-event-management" style="color:#0d6efd; font-weight:600;">Enterprise Product Launch Event Management</a>.</p>
      </div>
    </div>
  </div>
</section>
""",
            False,
        ),
        (
            "event-management-company-in-singapore.php",
            "fz-daily-2026-11-26-expo-sg",
            """
      <section id="fz-daily-2026-11-26-expo-sg" style="margin:24px 0; padding:20px; background:#f8fafc; border:1px solid #e2e8f0; border-radius:10px;">
        <h2>Trade Show Booth Fabrication &amp; Product Launches in Singapore</h2>
        <p>Exhibitors booking island or peninsula spaces at Singapore EXPO, Suntec Singapore or Sands Expo can appoint Framez through our dedicated <a href="/exhibition-and-trade-show-management">Exhibition &amp; Trade Show Management Services</a> for 3D carpentry, LED backdrops and organiser safety sign-off, or explore <a href="/product-launch-event-management">Product Launch Event Management</a> for press and customer reveal staging.</p>
      </section>
""",
            True,
        ),
    ]

    for fname, marker, block, use_cta in page_blocks:
        cur = remote_get("public_html", fname)
        if not cur:
            return False, f"Failed to read remote {fname}"
        updated = insert_block_idempotent(cur, marker, block, prefer_before_fzguide_cta=use_cta)
        if fname == "event-management-company-in-singapore.php":
            updated = append_fzguide_related(updated, "Exhibition & Trade Show Management", "/exhibition-and-trade-show-management")
        ok, _, receipt = backup_and_upload("2026-11-26-exhibition-crosslinks", fname, cur, updated, remote_get, remote_put, log_fn)
        if not ok:
            return False, f"Failed to upload {fname}"
        receipts.append(receipt)

    img_xml = fetch_remote_or_live(remote_get, "image-sitemap.xml", "https://framez.sg/image-sitemap.xml")
    img_report = {"generated_at": now_utc().isoformat(), "verified": False}
    if img_xml:
        new_xml = clean_dashes(img_xml)
        additions = [
            (
                "https://framez.sg/conference-and-mice-event-management",
                "https://framez.sg/assets/img/our%20work/Framez%20Events%20And%20Productions%20(14).webp",
                "Enterprise Plenary Conference and MICE Management by Framez",
            ),
            (
                "https://framez.sg/exhibition-and-trade-show-management",
                "https://framez.sg/assets/img/our%20work/Framez%20Events%20And%20Productions%20(16).webp",
                "Custom B2B Exhibition Pavilion and Trade Show Booth Fabrication by Framez",
            ),
            (
                "https://framez.sg/product-launch-event-management",
                "https://framez.sg/assets/images/framez-07.webp",
                "Enterprise Product Launch Stage Reveal and Demo Zone by Framez",
            ),
        ]
        blocks_to_add = []
        for page_url, img_loc, img_title in additions:
            if page_url not in new_xml:
                blocks_to_add.append(
                    f"    <url>\n"
                    f"        <loc>{page_url}</loc>\n"
                    f"        <image:image>\n"
                    f"            <image:loc>{img_loc}</image:loc>\n"
                    f"            <image:title>{html_lib.escape(img_title)}</image:title>\n"
                    f"        </image:image>\n"
                    f"    </url>"
                )
        if blocks_to_add and "</urlset>" in new_xml:
            new_xml = new_xml.replace("</urlset>", "\n".join(blocks_to_add) + "\n</urlset>", 1)
        ok, _, img_rec = backup_and_upload("2026-11-26-exhibition-crosslinks", "image-sitemap.xml", img_xml, new_xml, remote_get, remote_put, log_fn)
        if ok:
            receipts.append(img_rec)
        img_locs = re.findall(r"<image:loc>\s*([^<\s]+)\s*</image:loc>", new_xml)
        img_report = {"generated_at": now_utc().isoformat(), "verified": ok, "image_count": len(img_locs), "image_urls": img_locs}

    rpath = save_json_report("image-sitemap-verify-2026-11-26.json", img_report)
    return True, "Added exhibition cross-links and verified image-sitemap.xml.", {
        "target_urls": [
            "https://framez.sg/our-events-and-services",
            "https://framez.sg/event-management-company-in-singapore",
        ],
        "sha256_receipts": receipts,
        "report_path": str(rpath),
    }


def action_2026_11_27_book_demo_estimator(remote_get, remote_put, log_fn, indexnow_fn=None):
    """2026-11-27: Verify/expand book-a-demo.php with RFP scope estimator and FAQPage schema (idempotent)."""
    fname = "book-a-demo.php"
    cur = remote_get("public_html", fname)
    if not cur:
        return False, f"Failed to read remote {fname}"

    faq_schema = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": "What details should we include when booking a Framez event brief walkthrough?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": "Share your event format, preferred city (Singapore, Bangalore or pan-India), expected delegate count, target date window, venue status and key AV or staging priorities so our producers can prepare an itemized scope and cost framework.",
                },
            },
            {
                "@type": "Question",
                "name": "How quickly does Framez return an itemized corporate event scope estimate?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": "Following a brief submission or 20-minute scoping call, our Singapore and Bangalore production teams typically return a structured scope framework and itemized BoQ within 2 to 4 business days.",
                },
            },
            {
                "@type": "Question",
                "name": "Does Framez work under corporate NDAs and ISO 27001 security rules during RFP scoping?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": "Yes. Frame Events and Productions Private Limited operates under ISO 9001:2015 and ISO 27001:2013 practices and executes mutual NDAs prior to reviewing confidential launch roadmaps, internal town halls or executive guest manifests.",
                },
            },
        ],
    }

    updated = inject_jsonld_if_missing(cur, '"FAQPage"', faq_schema)
    words_before = strip_visible_words(updated)
    has_estimator = ("RFP Scope Estimator" in updated or "Enterprise Event Brief" in updated) and words_before >= 700

    if not has_estimator:
        estimator_html = """
<section id="fz-daily-2026-11-27-rfp-estimator" class="sec-padding" style="background:#f9fafb; padding:56px 0; border-top:1px solid #e5e7eb;">
  <div class="container">
    <div class="row">
      <div class="col-lg-10 mx-auto">
        <h2 style="color:#111827; font-size:28px; font-weight:700; margin-bottom:14px;">Enterprise Event Brief &amp; RFP Scope Estimator (Singapore &amp; Bangalore)</h2>
        <p style="color:#4b5563; font-size:15px; line-height:1.7;">To turn your briefing call into an actionable, itemized Bill of Quantities (BoQ) within 2 to 4 business days, Framez maps every corporate inquiry across four production tiers before allocating technical crew, scenic carpentry and venue coordination.</p>
        <div class="table-responsive mt-4 mb-4">
          <table class="table table-bordered bg-white" style="font-size:14px;">
            <thead style="background:#f1f5f9; color:#111827;">
              <tr>
                <th>Programme Tier</th>
                <th>Typical Format &amp; Scale</th>
                <th>Recommended Lead Time</th>
                <th>Core Inclusions Scoped in BoQ</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td><strong>Executive Summit &amp; Media Briefing</strong></td>
                <td>30 to 150 leaders or press guests</td>
                <td>4 to 6 weeks</td>
                <td>CBD hotel boardroom AV, broadcast table mics, NDA access desk, stage backdrop and VIP hospitality.</td>
              </tr>
              <tr>
                <td><strong>Corporate Conference &amp; MICE Programme</strong></td>
                <td>150 to 2,500+ delegates</td>
                <td>10 to 16 weeks</td>
                <td>Plenary LED stage, multi-track breakout AV kits, speaker slide-desk redundancy, QR badge printing and RAMS safety filings.</td>
              </tr>
              <tr>
                <td><strong>Dinner &amp; Dance / Annual Awards Gala</strong></td>
                <td>200 to 3,000+ employees</td>
                <td>10 to 18 weeks</td>
                <td>Theme scenic arch, show-calling cue sheet, winner marshalling, bilingual emcee/live acts, PDPA lucky draw and dietary table mapping.</td>
              </tr>
              <tr>
                <td><strong>Custom Exhibition Booth &amp; Product Launch</strong></td>
                <td>Island stands or multi-city roadshow</td>
                <td>8 to 12 weeks</td>
                <td>3D fabrication renders, organiser structural/electrical approvals, interactive product demo pods and tiered QR lead retrieval.</td>
              </tr>
            </tbody>
          </table>
        </div>
        <h3 style="color:#111827; font-size:21px; font-weight:700; margin-top:24px; margin-bottom:10px;">Six Inputs That Accelerate Your Proposal</h3>
        <ul style="color:#4b5563; font-size:15px; line-height:1.8; padding-left:20px;">
          <li><strong>City and Venue Status:</strong> Confirm whether you are targeting <a href="/event-management-company-in-singapore">Singapore</a>, <a href="/event-management-company-in-bangalore">Bangalore</a> or another Indian metro, and whether a venue is held or needs shortlisting.</li>
          <li><strong>Audience Headcount &amp; Format:</strong> Plenary keynotes, breakout tracks, exhibition stalls, product demos or gala banquet seating.</li>
          <li><strong>Technical &amp; Hybrid Needs:</strong> Wide-screen LED pitch, simultaneous translation, multi-camera recording or two-way watch-party streaming.</li>
          <li><strong>Governance &amp; Compliance:</strong> ISO 9001:2015, ISO 27001:2013 NDA requirements, Singapore PDPA attendee retention rules or India DPDP consent workflows.</li>
          <li><strong>Budget Structure:</strong> Indicate target budget band so our producers separate venue/F&amp;B pass-throughs from production hardware and management fees cleanly (see our <a href="/corporate-event-budget-planning-guide">Corporate Event Budget Planning Guide</a>).</li>
        </ul>
        <h3 style="color:#111827; font-size:21px; font-weight:700; margin-top:24px; margin-bottom:12px;">Frequently Asked Questions About Brief Walkthroughs</h3>
        <p style="color:#4b5563; font-size:15px; line-height:1.6;"><strong>What details should we include when booking a Framez event brief walkthrough?</strong><br>Share your event format, preferred city (Singapore, Bangalore or pan-India), expected delegate count, target date window, venue status and key AV or staging priorities so our producers can prepare an itemized scope and cost framework.</p>
        <p style="color:#4b5563; font-size:15px; line-height:1.6;"><strong>How quickly does Framez return an itemized corporate event scope estimate?</strong><br>Following a brief submission or 20-minute scoping call, our Singapore and Bangalore production teams typically return a structured scope framework and itemized BoQ within 2 to 4 business days.</p>
        <p style="color:#4b5563; font-size:15px; line-height:1.6; margin-bottom:0;"><strong>Does Framez work under corporate NDAs and ISO 27001 security rules during RFP scoping?</strong><br>Yes. Frame Events and Productions Private Limited operates under ISO 9001:2015 and ISO 27001:2013 practices and executes mutual NDAs prior to reviewing confidential launch roadmaps, internal town halls or executive guest manifests.</p>
      </div>
    </div>
  </div>
</section>
"""
        updated = insert_block_idempotent(updated, "fz-daily-2026-11-27-rfp-estimator", estimator_html, prefer_before_fzguide_cta=False)

    ok, _, receipt = backup_and_upload("2026-11-27-book-demo-estimator", fname, cur, updated, remote_get, remote_put, log_fn)
    if not ok:
        return False, f"Failed to upload {fname}"
    words_after = strip_visible_words(updated)
    return True, f"Verified/expanded book-a-demo.php ({words_before} -> {words_after} words, FAQPage & Turnstile intact).", {
        "target_urls": ["https://framez.sg/book-a-demo"],
        "sha256_receipts": [receipt],
        "words_before": words_before,
        "words_after": words_after,
    }


def action_2026_11_28_seasonal_townhall_sko(remote_get, remote_put, log_fn, indexnow_fn=None):
    """2026-11-28: Add Q4/Q1 town hall & SKO seasonal internal anchors on corporate-event-management-company.php and event-planner.php."""
    receipts = []
    targets = [
        (
            "corporate-event-management-company.php",
            "fz-daily-2026-11-28-townhall-corp",
            """
<section id="fz-daily-2026-11-28-townhall-corp" class="sec-padding" style="background:#f8fafc; padding:48px 0; border-top:1px solid #e5e7eb;">
  <div class="container">
    <div class="row">
      <div class="col-lg-10 mx-auto">
        <h2 style="color:#111827; font-size:26px; font-weight:700; margin-bottom:12px;">Q4 Year-End Town Halls &amp; Q1 Sales Kickoff (SKO) Production</h2>
        <p style="color:#4b5563; font-size:15px; line-height:1.7;">Closing Q4 with an all-hands town hall or mobilizing Q1 Sales Kickoffs across Singapore and Bangalore offices requires tight speaker timing, isolated broadcast audio mixes and multi-hub failover networking. Pair our <a href="/conference-and-mice-event-management" style="color:#0d6efd; font-weight:600;">Conference &amp; MICE Event Management</a> delivery with our <a href="/annual-day-and-awards-night-planning-guide" style="color:#0d6efd; font-weight:600;">Annual Day &amp; Awards Night Planning Guide</a> or <a href="/dinner-and-dance-event-management-singapore" style="color:#0d6efd; font-weight:600;">Singapore Dinner &amp; Dance Management</a>.</p>
      </div>
    </div>
  </div>
</section>
""",
            False,
        ),
        (
            "event-planner.php",
            "fz-daily-2026-11-28-townhall-planner",
            """
      <section id="fz-daily-2026-11-28-townhall-planner" style="margin:24px 0; padding:20px; background:#f8fafc; border:1px solid #e2e8f0; border-radius:10px;">
        <h2>Seasonal Readiness: Year-End Town Halls &amp; Q1 Sales Kickoffs (SKOs)</h2>
        <p>Internal comms and revenue enablement leaders preparing Q4 all-hands town halls or Q1 Sales Kickoffs across Singapore and Bangalore can consolidate keynote staging, breakout rooms and two-way remote watch-party streams through our <a href="/conference-and-mice-event-management">Conference &amp; MICE Event Management</a> and <a href="/dinner-and-dance-event-management-singapore">Singapore Dinner &amp; Dance</a> teams. <a href="/book-a-demo">Share your Q4/Q1 brief</a> early to lock peak hotel ballroom slots.</p>
      </section>
""",
            True,
        ),
    ]

    for fname, marker, block, use_cta in targets:
        cur = remote_get("public_html", fname)
        if not cur:
            return False, f"Failed to read remote {fname}"
        updated = insert_block_idempotent(cur, marker, block, prefer_before_fzguide_cta=use_cta)
        if fname == "event-planner.php":
            updated = append_fzguide_related(updated, "Conference & MICE Management", "/conference-and-mice-event-management")
        ok, _, receipt = backup_and_upload("2026-11-28-seasonal-townhall", fname, cur, updated, remote_get, remote_put, log_fn)
        if not ok:
            return False, f"Failed to upload {fname}"
        receipts.append(receipt)

    return True, "Injected Q4/Q1 town hall & SKO seasonal internal anchors.", {
        "target_urls": [
            "https://framez.sg/corporate-event-management-company",
            "https://framez.sg/event-planner",
        ],
        "sha256_receipts": receipts,
    }


def action_2026_11_30_mid_cycle_ctr_audit(remote_get, remote_put, log_fn, indexnow_fn=None):
    """2026-11-30: Analyze latest-gsc.json and write reports/mid-cycle-ctr-audit.json."""
    gsc_path = REPORT_DIR / "latest-gsc.json"
    gsc = load_json_safe(gsc_path, {})
    if not gsc:
        return False, f"Missing or unreadable {gsc_path}"

    w28 = gsc.get("window_28d") or {}
    totals = ((w28.get("totals") or {}).get("rows") or [{}])[0]
    countries = {
        (r.get("keys") or [""])[0]: {
            "clicks": r.get("clicks", 0),
            "impressions": r.get("impressions", 0),
            "ctr": round(float(r.get("ctr", 0.0)), 4),
            "position": round(float(r.get("position", 0.0)), 2),
        }
        for r in (w28.get("countries") or {}).get("rows") or []
    }
    pages = (w28.get("top_pages") or {}).get("rows") or []
    page1_zero_ctr = []
    page2_climbing = []
    for r in pages:
        url = (r.get("keys") or [""])[0]
        pos = float(r.get("position", 99.0))
        imp = int(r.get("impressions", 0))
        clicks = int(r.get("clicks", 0))
        ctr = float(r.get("ctr", 0.0))
        entry = {"url": url, "clicks": clicks, "impressions": imp, "ctr": round(ctr, 4), "position": round(pos, 2)}
        if pos <= 10.5 and imp >= 3 and ctr < 0.02:
            page1_zero_ctr.append(entry)
        elif 10.5 < pos <= 25.0 and imp >= 5:
            page2_climbing.append(entry)

    queries = _extract_gsc_queries(gsc)
    page2_queries = [q for q in queries if 10.5 < q["position"] <= 30.0]
    page2_queries.sort(key=lambda x: (-x["impressions"], x["position"]))

    audit_payload = {
        "generated_at": now_utc().isoformat(),
        "date_sgt": "2026-11-30",
        "source_gsc_generated_at": gsc.get("generated_at"),
        "window_28d": {"start": w28.get("start"), "end": w28.get("end")},
        "site_totals_28d": {
            "clicks": totals.get("clicks", 0),
            "impressions": totals.get("impressions", 0),
            "ctr": round(float(totals.get("ctr", 0.0)), 4),
            "position": round(float(totals.get("position", 0.0)), 2),
        },
        "country_breakdown": {k: countries[k] for k in ("sgp", "ind", "usa") if k in countries},
        "page1_low_ctr_pages": sorted(page1_zero_ctr, key=lambda x: -x["impressions"]),
        "page2_climbing_pages": sorted(page2_climbing, key=lambda x: -x["impressions"]),
        "page2_target_queries": page2_queries[:25],
    }

    rpath = save_json_report("mid-cycle-ctr-audit.json", audit_payload)
    log_fn(
        f"2026-11-30: wrote {rpath.name} (p1_low_ctr={len(page1_zero_ctr)}, p2_pages={len(page2_climbing)}, p2_queries={len(page2_queries)})"
    )
    return True, f"Mid-cycle CTR audit written ({len(page1_zero_ctr)} Page-1 low-CTR pages, {len(page2_climbing)} Page-2 pages).", {
        "report_path": str(rpath),
        "p1_low_ctr_count": len(page1_zero_ctr),
        "p2_climbing_count": len(page2_climbing),
    }


def action_2026_12_01_llms_parity_sync(remote_get, remote_put, log_fn, indexnow_fn=None):
    """2026-12-01: Sync live llms.txt & llms-full.txt with sitemap inventory, upload via remote_put, and push IndexNow."""
    smap_xml = fetch_remote_or_live(remote_get, "sitemap.xml", "https://framez.sg/sitemap.xml") or ""
    sitemap_urls = parse_sitemap_locs(smap_xml)
    if not sitemap_urls:
        latest_audit = load_json_safe(REPORT_DIR / "latest-audit.json", {})
        sitemap_urls = [p.get("url") for p in latest_audit.get("pages", []) if p.get("url")]

    receipts = []
    added_urls = []
    parity_summary = {}

    for fname in ("llms.txt", "llms-full.txt"):
        cur = fetch_remote_or_live(remote_get, fname, f"https://framez.sg/{fname}") or ""
        updated = clean_dashes(cur)

        nap_note = (
            "Legal Entity: Frame Events and Productions Private Limited (Brand: Framez) | "
            "ISO 9001:2015 & ISO 27001:2013 Certified | "
            "Singapore Office: 30 Cecil Street, #19-08 Prudential Tower, Singapore 049712 | "
            "India HQ: B/2, GANGA, 3rd Floor, 5th Block, KHB Colony, Koramangala, Bengaluru, Karnataka 560095"
        )
        if (
            "Prudential Tower" not in updated
            or "Koramangala" not in updated
            or "ISO 9001:2015" not in updated
            or "Frame Events and Productions Private Limited" not in updated
        ):
            updated = updated.rstrip() + f"\n\n## Verified Entity & Dual-HQ Profile\n\n- {nap_note}\n"

        missing_lines = []
        for u in sitemap_urls:
            if u not in updated:
                slug = u.rstrip("/").rsplit("/", 1)[-1] or "home"
                label = "Home" if slug == "framez.sg" else slug.replace("-", " ").title()
                missing_lines.append(f"- [{label}]({u})")
                if u not in added_urls:
                    added_urls.append(u)

        if missing_lines:
            if "## Synced Sitemap Inventory" not in updated:
                updated = updated.rstrip() + "\n\n## Synced Sitemap Inventory\n\n"
            else:
                updated = updated.rstrip() + "\n"
            updated += "\n".join(missing_lines) + "\n"

        ok, _, rec = backup_and_upload("2026-12-01-llms-sync", fname, cur, updated, remote_get, remote_put, log_fn)
        if not ok:
            return False, f"Failed to upload {fname}"
        receipts.append(rec)
        parity_summary[fname] = {
            "sitemap_urls_checked": len(sitemap_urls),
            "missing_before": len(missing_lines),
            "parity_complete": all(u in updated for u in sitemap_urls),
        }

    ping_targets = ["https://framez.sg/llms.txt", "https://framez.sg/llms-full.txt"] + added_urls
    idx_res = ping_indexnow(ping_targets, log_fn, indexnow_fn=indexnow_fn)
    rpath = save_json_report("llms-parity-2026-12-01.json", {
        "generated_at": now_utc().isoformat(),
        "parity": parity_summary,
        "indexnow": idx_res,
    })
    return True, f"Synced llms.txt & llms-full.txt against {len(sitemap_urls)} sitemap URLs and pinged IndexNow.", {
        "target_urls": ["https://framez.sg/llms.txt", "https://framez.sg/llms-full.txt"],
        "sha256_receipts": receipts,
        "indexnow": idx_res,
        "report_path": str(rpath),
    }


def action_2026_12_02_bangalore_tech_corridors(remote_get, remote_put, log_fn, indexnow_fn=None):
    """2026-12-02: Reinforce Koramangala, Whitefield, ORR & BIEC/KTPO entities on Bangalore and India pages."""
    receipts = []
    targets = [
        (
            "event-management-company-in-bangalore.php",
            "fz-daily-2026-12-02-blr-corridors",
            """
<section id="fz-daily-2026-12-02-blr-corridors" class="sec-padding" style="background:#ffffff; padding:44px 0; border-top:1px solid #e5e7eb;">
  <div class="container">
    <div class="row">
      <div class="col-lg-10 mx-auto">
        <h2 style="color:#111827; font-size:24px; font-weight:700; margin-bottom:12px;">Trade Exhibition &amp; Tech-Park Hub Coverage: BIEC, KTPO, Whitefield &amp; ORR</h2>
        <p style="color:#4b5563; font-size:15px; line-height:1.7;">From Global Capability Centre (GCC) summits along Outer Ring Road and Whitefield to heavy-freight industry expos at <strong>BIEC (Bengaluru International Exhibition Centre)</strong> and <strong>KTPO (Karnataka Trade Promotion Organisation)</strong>, our Koramangala production desk manages clear-span rigging, silent DG power, <a href="/exhibition-and-trade-show-management" style="color:#0d6efd; font-weight:600;">custom trade-show booth fabrication</a> and <a href="/corporate-annual-day-and-awards-night-management" style="color:#0d6efd; font-weight:600;">corporate annual days &amp; awards nights</a>.</p>
      </div>
    </div>
  </div>
</section>
""",
            False,
        ),
        (
            "event-management-company-in-india.php",
            "fz-daily-2026-12-02-india-corridors",
            """
      <section id="fz-daily-2026-12-02-india-corridors" style="margin:24px 0; padding:20px; background:#f8fafc; border:1px solid #e2e8f0; border-radius:10px;">
        <h2>Bengaluru Hub Execution: Koramangala HQ, Whitefield, ORR, BIEC &amp; KTPO</h2>
        <p>National roadshows and multi-city conferences originating from our Bengaluru headquarters pair regional scale with ground-level logistics across Koramangala, Whitefield, Outer Ring Road, BIEC and KTPO. Explore dedicated <a href="/exhibition-and-trade-show-management">Exhibition &amp; Trade Show Management</a>, <a href="/conference-and-mice-event-management">Conference &amp; MICE Services</a> and <a href="/corporate-annual-day-and-awards-night-management">Annual Day &amp; Awards Night Management</a>.</p>
      </section>
""",
            True,
        ),
    ]

    for fname, marker, block, use_cta in targets:
        cur = remote_get("public_html", fname)
        if not cur:
            return False, f"Failed to read remote {fname}"
        updated = insert_block_idempotent(cur, marker, block, prefer_before_fzguide_cta=use_cta)
        if fname == "event-management-company-in-india.php":
            updated = append_fzguide_related(updated, "Exhibition & Trade Show Management", "/exhibition-and-trade-show-management")
        ok, _, receipt = backup_and_upload("2026-12-02-blr-corridors", fname, cur, updated, remote_get, remote_put, log_fn)
        if not ok:
            return False, f"Failed to upload {fname}"
        receipts.append(receipt)

    return True, "Reinforced Koramangala, Whitefield, ORR, BIEC and KTPO entities across Bangalore and India pages.", {
        "target_urls": [
            "https://framez.sg/event-management-company-in-bangalore",
            "https://framez.sg/event-management-company-in-india",
        ],
        "sha256_receipts": receipts,
    }


def action_2026_12_04_offsite_crosslinks(remote_get, remote_put, log_fn, indexnow_fn=None):
    """2026-12-04: Cross-link executive-offsite-retreat-blueprint.php with Bangalore checklist and SG page."""
    receipts = []
    targets = [
        (
            "executive-offsite-retreat-blueprint.php",
            "fz-daily-2026-12-04-offsite-links",
            """
<section id="fz-daily-2026-12-04-offsite-links" class="sec-padding" style="background:#f8fafc; padding:44px 0; border-top:1px solid #e5e7eb;">
  <div class="container">
    <div class="row">
      <div class="col-lg-10 mx-auto">
        <h2 style="color:#111827; font-size:24px; font-weight:700; margin-bottom:12px;">Regional Offsite Logistics: Singapore &amp; Bangalore Planning Resources</h2>
        <p style="color:#4b5563; font-size:15px; line-height:1.7;">Coordinating leadership travel, resort buyouts or silent-generator stage setups for South India or Singapore retreats? Pair this blueprint with our <a href="/bangalore-corporate-event-venue-and-logistics-checklist" style="color:#0d6efd; font-weight:600;">Bangalore Corporate Event Venue &amp; Logistics Checklist</a>, our <a href="/event-management-company-in-singapore" style="color:#0d6efd; font-weight:600;">Singapore Corporate Event Management</a> hub, and our <a href="/event-management-company-in-bangalore" style="color:#0d6efd; font-weight:600;">Bangalore Event Management</a> team.</p>
      </div>
    </div>
  </div>
</section>
""",
        ),
        (
            "event-management-company-in-bangalore.php",
            "fz-daily-2026-12-04-blr-checklist-link",
            """
<section id="fz-daily-2026-12-04-blr-checklist-link" class="sec-padding" style="background:#f9fafb; padding:32px 0;">
  <div class="container">
    <div class="row">
      <div class="col-lg-10 mx-auto">
        <p style="color:#4b5563; font-size:15px; line-height:1.7; margin:0;">Before signing a hotel or resort venue contract in Bengaluru, review our <a href="/bangalore-corporate-event-venue-and-logistics-checklist" style="color:#0d6efd; font-weight:600;">Bangalore Corporate Event Venue &amp; Logistics Checklist</a> and <a href="/executive-offsite-retreat-blueprint" style="color:#0d6efd; font-weight:600;">Executive Offsite Retreat Blueprint</a> for DG power, acoustic cut-offs and corridor travel windows.</p>
      </div>
    </div>
  </div>
</section>
""",
        ),
    ]

    for fname, marker, block in targets:
        cur = remote_get("public_html", fname)
        if not cur:
            return False, f"Failed to read remote {fname}"
        updated = insert_block_idempotent(cur, marker, block, prefer_before_fzguide_cta=False)
        ok, _, receipt = backup_and_upload("2026-12-04-offsite-crosslinks", fname, cur, updated, remote_get, remote_put, log_fn)
        if not ok:
            return False, f"Failed to upload {fname}"
        receipts.append(receipt)

    return True, "Cross-linked executive offsite blueprint with Bangalore checklist and Singapore page.", {
        "target_urls": [
            "https://framez.sg/executive-offsite-retreat-blueprint",
            "https://framez.sg/event-management-company-in-bangalore",
        ],
        "sha256_receipts": receipts,
    }


def action_2026_12_05_green_mice_prep(remote_get, remote_put, log_fn, indexnow_fn=None):
    """2026-12-05: Pre-flight Singapore Green Plan 2030 & STB MICE sustainability block on SG page."""
    fname = "event-management-company-in-singapore.php"
    cur = remote_get("public_html", fname)
    if not cur:
        return False, f"Failed to read remote {fname}"

    green_block = """
      <section id="fz-daily-2026-12-05-green-mice-sg" style="margin:24px 0; padding:20px; background:#f0fdf4; border:1px solid #bbf7d0; border-radius:10px;">
        <h2>Singapore Green Plan 2030 &amp; Sustainable MICE Delivery</h2>
        <p>In support of enterprise ESG procurement mandates and the <strong>Singapore Green Plan 2030</strong> / <strong>Singapore Tourism Board (STB) MICE sustainability framework</strong>, Framez designs modular aluminium scenic frames, reusable LED screen backdrops in place of single-use PVC flex, QR digital wayfinding and MRT-accessible BCA Green Mark venue pairings. Review our NDA-safe <a href="/corporate-event-case-studies">Corporate Event Production Dossiers</a> for regional venue specifications.</p>
      </section>
"""
    updated = insert_block_idempotent(cur, "fz-daily-2026-12-05-green-mice-sg", green_block, prefer_before_fzguide_cta=True)
    ok, _, receipt = backup_and_upload("2026-12-05-green-mice-prep", fname, cur, updated, remote_get, remote_put, log_fn)
    if not ok:
        return False, f"Failed to upload {fname}"

    rpath = save_json_report("preflight-wave6-green-mice.json", {
        "generated_at": now_utc().isoformat(),
        "date_sgt": "2026-12-05",
        "upcoming_wave": "wave6_2026_12_07",
        "target_slug": "sustainable-corporate-events-esg-guide-singapore-india",
        "entities": ["Singapore Green Plan 2030", "STB MICE Sustainability", "BCA Green Mark", "Modular Aluminium Staging", "Recyclable Paper Badges"],
    })
    return True, "Added Singapore Green Plan 2030 & STB MICE sustainability pre-flight block.", {
        "target_urls": ["https://framez.sg/event-management-company-in-singapore"],
        "sha256_receipts": [receipt],
        "report_path": str(rpath),
    }


def action_2026_12_06_sustainable_rfp_llms_prep(remote_get, remote_put, log_fn, indexnow_fn=None):
    """2026-12-06: Modular staging entity block + llms-full.txt pre-Wave-6 prep."""
    receipts = []
    for fname, marker, block in [
        (
            "conference-and-mice-event-management.php",
            "fz-daily-2026-12-06-modular-staging",
            """
      <section id="fz-daily-2026-12-06-modular-staging" style="margin:24px 0; padding:20px; background:#f8fafc; border:1px solid #e2e8f0; border-radius:10px;">
        <h2>Modular Staging &amp; Low-Waste Enterprise RFP Readiness</h2>
        <p>Multi-city corporate roadshows and regional conferences cut build waste significantly by swapping disposable MDF carpentry and date-stamped PVC flex for modular aluminium trussing, reusable tension-fabric prints and programmable LED walls. Review real regional builds in our <a href="/corporate-event-case-studies">Corporate Event Production Dossiers</a>.</p>
      </section>
""",
        ),
    ]:
        cur = remote_get("public_html", fname)
        if not cur:
            return False, f"Failed to read remote {fname}"
        updated = insert_block_idempotent(cur, marker, block, prefer_before_fzguide_cta=True)
        ok, _, rec = backup_and_upload("2026-12-06-sustainable-rfp-prep", fname, cur, updated, remote_get, remote_put, log_fn)
        if not ok:
            return False, f"Failed to upload {fname}"
        receipts.append(rec)

    exh_cur = remote_get("public_html", "exhibition-and-trade-show-management.php")
    if exh_cur:
        exh_block = """
      <section id="fz-daily-2026-12-06-modular-exhibition" style="margin:24px 0; padding:20px; background:#f8fafc; border:1px solid #e2e8f0; border-radius:10px;">
        <h2>Low-Waste Modular Exhibition Architecture</h2>
        <p>Enterprise exhibitors running 3 to 8 annual shows can reuse modular aluminium structural frames and programmable LED fascias across <a href="/event-management-company-in-singapore">Singapore</a> and <a href="/event-management-company-in-bangalore">Bangalore</a>, eliminating disposable carpentry waste. View specifications in our <a href="/corporate-event-case-studies">Corporate Event Production Dossiers</a>.</p>
      </section>
"""
        exh_upd = insert_block_idempotent(exh_cur, "fz-daily-2026-12-06-modular-exhibition", exh_block, prefer_before_fzguide_cta=True)
        ok_exh, _, rec_exh = backup_and_upload("2026-12-06-sustainable-rfp-prep", "exhibition-and-trade-show-management.php", exh_cur, exh_upd, remote_get, remote_put, log_fn)
        if not ok_exh:
            return False, "Failed to upload exhibition-and-trade-show-management.php"
        receipts.append(rec_exh)

    llms_full = fetch_remote_or_live(remote_get, "llms-full.txt", "https://framez.sg/llms-full.txt") or ""
    updated_llms = clean_dashes(llms_full)
    if "Modular Aluminium & LED Staging" not in updated_llms:
        updated_llms = updated_llms.rstrip() + (
            "\n\n## Sustainable & Modular Production Standards\n\n"
            "- **Modular Aluminium & LED Staging**: Reusable stage frames, tension-fabric graphics and digital signage supporting Singapore Green Plan 2030 and enterprise ESG RFP requirements.\n"
            "- [Corporate Event Production Dossiers (NDA-Safe)](https://framez.sg/corporate-event-case-studies): SG & BLR operational archetypes and venue technical matrix\n"
            "- [Dinner & Dance Event Management Singapore](https://framez.sg/dinner-and-dance-event-management-singapore): Singapore D&D ballroom production\n"
            "- [Product Launch Event Management](https://framez.sg/product-launch-event-management): stage reveals and live demo zones\n"
            "- [Annual Day & Awards Night Management](https://framez.sg/corporate-annual-day-and-awards-night-management): corporate employee celebrations\n"
        )
        updated_llms = clean_dashes(updated_llms)

    ok, _, llms_rec = backup_and_upload("2026-12-06-sustainable-rfp-prep", "llms-full.txt", llms_full, updated_llms, remote_get, remote_put, log_fn)
    if not ok:
        return False, "Failed to upload llms-full.txt"
    receipts.append(llms_rec)

    return True, "Prepared modular staging block and refreshed llms-full.txt ahead of Wave 6.", {
        "target_urls": [
            "https://framez.sg/conference-and-mice-event-management",
            "https://framez.sg/llms-full.txt",
        ],
        "sha256_receipts": receipts,
    }


def action_2026_12_08_esg_crosslinks(remote_get, remote_put, log_fn, indexnow_fn=None):
    """2026-12-08: Cross-link /sustainable-corporate-events-esg-guide-singapore-india from SG and RFP pages."""
    receipts = []
    targets = [
        (
            "event-management-company-in-singapore.php",
            "fz-daily-2026-12-08-esg-sg",
            """
      <section id="fz-daily-2026-12-08-esg-sg" style="margin:24px 0; padding:20px; background:#f8fafc; border:1px solid #e2e8f0; border-radius:10px;">
        <h2>ESG &amp; Green MICE Procurement Framework</h2>
        <p>Preparing an MNC sustainability tender in Singapore? Review our dedicated <a href="/sustainable-corporate-events-esg-guide-singapore-india">Sustainable Corporate Events &amp; Green MICE Planning Guide</a> for modular staging comparisons, digital badge recovery and transparent post-event production metrics.</p>
      </section>
""",
            True,
        ),
        (
            "b2b-event-agency-rfp-evaluation-guide.php",
            "fz-daily-2026-12-08-esg-rfp",
            """
<section id="fz-daily-2026-12-08-esg-rfp" class="sec-padding" style="background:#f8fafc; padding:44px 0; border-top:1px solid #e5e7eb;">
  <div class="container">
    <div class="row">
      <div class="col-lg-10 mx-auto">
        <h2 style="color:#111827; font-size:24px; font-weight:700; margin-bottom:12px;">Adding ESG &amp; Green MICE Scoring Criteria to Your Event Agency RFP</h2>
        <p style="color:#4b5563; font-size:15px; line-height:1.7;">Enterprise procurement teams scoring vendors on waste reduction, reusable aluminium/LED staging and transparent materials reporting can incorporate clauses from our <a href="/sustainable-corporate-events-esg-guide-singapore-india" style="color:#0d6efd; font-weight:600;">Sustainable Corporate Events &amp; ESG Guide</a> alongside our <a href="/event-management-company-in-singapore" style="color:#0d6efd; font-weight:600;">Singapore Corporate Event Management</a> and <a href="/corporate-event-case-studies" style="color:#0d6efd; font-weight:600;">Production Dossiers</a>.</p>
      </div>
    </div>
  </div>
</section>
""",
            False,
        ),
    ]

    for fname, marker, block, use_cta in targets:
        cur = remote_get("public_html", fname)
        if not cur:
            return False, f"Failed to read remote {fname}"
        updated = insert_block_idempotent(cur, marker, block, prefer_before_fzguide_cta=use_cta)
        if fname == "event-management-company-in-singapore.php":
            updated = append_fzguide_related(updated, "Sustainable Corporate Events Guide", "/sustainable-corporate-events-esg-guide-singapore-india")
        ok, _, receipt = backup_and_upload("2026-12-08-esg-crosslinks", fname, cur, updated, remote_get, remote_put, log_fn)
        if not ok:
            return False, f"Failed to upload {fname}"
        receipts.append(receipt)

    return True, "Cross-linked Sustainable Corporate Events ESG guide from Singapore and RFP evaluation pages.", {
        "target_urls": [
            "https://framez.sg/event-management-company-in-singapore",
            "https://framez.sg/b2b-event-agency-rfp-evaluation-guide",
        ],
        "sha256_receipts": receipts,
    }


def action_2026_12_09_cwv_asset_audit(remote_get, remote_put, log_fn, indexnow_fn=None):
    """2026-12-09: Sitewide CWV and asset bloat verification audit writing reports/cwv-asset-audit.json."""
    smap_xml = fetch_remote_or_live(remote_get, "sitemap.xml", "https://framez.sg/sitemap.xml") or ""
    urls = parse_sitemap_locs(smap_xml)
    if not urls:
        latest_audit = load_json_safe(REPORT_DIR / "latest-audit.json", {})
        urls = [p.get("url") for p in latest_audit.get("pages", []) if p.get("url")]

    pages_checked = []
    bloat_hits_total = 0
    for u in urls:
        entry = {"url": u, "status": None, "html_bytes": 0, "legacy_bloat_markers": [], "imgs_total": 0, "imgs_missing_dims": 0, "imgs_missing_lazy": 0, "blocking_scripts": 0, "ga4_count": 0}
        try:
            req = urllib.request.Request(u, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = resp.read().decode("utf-8", "ignore")
                entry["status"] = resp.status
            entry["html_bytes"] = len(body)
            entry["legacy_bloat_markers"] = [m for m in LEGACY_BLOAT_MARKERS if m in body]
            bloat_hits_total += len(entry["legacy_bloat_markers"])
            imgs = re.findall(r"<img\b[^>]*>", body, re.I)
            entry["imgs_total"] = len(imgs)
            entry["imgs_missing_dims"] = sum(1 for i in imgs if not (re.search(r"\bwidth\s*=", i, re.I) and re.search(r"\bheight\s*=", i, re.I)))
            entry["imgs_missing_lazy"] = sum(1 for i in imgs if not re.search(r"\bloading\s*=", i, re.I))
            scripts = re.findall(r"<script\b[^>]*\bsrc=[^>]*>", body, re.I)
            entry["blocking_scripts"] = sum(1 for s in scripts if not re.search(r"\b(async|defer)\b", s, re.I))
            entry["ga4_count"] = len(re.findall(r"gtag\(['\"]config['\"],\s*['\"]" + GA4_ID + r"['\"]", body))
        except Exception as exc:
            entry["error"] = str(exc)
        pages_checked.append(entry)

    payload = {
        "generated_at": now_utc().isoformat(),
        "date_sgt": "2026-12-09",
        "urls_audited": len(pages_checked),
        "legacy_bloat_hits_total": bloat_hits_total,
        "pages": pages_checked,
    }
    rpath = save_json_report("cwv-asset-audit.json", payload)
    log_fn(f"2026-12-09: CWV asset audit complete across {len(pages_checked)} URLs (bloat_hits={bloat_hits_total})")
    return True, f"CWV & asset bloat audit saved for {len(pages_checked)} URLs ({bloat_hits_total} legacy bloat hits).", {
        "report_path": str(rpath),
        "urls_audited": len(pages_checked),
        "legacy_bloat_hits_total": bloat_hits_total,
    }


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _inspect_redirect_chain(url, max_hops=5):
    opener = urllib.request.build_opener(_NoRedirectHandler)
    hops = []
    cur = url
    for _ in range(max_hops):
        try:
            req = urllib.request.Request(cur, headers={"User-Agent": UA})
            with opener.open(req, timeout=10) as resp:
                body = resp.read().decode("utf-8", "ignore")
                canon_m = re.search(r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']*)', body, re.I)
                return {
                    "initial_url": url,
                    "final_url": cur,
                    "final_status": resp.status,
                    "hops": hops,
                    "hop_count": len(hops),
                    "canonical": canon_m.group(1).strip() if canon_m else "",
                }
        except urllib.error.HTTPError as exc:
            if exc.code in (301, 302, 307, 308):
                loc = exc.headers.get("Location", "")
                nxt = urllib.parse.urljoin(cur, loc)
                hops.append({"from": cur, "status": exc.code, "to": nxt})
                cur = nxt
                continue
            return {"initial_url": url, "final_url": cur, "final_status": exc.code, "hops": hops, "hop_count": len(hops), "canonical": ""}
        except Exception as exc:
            return {"initial_url": url, "final_url": cur, "final_status": None, "hops": hops, "hop_count": len(hops), "error": str(exc)}
    return {"initial_url": url, "final_url": cur, "final_status": None, "hops": hops, "hop_count": len(hops), "error": "too_many_redirects"}


def action_2026_12_10_redirect_canonical_audit(remote_get, remote_put, log_fn, indexnow_fn=None):
    """2026-12-10: Full redirect and canonical hygiene verification crawl writing reports/redirect-canonical-audit.json."""
    smap_xml = fetch_remote_or_live(remote_get, "sitemap.xml", "https://framez.sg/sitemap.xml") or ""
    canonical_urls = parse_sitemap_locs(smap_xml)
    if not canonical_urls:
        latest_audit = load_json_safe(REPORT_DIR / "latest-audit.json", {})
        canonical_urls = [p.get("url") for p in latest_audit.get("pages", []) if p.get("url")]

    legacy_checks = [
        "https://framez.sg/get-to-know-us",
        "https://framez.sg/our-team",
        "https://framez.sg/social-event",
        "https://framez.sg/corporate-event-management-company.php",
        "https://framez.sg/event-management-company-in-singapore.php",
        "https://www.framez.sg/",
    ]

    canonical_results = []
    issues = []
    for u in canonical_urls:
        res = _inspect_redirect_chain(u)
        self_canon_ok = res.get("canonical", "").rstrip("/") == u.rstrip("/") and res.get("final_status") == 200 and res.get("hop_count", 0) == 0
        res["hygiene_ok"] = self_canon_ok
        if not self_canon_ok:
            issues.append({"url": u, "status": res.get("final_status"), "hops": res.get("hop_count"), "canonical": res.get("canonical")})
        canonical_results.append(res)

    legacy_results = [_inspect_redirect_chain(u) for u in legacy_checks]
    payload = {
        "generated_at": now_utc().isoformat(),
        "date_sgt": "2026-12-10",
        "canonical_checked": len(canonical_results),
        "canonical_issues_count": len(issues),
        "canonical_issues": issues,
        "legacy_redirect_checks": legacy_results,
        "canonical_results": canonical_results,
    }
    rpath = save_json_report("redirect-canonical-audit.json", payload)
    log_fn(f"2026-12-10: redirect & canonical hygiene checked {len(canonical_results)} canonicals + {len(legacy_results)} legacy URLs (issues={len(issues)})")
    return True, f"Redirect & canonical hygiene crawl finished ({len(canonical_results)} canonicals, {len(issues)} issues).", {
        "report_path": str(rpath),
        "canonical_issues_count": len(issues),
    }


def action_2026_12_11_ranking_velocity_rollup(remote_get, remote_put, log_fn, indexnow_fn=None):
    """2026-12-11: End-of-cycle ranking velocity rollup using latest-gsc.json and cycle-start baseline."""
    gsc = load_json_safe(REPORT_DIR / "latest-gsc.json", {})
    if not gsc:
        return False, "Missing reports/latest-gsc.json"

    baseline = load_json_safe(REPORT_DIR / "monthly-snapshots" / "cycle-start-2026-11-18.json", {})
    base_gsc = (baseline.get("gsc") or {}).get("window_28d") or {}
    cur_28 = gsc.get("window_28d") or {}
    cur_7 = gsc.get("window_7d") or {}

    def _country_map(w):
        return {
            (r.get("keys") or [""])[0]: r
            for r in ((w.get("countries") or {}).get("rows") or [])
        }

    cur_countries = _country_map(cur_28)
    base_countries = _country_map(base_gsc)
    cur_tot = ((cur_28.get("totals") or {}).get("rows") or [{}])[0]
    cur_7_tot = ((cur_7.get("totals") or {}).get("rows") or [{}])[0]

    sg_cur = cur_countries.get("sgp", {})
    in_cur = cur_countries.get("ind", {})
    sg_base = base_countries.get("sgp", {})
    in_base = base_countries.get("ind", {})

    top_queries = sorted(_extract_gsc_queries(gsc), key=lambda x: (-x["clicks"], -x["impressions"]))[:30]
    payload = {
        "generated_at": now_utc().isoformat(),
        "date_sgt": "2026-12-11",
        "gsc_generated_at": gsc.get("generated_at"),
        "window_28d": {"start": cur_28.get("start"), "end": cur_28.get("end"), "totals": cur_tot},
        "window_7d": {"start": cur_7.get("start"), "end": cur_7.get("end"), "totals": cur_7_tot},
        "singapore_28d": sg_cur,
        "india_28d": in_cur,
        "delta_vs_nov18_baseline": {
            "sgp_clicks_delta": sg_cur.get("clicks", 0) - sg_base.get("clicks", 0) if sg_base else None,
            "sgp_impressions_delta": sg_cur.get("impressions", 0) - sg_base.get("impressions", 0) if sg_base else None,
            "ind_clicks_delta": in_cur.get("clicks", 0) - in_base.get("clicks", 0) if in_base else None,
            "ind_impressions_delta": in_cur.get("impressions", 0) - in_base.get("impressions", 0) if in_base else None,
        },
        "top_queries": top_queries,
    }
    rpath = save_json_report("ranking-velocity-rollup.json", payload)
    log_fn(f"2026-12-11: saved ranking velocity rollup to {rpath.name}")
    return True, f"Ranking velocity rollup complete (28d clicks={cur_tot.get('clicks', 0)}, impressions={cur_tot.get('impressions', 0)}).", {
        "report_path": str(rpath),
    }


def action_2026_12_12_lead_turnstile_audit(remote_get, remote_put, log_fn, indexnow_fn=None):
    """2026-12-12: Privacy-safe aggregate lead & Turnstile security integrity audit (zero PII)."""
    leads_raw = remote_get("public_html", "leads_log.json") or "[]"
    spam_raw = remote_get("public_html", "leads_spam_log.json") or "[]"

    try:
        leads_arr = json.loads(leads_raw)
        if not isinstance(leads_arr, list):
            leads_arr = []
    except Exception:
        leads_arr = []

    try:
        stxt = spam_raw.strip()
        if stxt.startswith("["):
            spam_arr = json.loads(stxt)
        else:
            spam_arr = [json.loads(ln) for ln in stxt.splitlines() if ln.strip()]
    except Exception:
        spam_arr = []

    def _since_nov15(items):
        cnt = 0
        for item in items:
            if not isinstance(item, dict):
                continue
            ts = str(item.get("timestamp") or item.get("time") or item.get("date") or item.get("created_at") or "")
            if ts >= "2026-11-15":
                cnt += 1
        return cnt

    form_checks = {}
    for fname, expected_action in (("get-in-touch.php", "contact-submit"), ("book-a-demo.php", "submit-demo")):
        html_src = remote_get("public_html", fname) or ""
        form_checks[fname] = {
            "turnstile_present": TURNSTILE_SITEKEY in html_src,
            "form_action_present": expected_action in html_src,
            "ga4_present": GA4_ID in html_src,
        }

    audit_payload = {
        "generated_at": now_utc().isoformat(),
        "date_sgt": "2026-12-12",
        "verified_leads_total": len(leads_arr),
        "verified_leads_since_nov15": _since_nov15(leads_arr),
        "spam_blocked_total": len(spam_arr),
        "spam_blocked_since_nov15": _since_nov15(spam_arr),
        "form_security_checks": form_checks,
        "pii_stored": False,
    }
    rpath = save_json_report("lead-integrity-audit.json", audit_payload)
    log_fn(
        f"2026-12-12: lead integrity audit (leads={len(leads_arr)}, spam_blocked={len(spam_arr)}, zero PII)"
    )
    return True, f"Lead & Turnstile audit complete (leads={len(leads_arr)}, spam_blocked={len(spam_arr)}).", {
        "report_path": str(rpath),
        "verified_leads_total": len(leads_arr),
        "spam_blocked_total": len(spam_arr),
    }


def action_2026_12_13_full_sitemap_indexnow(remote_get, remote_put, log_fn, indexnow_fn=None):
    """2026-12-13: Full sitemap IndexNow push and reconciliation verification."""
    smap_xml = fetch_remote_or_live(remote_get, "sitemap.xml", "https://framez.sg/sitemap.xml") or ""
    urls = parse_sitemap_locs(smap_xml)
    if not urls:
        latest_audit = load_json_safe(REPORT_DIR / "latest-audit.json", {})
        urls = [p.get("url") for p in latest_audit.get("pages", []) if p.get("url")]

    idx_res = ping_indexnow(urls, log_fn, indexnow_fn=indexnow_fn)
    rpath = save_json_report("indexnow-reconciliation-2026-12-13.json", {
        "generated_at": now_utc().isoformat(),
        "date_sgt": "2026-12-13",
        "sitemap_urls_count": len(urls),
        "indexnow": idx_res,
    })
    return True, f"Pushed {len(urls)} canonical sitemap URLs to IndexNow.", {
        "target_urls": urls,
        "indexnow": idx_res,
        "report_path": str(rpath),
    }


def action_2026_12_14_cycle_freeze_check(remote_get, remote_put, log_fn, indexnow_fn=None):
    """2026-12-14: Verify cycle-boundary telemetry snapshot freeze and ledger completeness."""
    snap_dir = REPORT_DIR / "monthly-snapshots"
    snap_dir.mkdir(parents=True, exist_ok=True)
    freeze_file = snap_dir / "boundary-2026-12-14.json"

    gsc = load_json_safe(REPORT_DIR / "latest-gsc.json", {})
    ga4 = load_json_safe(REPORT_DIR / "latest-ga4.json", {})
    audit = load_json_safe(REPORT_DIR / "latest-audit.json", {})
    leads = load_json_safe(REPORT_DIR / "latest-leads.json", {})

    if not freeze_file.exists():
        freeze_file.write_text(json.dumps({
            "captured_at": now_utc().isoformat(),
            "sgt_date": "2026-12-14",
            "active_cycle": ["2026-11-15", "2026-12-15"],
            "gsc": gsc,
            "ga4": ga4,
            "audit_summary": {"audited": audit.get("audited"), "pages_with_issues": audit.get("pages_with_issues")},
            "leads": leads,
        }, indent=2, ensure_ascii=False), encoding="utf-8")

    verification = {
        "generated_at": now_utc().isoformat(),
        "date_sgt": "2026-12-14",
        "boundary_snapshot_exists": freeze_file.exists(),
        "has_gsc": bool(gsc),
        "has_ga4": bool(ga4),
        "has_audit": bool(audit),
        "has_leads": bool(leads),
        "ledger_exists": LEDGER_PATH.exists(),
    }
    rpath = save_json_report("cycle-freeze-verification.json", verification)
    log_fn(f"2026-12-14: cycle freeze verification complete (snapshot={freeze_file.name})")
    return True, "Cycle 4 data freeze and telemetry snapshot verified.", {
        "report_path": str(rpath),
        "boundary_snapshot": str(freeze_file),
    }


def action_2026_12_15_final_report_verify(remote_get, remote_put, log_fn, indexnow_fn=None):
    """2026-12-15: Verify final monthly report compliance (zero dashes, zero banned buzzwords, zero client revenue, zero PII)."""
    candidates = [
        JOB_DIR.parent.parent / "DocMaker" / "FRAMEZ_NOVEMBER_DECEMBER_2026_SEO_AEO_GEO_REPORT.md",
        REPORT_DIR / "FRAMEZ_NOVEMBER_DECEMBER_2026_SEO_AEO_GEO_REPORT.md",
        JOB_DIR / "FRAMEZ_NOVEMBER_DECEMBER_2026_SEO_AEO_GEO_REPORT.md",
    ]
    report_path = next((p for p in candidates if p.exists()), None)
    banned = ("leverage", "utilize", "facilitate", "streamline", "robust", "seamless", "delve", "navigate", "unlock", "harness", "foster", "cultivate", "landscape", "ecosystem", "journey", "game-changer", "deep dive")

    report_text = report_path.read_text(encoding="utf-8", errors="ignore") if report_path else ""
    em_en_count = report_text.count("\u2014") + report_text.count("\u2013")
    banned_found = [w for w in banned if report_text and re.search(rf"\b{re.escape(w)}\b", report_text, re.I)]
    revenue_hits = len(
        re.findall(
            r"(?:client\s+revenue|ticket\s+sales|booking\s+revenue)\s*[:=]?\s*(?:INR|USD|SGD|\$|₹|\d)|(?:₹|INR|USD|SGD)\s*\d+(?:,\d+)*(?:\.\d+)?\s*(?:crore|lakhs?|million|M|K)\b",
            report_text,
            re.I,
        )
    ) if report_text else 0

    payload = {
        "generated_at": now_utc().isoformat(),
        "date_sgt": "2026-12-15",
        "report_found": report_path is not None,
        "report_path": str(report_path) if report_path else None,
        "report_bytes": len(report_text),
        "em_en_dashes_count": em_en_count,
        "banned_buzzwords_found": banned_found,
        "revenue_figure_hits": revenue_hits,
        "compliant": (em_en_count == 0 and not banned_found and revenue_hits == 0),
    }
    rpath = save_json_report("final-cycle-report-verification.json", payload)
    log_fn(f"2026-12-15: final report verification complete (found={payload['report_found']}, compliant={payload['compliant']})")
    return True, f"Final cycle report verification complete (report_found={payload['report_found']}, compliant={payload['compliant']}).", {
        "report_path": str(rpath),
        "verified_report_file": payload["report_path"],
    }


HANDLERS = {
    "2026-11-20": action_2026_11_20_clientele,
    "2026-11-22": action_2026_11_22_mice_crosslinks,
    "2026-11-23": action_2026_11_23_bangalore_ctr_faq,
    "2026-11-24": action_2026_11_24_mice_preflight_venues,
    "2026-11-26": action_2026_11_26_exhibition_crosslinks,
    "2026-11-27": action_2026_11_27_book_demo_estimator,
    "2026-11-28": action_2026_11_28_seasonal_townhall_sko,
    "2026-11-30": action_2026_11_30_mid_cycle_ctr_audit,
    "2026-12-01": action_2026_12_01_llms_parity_sync,
    "2026-12-02": action_2026_12_02_bangalore_tech_corridors,
    "2026-12-04": action_2026_12_04_offsite_crosslinks,
    "2026-12-05": action_2026_12_05_green_mice_prep,
    "2026-12-06": action_2026_12_06_sustainable_rfp_llms_prep,
    "2026-12-08": action_2026_12_08_esg_crosslinks,
    "2026-12-09": action_2026_12_09_cwv_asset_audit,
    "2026-12-10": action_2026_12_10_redirect_canonical_audit,
    "2026-12-11": action_2026_12_11_ranking_velocity_rollup,
    "2026-12-12": action_2026_12_12_lead_turnstile_audit,
    "2026-12-13": action_2026_12_13_full_sitemap_indexnow,
    "2026-12-14": action_2026_12_14_cycle_freeze_check,
    "2026-12-15": action_2026_12_15_final_report_verify,
}


def execute_daily_action_for_date(target_date, remote_get, remote_put, log_fn, indexnow_fn=None):
    """Execute the scheduled action for the given SGT date via HANDLERS dispatch."""
    if target_date not in DAILY_SCHEDULE:
        log_fn(f"daily_actions: no specific scheduled action for {target_date}, running standard audit & deepseek.")
        return {"status": "skipped", "reason": "no_action_for_date", "date": target_date}

    meta = DAILY_SCHEDULE[target_date]
    if meta.get("executed_prior"):
        log_fn(f"daily_actions: action for {target_date} ({meta['action_id']}) was already executed historically.")
        return {"status": "prior_completed", "action": meta, "date": target_date}

    if meta.get("is_wave"):
        log_fn(f"daily_actions: {target_date} is wave release day ({meta.get('wave_id')}), handled by wave engine.")
        return {"status": "wave_release_day", "action": meta, "date": target_date}

    handler_fn = HANDLERS.get(target_date)
    if handler_fn is None and meta.get("handler"):
        handler_fn = globals().get(meta["handler"])

    if handler_fn is None:
        log_fn(f"daily_actions: handler not registered for {target_date}")
        return {"status": "pending_handler", "action": meta, "date": target_date}

    try:
        res = handler_fn(remote_get, remote_put, log_fn, indexnow_fn=indexnow_fn)
    except Exception as exc:
        log_fn(f"daily_actions: error executing {target_date} ({meta['action_id']}): {exc}")
        res = (False, str(exc), {})

    if len(res) == 2:
        ok, msg = res
        extra = {}
    else:
        ok, msg, extra = res

    status_str = "ok" if ok else "error"
    result_record = {
        "event": "daily_micro_action_executed",
        "date_sgt": target_date,
        "action_id": meta["action_id"],
        "title": meta["title"],
        "kind": meta["kind"],
        "target_file": meta.get("target_file"),
        "target_url": meta.get("target_url"),
        "status": status_str,
        "message": msg,
        "timestamp": now_utc().isoformat(),
    }
    if extra:
        result_record.update(extra)

    append_jsonl(DAILY_ACTION_LOG, result_record)
    append_jsonl(LEDGER_PATH, result_record)
    return result_record
