#!/usr/bin/env python3
"""Framez.sg Automated SEO · GEO · AEO & Cycle Execution Engine.

Runs daily via /etc/cron.d/framez-seo on 72.61.173.127:
  1. Executes any due staggered Nov-Dec cycle wave (Nov 21, Nov 25, Nov 29, Dec 03, Dec 07)
     with pre-write backups, SHA-256 readback, live HTTP 200 verification & IndexNow push.
  2. Crawls every sitemap URL and validates status, canonicals, meta robots, titles,
     descriptions, H1, JSON-LD, GA4 (G-XDPHV6MX44), image alts, duplicates & orphans.
  3. Reconciles sitemap.xml against deployed cPanel files with real mtime <lastmod>.
  4. Pushes only changed/new canonical URLs to IndexNow.
  5. Pulls live Google Search Console (sc-domain:framez.sg) 7d/28d queries, pages & countries.
  6. Pulls live Google Analytics 4 (Property 547082278) 7d/28d sessions, channels & conversions.
  7. Records privacy-safe aggregate lead & blocked-bot counts from cPanel logs (zero PII).
  8. Appends every run & wave receipt to reports/cycle-2026-11-15-to-2026-12-15-ledger.jsonl.

Usage:
  python3 framez_seo_cron.py all          # full daily pipeline (cron default)
  python3 framez_seo_cron.py audit        # technical crawl only
  python3 framez_seo_cron.py geo_audit    # GEO/AEO, schema, llms parity & asset audit
  python3 framez_seo_cron.py sync_llms    # sync llms.txt & llms-full.txt to live sitemap
  python3 framez_seo_cron.py sitemap      # reconcile & upload sitemap.xml
  python3 framez_seo_cron.py indexnow     # push changed URLs
  python3 framez_seo_cron.py gsc          # Search Console snapshot
  python3 framez_seo_cron.py ga4          # GA4 snapshot
  python3 framez_seo_cron.py leads        # privacy-safe lead/bot count snapshot
  python3 framez_seo_cron.py release_due  # deploy any scheduled wave due <= today
  python3 framez_seo_cron.py status       # print last run state
"""

import datetime
import fcntl
import hashlib
import html as html_lib
import json
import os
import pathlib
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.sax.saxutils as saxutils

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
JOB = SCRIPT_DIR.parent if SCRIPT_DIR.name == "scripts" else SCRIPT_DIR
BASE = JOB.parent.parent if (JOB.parent and JOB.parent.name == "seo-jobs") else pathlib.Path("/root/websites/seogeoopt")

for p in (JOB / "scripts", JOB):
    p_str = str(p)
    if p.exists() and p_str not in sys.path:
        sys.path.insert(0, p_str)

from content_pages import GA4_ID, STAGED_WAVES, render_page
CONFIG_PATH = JOB / "config.json"
STATE_PATH = JOB / "state.json"
LOG_DIR = JOB / "logs"
REPORT_DIR = JOB / "reports"
BACKUP_DIR = JOB / "backups"
SNAPSHOT_DIR = REPORT_DIR / "monthly-snapshots"
LOCK_PATH = JOB / ".run.lock"

for d in (LOG_DIR, REPORT_DIR, BACKUP_DIR, SNAPSHOT_DIR):
    d.mkdir(parents=True, exist_ok=True)

DEFAULT_CONFIG = {
    "site": "https://framez.sg",
    "host": "framez.sg",
    "sitemap_url": "https://framez.sg/sitemap.xml",
    "sitemap_remote_file": "sitemap.xml",
    "sitemap_remote_dir": "public_html",
    "indexnow_key": "59951843f48f4e09a34b4f61a08fd59c",
    "indexnow_key_location": "https://framez.sg/59951843f48f4e09a34b4f61a08fd59c.txt",
    "indexnow_endpoint": "https://api.indexnow.org/IndexNow",
    "gsc_site": "sc-domain:framez.sg",
    "ga4_property_id": "547082278",
    "exclude_slugs": [
        "404-not-found", "thank-you", "contact-submit", "submit-demo",
        "database", "img_helper", "auto_indexnow", "footer", "header",
        "index-backup-2026", "emailtemplate", "index_broken_backup",
        "get-to-know-us", "our-team", "social-event",
        "virtual-event", "virtual-event-and-hybrid-event-platform",
        "virtual-event-management-companies-in-india",
        "best-virtual-event-platform-in-india",
        "hybrid-event-management-company", "hybrid-event-platform",
        "index",
    ],
    "legacy_slugs": [],
    "min_word_count": 300,
    "title_max": 60,
    "description_max": 160,
}

UA = "Mozilla/5.0 (compatible; Adelev8SEOBot/2.0; +https://portal.adelev8.com)"


def now_utc():
    return datetime.datetime.now(datetime.timezone.utc)


def today_sgt_date():
    sgt = datetime.timezone(datetime.timedelta(hours=8))
    return datetime.datetime.now(sgt).date()


def today_sgt():
    return today_sgt_date().strftime("%Y-%m-%d")


def active_cycle_window(d=None):
    """Compute the active 15th-to-15th monthly billing cycle for any date."""
    d = d or today_sgt_date()
    if d.day >= 15:
        start = datetime.date(d.year, d.month, 15)
        if d.month == 12:
            end = datetime.date(d.year + 1, 1, 15)
        else:
            end = datetime.date(d.year, d.month + 1, 15)
    else:
        end = datetime.date(d.year, d.month, 15)
        if d.month == 1:
            start = datetime.date(d.year - 1, 12, 15)
        else:
            start = datetime.date(d.year, d.month - 1, 15)
    return start.isoformat(), end.isoformat()


def ledger_path_for_today():
    s, e = active_cycle_window()
    return REPORT_DIR / f"cycle-{s}-to-{e}-ledger.jsonl"


def log(msg):
    line = "%s %s" % (now_utc().strftime("%Y-%m-%dT%H:%M:%SZ"), msg)
    print(line, flush=True)
    with open(LOG_DIR / "seo.log", "a") as fh:
        fh.write(line + "\n")


def append_ledger(entry):
    s, e = active_cycle_window()
    rec = {"timestamp": now_utc().isoformat(), "cycle": f"{s}_to_{e}", **entry}
    with open(ledger_path_for_today(), "a") as fh:
        fh.write(json.dumps(rec) + "\n")


def load_json(path, default):
    try:
        return json.loads(pathlib.Path(path).read_text())
    except Exception:
        return default


def save_json(path, data):
    pathlib.Path(path).write_text(json.dumps(data, indent=2, sort_keys=False))


def config():
    cfg = dict(DEFAULT_CONFIG)
    cfg.update(load_json(CONFIG_PATH, {}))
    # Force canonical verified domain property
    if cfg.get("gsc_site") == "https://framez.sg/":
        cfg["gsc_site"] = "sc-domain:framez.sg"
    return cfg


def env_file():
    values = {}
    try:
        for line in (BASE / ".env").read_text().splitlines():
            m = re.match(r"^([A-Z0-9_]+)=(.*)$", line.strip())
            if m:
                values[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    return values


def http(url, data=None, headers=None, method=None, timeout=30, retries=2):
    hdrs = {"User-Agent": UA, "Accept": "*/*"}
    if headers:
        hdrs.update(headers)
    last_err = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status, resp.read().decode("utf-8", "ignore"), dict(resp.headers)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "ignore") if e.fp else ""
            return e.code, body, dict(e.headers or {})
        except Exception as e:
            last_err = e
            time.sleep(1 + attempt)
    raise RuntimeError("request failed for %s: %s" % (url, last_err))


def fetch(url):
    return http(url, timeout=30)


def cpanel_call(module, function, params=None, method="GET"):
    creds = env_file()
    host = creds.get("CPANEL_HOST", "https://framez.sg:2083").rstrip("/")
    auth = "cpanel %s:%s" % (creds.get("CPANEL_USERNAME", ""), creds.get("CPANEL_API_TOKEN", ""))
    url = "%s/execute/%s/%s" % (host, module, function)
    headers = {"Authorization": auth}
    if method == "GET":
        if params:
            url += "?" + urllib.parse.urlencode(params)
        status, body, _ = http(url, headers=headers, timeout=60)
    else:
        headers["Content-Type"] = "application/json"
        status, body, _ = http(url, data=json.dumps(params or {}).encode(), headers=headers, method="POST", timeout=90)
    try:
        return json.loads(body)
    except Exception:
        return {"status": 0, "raw": body[:500], "http": status}


def remote_list(dir_path):
    res = cpanel_call("Fileman", "list_files", {"dir": dir_path, "types": "file", "includeHidden": "0"})
    return res.get("data") or []


def remote_get(dir_path, filename):
    res = cpanel_call("Fileman", "get_file_content", {"dir": dir_path, "file": filename})
    return (res.get("data") or {}).get("content")


def remote_put(dir_path, filename, content):
    res = cpanel_call("Fileman", "save_file_content", {"dir": dir_path, "file": filename, "content": content}, method="POST")
    return res.get("status") == 1


def parse_sitemap(xml_text):
    out = []
    for m in re.finditer(r"<url>(.*?)</url>", xml_text, re.S | re.I):
        block = m.group(1)
        loc = re.search(r"<loc>\s*([^<\s]+)\s*</loc>", block)
        if not loc:
            continue
        lastmod = re.search(r"<lastmod>\s*(\d{4}-\d{2}-\d{2})", block)
        out.append({"loc": loc.group(1), "lastmod": lastmod.group(1) if lastmod else None})
    return out


def slug_to_url(cfg, slug):
    if slug in ("", "index", "index.html"):
        return cfg["site"].rstrip("/") + "/"
    return cfg["site"].rstrip("/") + "/" + slug


def url_to_slug(cfg, url):
    base = cfg["site"].rstrip("/")
    if url.rstrip("/") == base:
        return ""
    return url[len(base):].strip("/")


def _strip_dashes(text):
    """Replace em and en dashes with standard punctuation."""
    if not text:
        return ""
    cleaned = re.sub(r"\s*\u2014\s*", ": ", str(text))
    return cleaned.replace("\u2013", "-")


def _normalize_site_url(cfg, raw_url):
    base = cfg["site"].rstrip("/")
    u = str(raw_url or "").strip()
    if not u:
        return ""
    if u.rstrip("/") == base:
        return base + "/"
    return u.rstrip("/")


def _extract_jsonld_info(html):
    """Extract schema @type values, invalid JSON-LD block count, and Speakable presence."""
    ld_types, ld_invalid = [], 0
    has_speakable = False
    for block in re.findall(r'application/ld\+json[^>]*>(.*?)</script>', html, re.S | re.I):
        try:
            parsed = json.loads(block.strip())
            items = parsed if isinstance(parsed, list) else parsed.get("@graph", [parsed])
            for item in items:
                if isinstance(item, dict):
                    t = item.get("@type")
                    if isinstance(t, list):
                        ld_types.extend(str(x) for x in t)
                    elif t:
                        ld_types.append(str(t))
                    if item.get("speakable") or (
                        isinstance(t, str) and t == "SpeakableSpecification"
                    ) or (isinstance(t, list) and "SpeakableSpecification" in t):
                        has_speakable = True
                else:
                    ld_invalid += 1
        except Exception:
            ld_invalid += 1
    return ld_types, ld_invalid, has_speakable


def analyze_page(url, html):
    def one(pattern):
        m = re.search(pattern, html, re.S | re.I)
        return m.group(1).strip() if m else ""

    title = html_lib.unescape(one(r"<title[^>]*>(.*?)</title>"))
    desc = ""
    m = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content="([^"]*)"', html, re.I | re.S)
    if not m:
        m = re.search(r"<meta[^>]+name=[\"']description[\"'][^>]+content='([^']*)'", html, re.I | re.S)
    if m:
        desc = html_lib.unescape(m.group(1).strip())
    canonical = one(r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']*)')
    robots = one(r'<meta[^>]+name=["\']robots["\'][^>]+content=["\']([^"\']*)')
    h1_count = len(re.findall(r"<h1[\s>]", html, re.I))
    viewport = bool(re.search(r'name=["\']viewport["\']', html, re.I))
    og_title = bool(re.search(r'property=["\']og:title["\']', html, re.I))
    twitter = bool(re.search(r'name=["\']twitter:card["\']', html, re.I))
    has_ga4 = GA4_ID in html

    ld_types, ld_invalid, _ = _extract_jsonld_info(html)

    body = re.search(r"<body.*?</body>", html, re.S | re.I)
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", body.group(0) if body else html, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    words = len(text.split())

    imgs = re.findall(r"<img\b[^>]*>", html, re.I)
    missing_alt = [i for i in imgs if not re.search(r"""alt\s*=\s*["'][^"']+["']""", i, re.I)]
    dup_alt = [i for i in imgs if len(re.findall(r"\balt\s*=", i, re.I)) > 1]
    links = len(re.findall(r"<a\s[^>]*href=", html, re.I))

    return {
        "title": title,
        "title_len": len(title),
        "description": desc,
        "description_len": len(desc),
        "canonical": canonical,
        "robots": robots,
        "h1_count": h1_count,
        "viewport": viewport,
        "og_title": og_title,
        "twitter_card": twitter,
        "has_ga4": has_ga4,
        "jsonld_types": ld_types,
        "jsonld_invalid": ld_invalid,
        "word_count": words,
        "images": len(imgs),
        "images_missing_alt": len(missing_alt),
        "images_duplicate_alt": len(dup_alt),
        "internal_links": links,
        "noindex": "noindex" in robots.lower(),
    }


def page_issues(url, info, cfg):
    issues = []
    if not info["title"]:
        issues.append("missing_title")
    elif info["title_len"] > cfg["title_max"]:
        issues.append("title_too_long:%d" % info["title_len"])
    if not info["description"]:
        issues.append("missing_meta_description")
    elif info["description_len"] > cfg["description_max"]:
        issues.append("description_too_long:%d" % info["description_len"])
    if not info["canonical"]:
        issues.append("missing_canonical")
    elif info["canonical"].rstrip("/") != url.rstrip("/"):
        issues.append("canonical_mismatch:%s" % info["canonical"])
    if info["robots"] == "":
        issues.append("missing_meta_robots")
    if info["noindex"]:
        issues.append("noindex")
    if info["h1_count"] != 1:
        issues.append("h1_count:%d" % info["h1_count"])
    if not info["viewport"]:
        issues.append("missing_viewport")
    if not info["og_title"]:
        issues.append("missing_og_title")
    if not info["twitter_card"]:
        issues.append("missing_twitter_card")
    if not info["has_ga4"]:
        issues.append("missing_ga4")
    if info["jsonld_invalid"]:
        issues.append("invalid_jsonld:%d" % info["jsonld_invalid"])
    if "Product" in info["jsonld_types"]:
        issues.append("unexpected_product_schema")
    if info["images_missing_alt"]:
        issues.append("images_missing_alt:%d" % info["images_missing_alt"])
    if info["images_duplicate_alt"]:
        issues.append("images_duplicate_alt:%d" % info["images_duplicate_alt"])
    if info["word_count"] < cfg["min_word_count"]:
        issues.append("thin_content:%d" % info["word_count"])
    return issues


def discover_deployed(cfg):
    files = remote_list(cfg["sitemap_remote_dir"])
    if not files:
        return {}
    out = {}
    for item in files:
        name = item.get("file", "")
        mtime = item.get("mtime")
        if name == "index.html":
            out[""] = int(mtime) if mtime else None
        elif name.endswith(".php"):
            out[name[:-4]] = int(mtime) if mtime else None
    return out


def release_due_waves(cfg, state):
    """Automatically deploy any pre-validated cycle wave whose deploy_date <= today (SGT)."""
    today = today_sgt()
    deployed_waves = state.setdefault("deployed_waves", {})
    newly_deployed = []

    for wave in STAGED_WAVES:
        wid = wave["wave_id"]
        if wid in deployed_waves:
            continue
        if wave["deploy_date"] > today:
            continue

        spec = wave["spec"]
        slug = spec["slug"]
        fname = f"{slug}.php"
        log(f"release_due: deploying {wid} ({fname}, scheduled {wave['deploy_date']})")

        # 1. Render and validate new page
        page_html = render_page(spec)
        wbackup = BACKUP_DIR / f"{wid}-{now_utc().strftime('%Y%m%dT%H%M%SZ')}"
        wbackup.mkdir(parents=True, exist_ok=True)

        # 2. Backup & update blog.php, llms.txt, llms-full.txt, and our-events-and-services.php (if service)
        touched_files = {fname: page_html}
        blog_cur = remote_get("public_html", "blog.php") or ""
        if blog_cur:
            (wbackup / "blog.php").write_text(blog_cur)
            if f"/{slug}" not in blog_cur:
                card = wave["blog_card"]
                card_html = f"""
			<div class="col-lg-6 col-md-12 col-sm-12">
			    <img loading="lazy" decoding="async" src="{card['img']}" class="image-fluid" alt="{html_lib.escape(card['alt'])}" title="{html_lib.escape(card['alt'])}" style="border-radius:10px;" />
				<div class="card card-color-gray">
					<div class="card-body">
               	<a href="https://framez.sg/{slug}">
                   <h4 style="color: #392682;">{html_lib.escape(card['heading'])}</h4><br>
                   <p>{html_lib.escape(card['blurb'])}</p><br>
               </a>
               </div>
           </div>
            </div>
"""
                marker = '<div class="row justify-content-start align-items-center">'
                idx = blog_cur.rfind(marker)
                if idx != -1:
                    ins = idx + len(marker)
                    touched_files["blog.php"] = blog_cur[:ins] + "\n" + card_html + blog_cur[ins:]

        # 3. Upload and SHA-256 verify page & blog.php
        receipts = []
        for tf, tcontent in touched_files.items():
            ok = remote_put("public_html", tf, tcontent)
            if not ok:
                raise RuntimeError(f"release_due: cPanel upload failed for {tf}")
            rb = remote_get("public_html", tf) or ""
            sha = hashlib.sha256(tcontent.encode("utf-8")).hexdigest()
            if hashlib.sha256(rb.encode("utf-8")).hexdigest() != sha:
                raise RuntimeError(f"release_due: SHA-256 mismatch on {tf}")
            receipts.append({"file": tf, "bytes": len(tcontent), "sha256": sha})

        # 4. Verify live HTTP 200 & self-canonical
        time.sleep(2)
        live_url = f"https://framez.sg/{slug}"
        st, live_body, _ = fetch(live_url)
        info = analyze_page(live_url, live_body)
        if st != 200 or info["canonical"].rstrip("/") != live_url:
            raise RuntimeError(f"release_due: live verification failed for {live_url} (HTTP {st})")

        # 5. Sync llms.txt & llms-full.txt cleanly with the newly deployed wave URL
        try:
            llms_res = sync_llms_files(
                cfg,
                state,
                upload=True,
                extra_pages=[{
                    "loc": live_url,
                    "title": spec.get("h1") or spec.get("title") or slug,
                    "desc": spec.get("description") or "",
                    "kind": spec.get("kind", "guide"),
                }],
            )
            for fname_l, sha_l in (llms_res.get("sha256") or {}).items():
                if fname_l in (llms_res.get("updated_files") or []):
                    receipts.append({"file": fname_l, "sha256": sha_l})
        except Exception as e:
            log(f"release_due: llms sync warning ({e})")

        wave_record = {
            "deployed_at": now_utc().isoformat(),
            "scheduled_date": wave["deploy_date"],
            "url": live_url,
            "http_status": st,
            "word_count": info["word_count"],
            "receipts": receipts,
        }
        deployed_waves[wid] = wave_record
        newly_deployed.append(wave_record)
        append_ledger({"event": "staged_wave_deployed", "wave_id": wid, **wave_record})
        log(f"release_due: {wid} LIVE at {live_url} ({info['word_count']} words, HTTP {st})")

    return newly_deployed


def audit(cfg, state):
    log("audit: start")
    status, xml_text, _ = fetch(cfg["sitemap_url"])
    if status != 200:
        raise RuntimeError("sitemap fetch failed: HTTP %s" % status)
    entries = parse_sitemap(xml_text)
    log("audit: %d sitemap URLs" % len(entries))

    results, changed, broken = [], [], []
    titles, descriptions = {}, {}
    for entry in entries:
        url = entry["loc"]
        try:
            st, html, _ = fetch(url)
        except Exception as e:
            log("audit: %s unreachable: %s" % (url, e))
            broken.append({"url": url, "error": str(e)})
            continue
        digest = hashlib.sha256(html.encode("utf-8", "ignore")).hexdigest()
        info = analyze_page(url, html)
        issues = page_issues(url, info, cfg)
        if st != 200:
            issues.insert(0, "http_%d" % st)
            broken.append({"url": url, "status": st})
        if not entry.get("lastmod"):
            issues.append("missing_lastmod")
        titles.setdefault(info["title"], []).append(url)
        descriptions.setdefault(info["description"], []).append(url)
        if state.get("hashes", {}).get(url) != digest:
            changed.append(url)
        results.append({
            "url": url,
            "status": st,
            "sha256": digest,
            "content_length": len(html),
            "sitemap_lastmod": entry.get("lastmod"),
            "issues": issues,
            **{k: info[k] for k in ("title", "title_len", "description_len", "canonical",
                                    "robots", "h1_count", "has_ga4", "word_count", "images",
                                    "images_missing_alt", "images_duplicate_alt",
                                    "internal_links", "jsonld_types")},
        })

    duplicates = {
        "titles": {t: urls for t, urls in titles.items() if t and len(urls) > 1},
        "descriptions": {d: urls for d, urls in descriptions.items() if d and len(urls) > 1},
    }

    report = {
        "generated_at": now_utc().isoformat(),
        "site": cfg["site"],
        "sitemap_urls": len(entries),
        "audited": len(results),
        "broken": broken,
        "pages_with_issues": sum(1 for r in results if r["issues"]),
        "issue_counts": {},
        "duplicates": duplicates,
        "changed_urls": changed,
        "pages": results,
    }
    for r in results:
        for issue in r["issues"]:
            key = issue.split(":")[0]
            report["issue_counts"][key] = report["issue_counts"].get(key, 0) + 1

    stamp = now_utc().strftime("%Y-%m-%d")
    save_json(REPORT_DIR / ("audit-%s.json" % stamp), report)
    save_json(REPORT_DIR / "latest-audit.json", report)

    for r in results:
        state.setdefault("hashes", {})[r["url"]] = r["sha256"]
    state["last_audit_at"] = report["generated_at"]
    state["last_audit_summary"] = {
        "urls": report["audited"],
        "issues": report["pages_with_issues"],
        "broken": len(broken),
        "changed": len(changed),
        "issue_counts": report["issue_counts"],
    }
    log("audit: done, %d issues across %d pages, %d changed, %d broken"
        % (report["pages_with_issues"], report["audited"], len(changed), len(broken)))
    return report


def sitemap_sync(cfg, state):
    log("sitemap: start")
    status, xml_text, _ = fetch(cfg["sitemap_url"])
    if status != 200:
        raise RuntimeError("cannot read live sitemap: HTTP %s" % status)
    current = parse_sitemap(xml_text)
    current_order = [url_to_slug(cfg, e["loc"]) for e in current]
    current_lastmod = {url_to_slug(cfg, e["loc"]): e.get("lastmod") for e in current}

    deployed = discover_deployed(cfg)
    candidates = list(dict.fromkeys(current_order + sorted(deployed)))
    excluded = set(cfg["exclude_slugs"])

    kept, dropped = [], []
    for slug in candidates:
        if slug in excluded:
            dropped.append(slug)
            continue
        url = slug_to_url(cfg, slug)
        try:
            st, html, _ = fetch(url)
        except Exception as e:
            log("sitemap: skip %s (%s)" % (slug, e))
            dropped.append(slug)
            continue
        if st != 200:
            dropped.append(slug)
            continue
        info = analyze_page(url, html)
        if info["noindex"] or info["canonical"].rstrip("/") != url.rstrip("/"):
            dropped.append(slug)
            continue
        mtime = deployed.get(slug)
        if mtime:
            lastmod = datetime.datetime.fromtimestamp(mtime, datetime.timezone.utc).strftime("%Y-%m-%d")
        else:
            lastmod = current_lastmod.get(slug) or now_utc().strftime("%Y-%m-%d")
        kept.append({"loc": url, "lastmod": lastmod})

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for e in kept:
        lines.append("  <url><loc>%s</loc><lastmod>%s</lastmod></url>" % (saxutils.escape(e["loc"]), e["lastmod"]))
    lines.append("</urlset>\n")
    new_xml = "\n".join(lines)

    added = [e["loc"] for e in kept if url_to_slug(cfg, e["loc"]) not in current_order]
    removed = [e["loc"] for e in current if url_to_slug(cfg, e["loc"]) not in {url_to_slug(cfg, e["loc"]) for e in kept}]
    uploaded = False
    if new_xml.strip() != xml_text.strip():
        stamp = now_utc().strftime("%Y%m%dT%H%M%SZ")
        (BACKUP_DIR / ("sitemap-%s.xml" % stamp)).write_text(xml_text)
        (JOB / "sitemap.generated.xml").write_text(new_xml)
        uploaded = remote_put(cfg["sitemap_remote_dir"], cfg["sitemap_remote_file"], new_xml)
        log("sitemap: uploaded=%s urls=%d added=%d removed=%d" % (uploaded, len(kept), len(added), len(removed)))
    else:
        log("sitemap: already up to date (%d URLs)" % len(kept))

    state["last_sitemap_at"] = now_utc().isoformat()
    state["last_sitemap_summary"] = {
        "urls": len(kept),
        "added": added,
        "removed": removed,
        "uploaded": uploaded,
    }
    return state["last_sitemap_summary"]


def indexnow(cfg, state, urls):
    urls = sorted(set(urls))
    if not urls:
        log("indexnow: nothing changed, skipped")
        return {"submitted": 0, "status": None}
    payload = json.dumps({
        "host": cfg["host"],
        "key": cfg["indexnow_key"],
        "keyLocation": cfg["indexnow_key_location"],
        "urlList": urls,
    }).encode()
    status, body, _ = http(cfg["indexnow_endpoint"], data=payload,
                           headers={"Content-Type": "application/json"}, method="POST", timeout=45)
    ok = status in (200, 202)
    state["last_indexnow_at"] = now_utc().isoformat()
    state["last_indexnow"] = {"submitted": len(urls), "status": status, "ok": ok, "urls": urls}
    log("indexnow: %d URLs, HTTP %s" % (len(urls), status))
    return {"submitted": len(urls), "status": status, "ok": ok}


def google_token():
    portal = load_json(BASE / "server" / "data" / "portal.json", {})
    brand = next((b for b in portal.get("brands", []) if "framez" in (b.get("name", "") + b.get("website", "")).lower()), None)
    if not brand:
        return None, "no_brand"
    integ = brand.get("integrations") or {}
    oauth = ((integ.get("searchConsole") or {}).get("oauth")
             or (integ.get("ga4") or {}).get("oauth") or {})
    refresh = oauth.get("refreshToken")
    if not refresh:
        return None, "no_refresh_token"
    creds = env_file()
    body = urllib.parse.urlencode({
        "client_id": creds.get("GOOGLE_CLIENT_ID", ""),
        "client_secret": creds.get("GOOGLE_CLIENT_SECRET", ""),
        "refresh_token": refresh,
        "grant_type": "refresh_token",
    }).encode()
    status, text, _ = http("https://oauth2.googleapis.com/token", data=body,
                           headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST", timeout=25)
    if status != 200:
        return None, "invalid_grant"
    return json.loads(text).get("access_token"), "ok"


def gsc_query(site_enc, headers, start_date, end_date, dimensions=None, row_limit=25, dimensionFilterGroups=None):
    payload = {"startDate": start_date, "endDate": end_date, "rowLimit": row_limit}
    if dimensions:
        payload["dimensions"] = dimensions
    if dimensionFilterGroups:
        payload["dimensionFilterGroups"] = dimensionFilterGroups
    st, text, _ = http(
        f"https://www.googleapis.com/webmasters/v3/sites/{site_enc}/searchAnalytics/query",
        data=json.dumps(payload).encode(),
        headers={**headers, "Content-Type": "application/json"},
        method="POST",
        timeout=30,
    )
    if st != 200:
        return {"error": st, "body": text[:200]}
    return json.loads(text)


def gsc_snapshot(cfg, state):
    token, reason = google_token()
    if not token:
        state["gsc_status"] = "reauth_required" if reason == "invalid_grant" else reason
        log("gsc: skipped (%s)" % state["gsc_status"])
        return {"status": state["gsc_status"]}
    headers = {"Authorization": "Bearer " + token}
    site_enc = urllib.parse.quote(cfg["gsc_site"], safe="")
    out = {"status": "ok", "generated_at": now_utc().isoformat(), "property": cfg["gsc_site"]}

    st, text, _ = http(f"https://www.googleapis.com/webmasters/v3/sites/{site_enc}/sitemaps", headers=headers, timeout=25)
    if st == 200:
        out["sitemaps"] = [
            {"path": m.get("path"), "lastSubmitted": m.get("lastSubmitted"),
             "lastDownloaded": m.get("lastDownloaded"), "errors": m.get("errors"), "warnings": m.get("warnings")}
            for m in json.loads(text).get("sitemap", [])
        ]

    # GSC data usually lags 2 days
    end_d = now_utc().date() - datetime.timedelta(days=2)
    start_7d = (end_d - datetime.timedelta(days=6)).isoformat()
    start_28d = (end_d - datetime.timedelta(days=27)).isoformat()
    end_iso = end_d.isoformat()

    def _country_filter(code):
        return [{"filters": [{"dimension": "country", "operator": "equals", "expression": code}]}]

    out["window_7d"] = {"start": start_7d, "end": end_iso, "totals": gsc_query(site_enc, headers, start_7d, end_iso)}
    out["window_28d"] = {
        "start": start_28d,
        "end": end_iso,
        "totals": gsc_query(site_enc, headers, start_28d, end_iso),
        "countries": gsc_query(site_enc, headers, start_28d, end_iso, ["country"], 30),
        "top_queries": gsc_query(site_enc, headers, start_28d, end_iso, ["query"], 500),
        "top_pages": gsc_query(site_enc, headers, start_28d, end_iso, ["page"], 100),
        "singapore_queries": gsc_query(
            site_enc, headers, start_28d, end_iso, ["query"], 200,
            dimensionFilterGroups=_country_filter("sgp"),
        ),
        "india_queries": gsc_query(
            site_enc, headers, start_28d, end_iso, ["query"], 200,
            dimensionFilterGroups=_country_filter("ind"),
        ),
        "query_page_pairs": gsc_query(site_enc, headers, start_28d, end_iso, ["query", "page"], 250),
    }

    state["gsc_status"] = "ok"
    state["gsc_last_sync"] = out["generated_at"]
    stamp = now_utc().strftime("%Y-%m-%d")
    save_json(REPORT_DIR / f"gsc-{stamp}.json", out)
    save_json(REPORT_DIR / "latest-gsc.json", out)
    log("gsc: snapshot complete for %s" % cfg["gsc_site"])
    return out


def ga4_snapshot(cfg, state):
    token, reason = google_token()
    if not token:
        state["ga4_status"] = "reauth_required" if reason == "invalid_grant" else reason
        log("ga4: skipped (%s)" % state["ga4_status"])
        return {"status": state["ga4_status"]}
    prop = cfg.get("ga4_property_id", "547082278")
    headers = {"Authorization": "Bearer " + token, "Content-Type": "application/json"}
    url = f"https://analyticsdata.googleapis.com/v1beta/properties/{prop}:runReport"

    def run_rep(body):
        st, txt, _ = http(url, data=json.dumps(body).encode(), headers=headers, method="POST", timeout=30)
        return json.loads(txt) if st == 200 else {"error": st, "body": txt[:200]}

    out = {
        "status": "ok",
        "generated_at": now_utc().isoformat(),
        "property_id": prop,
        "totals_28d": run_rep({
            "dateRanges": [{"startDate": "28daysAgo", "endDate": "yesterday"}],
            "metrics": [
                {"name": "activeUsers"}, {"name": "newUsers"}, {"name": "sessions"},
                {"name": "screenPageViews"}, {"name": "keyEvents"},
            ],
        }),
        "channels_28d": run_rep({
            "dateRanges": [{"startDate": "28daysAgo", "endDate": "yesterday"}],
            "dimensions": [{"name": "sessionDefaultChannelGroup"}],
            "metrics": [{"name": "activeUsers"}, {"name": "sessions"}, {"name": "screenPageViews"}],
        }),
        "events_28d": run_rep({
            "dateRanges": [{"startDate": "28daysAgo", "endDate": "yesterday"}],
            "dimensions": [{"name": "eventName"}],
            "metrics": [{"name": "eventCount"}],
        }),
    }
    state["ga4_status"] = "ok"
    state["ga4_last_sync"] = out["generated_at"]
    stamp = now_utc().strftime("%Y-%m-%d")
    save_json(REPORT_DIR / f"ga4-{stamp}.json", out)
    save_json(REPORT_DIR / "latest-ga4.json", out)
    log("ga4: snapshot complete for property %s" % prop)
    return out


def leads_snapshot(state):
    """Count verified leads and blocked bots from cPanel without storing any PII."""
    out = {"generated_at": now_utc().isoformat(), "verified_leads_total": None, "spam_blocked_total": None}
    try:
        raw_leads = remote_get("public_html", "leads_log.json")
        if raw_leads:
            parsed = json.loads(raw_leads)
            if isinstance(parsed, list):
                out["verified_leads_total"] = len(parsed)
                # Count leads in Nov 15 - Dec 15 cycle by timestamp field if present
                cycle_cnt = 0
                for item in parsed:
                    ts = str(item.get("timestamp") or item.get("date") or item.get("created_at") or "")
                    if "2026-11-1" in ts or "2026-11-2" in ts or "2026-11-3" in ts or "2026-12-" in ts:
                        if ts >= "2026-11-15":
                            cycle_cnt += 1
                out["verified_leads_since_nov15"] = cycle_cnt
    except Exception as e:
        out["leads_error"] = str(e)

    try:
        raw_spam = remote_get("public_html", "leads_spam_log.json")
        if raw_spam:
            # May be JSON array or JSON lines
            txt = raw_spam.strip()
            if txt.startswith("["):
                arr = json.loads(txt)
            else:
                arr = [json.loads(ln) for ln in txt.splitlines() if ln.strip()]
            out["spam_blocked_total"] = len(arr)
            cycle_spam = 0
            for item in arr:
                ts = str(item.get("timestamp") or item.get("time") or item.get("date") or "")
                if ts >= "2026-11-15":
                    cycle_spam += 1
            out["spam_blocked_since_nov15"] = cycle_spam
    except Exception as e:
        out["spam_error"] = str(e)

    state["last_leads_snapshot"] = out
    save_json(REPORT_DIR / "latest-leads.json", out)
    log(f"leads: total={out.get('verified_leads_total')} spam_blocked={out.get('spam_blocked_total')}")
    return out


def maybe_freeze_monthly_boundary(summary, gsc, ga4, leads):
    """Freeze immutable cycle-boundary snapshots on the 14th and 15th of every month (and initial baseline)."""
    d = today_sgt_date()
    snap_file = SNAPSHOT_DIR / f"boundary-{d.isoformat()}.json"
    baseline_init = SNAPSHOT_DIR / "cycle-start-2026-11-18.json"
    payload = {
        "captured_at": now_utc().isoformat(),
        "sgt_date": d.isoformat(),
        "active_cycle": active_cycle_window(d),
        "summary": summary,
        "gsc": gsc,
        "ga4": ga4,
        "leads": leads,
    }
    if not baseline_init.exists():
        save_json(baseline_init, payload)
        log(f"snapshot: wrote initial cycle baseline {baseline_init.name}")
    if d.day in (14, 15) and not snap_file.exists():
        save_json(snap_file, payload)
        log(f"snapshot: froze monthly cycle boundary {snap_file.name}")


_LLMS_CORE_SLUGS = {
    "",
    "corporate-event-management-company",
    "event-management-company-in-singapore",
    "event-management-company-in-bangalore",
    "event-management-company-in-india",
    "our-events-and-services",
    "event-marketing-services",
    "event-planner",
    "experiential-marketing-brand-activations",
    "conference-and-mice-event-management",
    "exhibition-and-trade-show-management",
    "dinner-and-dance-event-management-singapore",
    "product-launch-event-management",
    "corporate-annual-day-and-awards-night-management",
    "corporate-event-case-studies",
    "about-us",
    "clientele",
    "blog",
    "get-in-touch",
    "book-a-demo",
}

_LLMS_CURATED_META = {
    "": ("Home", "Overview of Framez B2B corporate event management, MICE production, and contact options"),
    "corporate-event-management-company": ("Corporate Event Management", "End-to-end corporate event planning, stage engineering, and production scope across Singapore and India"),
    "event-management-company-in-singapore": ("Event Management Company in Singapore", "Corporate conferences, MICE summits, product launches, Dinner and Dance galas, and activations managed from Prudential Tower, Singapore"),
    "event-management-company-in-bangalore": ("Event Management Company in Bangalore", "Bangalore corporate event management, stage AV production, venue sourcing, and delegate logistics from Koramangala HQ"),
    "event-management-company-in-india": ("Event Management Company in India", "Pan-India corporate event delivery across Bengaluru, Mumbai, Delhi NCR, Hyderabad, and Chennai"),
    "our-events-and-services": ("Events and Services", "Full service catalogue covering conferences, MICE, residential meets, rewards, exhibitions, and brand activations"),
    "event-marketing-services": ("Event Marketing Services", "B2B event promotion, audience acquisition, delegate registration workflows, and trade show lead capture"),
    "event-planner": ("Event Planner", "Enterprise corporate event planning, run-of-show management, and turnkey technical production"),
    "experiential-marketing-brand-activations": ("Experiential Marketing & Brand Activations", "Pop-ups, roadshows, exhibition environments, and interactive brand experiences"),
    "about-us": ("About Us", "Company background, dual-HQ operations, ISO 9001:2015 and ISO 27001:2013 governance"),
    "clientele": ("Clientele", "Enterprise client portfolio across technology, financial services, healthcare, and MICE sectors"),
    "blog": ("Blog & Guides", "Practical planning guides, procurement checklists, and technical handbooks for corporate event buyers"),
    "get-in-touch": ("Contact", "Direct enquiry form, Prudential Tower Singapore and Koramangala Bengaluru office details"),
    "book-a-demo": ("Book a Demo", "Schedule an event brief walkthrough, venue check, and scoped production quote"),
    "corporate-event-budget-planning-guide": ("Corporate Event Budget Planning Guide", "Cost categories, quote scope, fixed vs per-guest items, change orders, and procurement checklist"),
    "annual-day-and-awards-night-planning-guide": ("Annual Day & Awards Night Planning Guide", "Recognition goals, award approvals, rehearsal run-of-show, and inclusive guest planning"),
    "corporate-event-roi-measurement-guide": ("Corporate Event ROI Measurement Guide", "Objectives vs metrics, attendance denominators, attribution models, and closeout reporting"),
    "singapore-corporate-event-planning-checklist": ("Singapore Corporate Event Planning Checklist", "Venue access, PDPA attendee data compliance, permits, wet-weather fallback, and supplier vetting"),
    "corporate-event-planning-handbook-2027": ("The 2027 Corporate Event Planning Handbook", "Enterprise planning framework for APAC corporate events, budgets, and AV standards"),
    "experiential-brand-activations-framework": ("Experiential Brand Activations Framework", "Activation design, dwell time metrics, and lead capture models for enterprise teams"),
    "executive-offsite-retreat-blueprint": ("Executive Offsite Retreat Blueprint", "Leadership offsite venue selection, security, agenda architecture, and logistics"),
    "b2b-event-agency-rfp-evaluation-guide": ("B2B Event Agency RFP Evaluation Guide", "Procurement scoring rubrics, SLA benchmarks, and vendor contract checks"),
    "corporate-product-launch-event-architecture": ("Corporate Product Launch Event Architecture", "Reveal engineering, press operations, broadcast standards, and lead routing"),
    "high-security-cxo-board-summit-protocol": ("High-Security CXO Board Summit Protocol", "Executive summit confidentiality tiers, TSCM sweeps, and duty-of-care protocols"),
    "festive-corporate-gala-diwali-celebrations": ("Festive Corporate Gala & Diwali Celebrations", "Corporate festive programming, venue decor fire safety, and inclusive design"),
    "corporate-family-day-carnival-safety-logistics": ("Corporate Family Day Carnival Safety & Logistics", "Child-safe zone zoning, vendor vetting, crowd engineering, and medical readiness"),
    "corporate-event-trends-singapore": ("Corporate Event Trends in Singapore", "Singapore MICE production shifts, sustainable staging, and experiential AV trends"),
    "Framez-Public-Statement-on-Health-and-Safety-Commitment": ("Health and Safety Commitment Statement", "Public ISO 9001:2015, ISO 27001:2013, and site safety compliance statement"),
}


def _collect_llms_page_metadata(cfg, sitemap_entries, extra_pages=None):
    """Build clean title/description/category metadata for every live sitemap URL."""
    base = cfg["site"].rstrip("/")
    audit_rep = load_json(REPORT_DIR / "latest-audit.json", {})
    audit_titles = {}
    for p in (audit_rep.get("pages") or []):
        if isinstance(p, dict) and p.get("url"):
            audit_titles[_normalize_site_url(cfg, p["url"])] = p.get("title") or ""

    wave_meta = {}
    core_slugs = set(_LLMS_CORE_SLUGS)
    for w in STAGED_WAVES:
        spec = w.get("spec") or {}
        sl = spec.get("slug", "")
        if sl:
            wave_meta[sl] = (
                spec.get("h1") or spec.get("title") or sl,
                spec.get("description") or "",
            )
            if spec.get("kind") == "service":
                core_slugs.add(sl)

    extra_meta = {}
    extra_urls = []
    for ep in (extra_pages or []):
        if isinstance(ep, dict) and ep.get("loc"):
            nu = _normalize_site_url(cfg, ep["loc"])
            eslug = url_to_slug(cfg, nu)
            extra_meta[eslug] = (ep.get("title") or eslug, ep.get("desc") or "")
            if ep.get("kind") == "service":
                core_slugs.add(eslug)
            extra_urls.append(nu)

    all_urls = []
    seen = set()
    for e in sitemap_entries:
        nu = _normalize_site_url(cfg, e.get("loc"))
        if nu and nu not in seen:
            seen.add(nu)
            all_urls.append(nu)
    for nu in extra_urls:
        if nu not in seen:
            seen.add(nu)
            all_urls.append(nu)

    core_items = []
    guide_items = []
    for u in all_urls:
        slug = url_to_slug(cfg, u)
        if slug in _LLMS_CURATED_META:
            title, desc = _LLMS_CURATED_META[slug]
        elif slug in extra_meta:
            title, desc = extra_meta[slug]
        elif slug in wave_meta:
            title, desc = wave_meta[slug]
        else:
            title = audit_titles.get(u, "")
            desc = ""
            if not title or not desc:
                try:
                    st, html, _ = fetch(u)
                    if st == 200:
                        info = analyze_page(u, html)
                        title = title or info.get("title") or slug or "Home"
                        desc = desc or info.get("description") or ""
                except Exception:
                    pass
            if not title:
                title = slug.replace("-", " ").title() if slug else "Home"
        if not desc:
            desc = f"Framez Events & Productions resource at {base}/{slug}" if slug else "Framez corporate event management homepage"

        title = _strip_dashes(re.sub(r"\s*\|\s*Framez.*$", "", title).strip())
        desc = _strip_dashes(desc.strip())
        item = {"url": u, "slug": slug, "title": title, "desc": desc}
        if slug in core_slugs:
            core_items.append(item)
        else:
            guide_items.append(item)

    return core_items, guide_items


def sync_llms_files(cfg=None, state=None, upload=True, extra_pages=None):
    """Build and sync llms.txt and llms-full.txt with all live sitemap URLs, dual-HQ NAP, ISO proof, and entity disambiguation."""
    cfg = cfg or config()
    state = state if state is not None else {}
    log("llms: checking parity against %s" % cfg["sitemap_url"])
    status, xml_text, _ = fetch(cfg["sitemap_url"])
    if status != 200:
        raise RuntimeError(f"sync_llms_files: sitemap fetch failed HTTP {status}")

    entries = parse_sitemap(xml_text)
    core_items, guide_items = _collect_llms_page_metadata(cfg, entries, extra_pages=extra_pages)

    llms_txt_lines = [
        "# Framez Events & Productions",
        "",
        "> Frame Events and Productions Private Limited (India HQ) and Frame Events & Productions Pte. Ltd. (Singapore), operating publicly as Framez and Framez Events & Productions (https://framez.sg), is an enterprise B2B corporate event management, MICE, and technical production agency. Framez is distinct from consumer ticketing marketplaces and unrelated photography studios.",
        "",
        "## Entity Disambiguation, Dual-HQ NAP & Certifications",
        "",
        "- **Legal Entities:** Frame Events and Productions Private Limited (India HQ) / Frame Events & Productions Pte. Ltd. (Singapore)",
        "- **Brand Names:** Framez, Framez Events & Productions",
        "- **Singapore Office:** 30 Cecil Street, #19-08 Prudential Tower, Singapore 049712",
        "- **India Headquarters (Bengaluru):** B/2, GANGA, 3rd Floor, 5th Block, KHB Colony, Koramangala, Bengaluru, Karnataka 560095, India",
        "- **Email:** info@framez.sg",
        "- **Phone:** +91-9448066560",
        "- **Website:** https://framez.sg",
        "- **Certifications (ISO Proof):** ISO 9001:2015 (Quality Management: https://framez.sg/FRAMEZ%20ISO%209001%20Certificate.pdf) and ISO 27001:2013 (Information Security: https://framez.sg/FRAMEZ%20ISO%2027001%20Certificate.pdf)",
        "- **Health & Safety Compliance:** https://framez.sg/Framez-Public-Statement-on-Health-and-Safety-Commitment",
        "- **Official Social Profiles:** LinkedIn (https://www.linkedin.com/company/frame-events-productions), Instagram (https://www.instagram.com/weareframez/), Facebook (https://www.facebook.com/frameeventsandproductions)",
        "",
        "## Services",
        "",
        "- Corporate event management and end-to-end stage/AV production",
        "- B2B conferences, tech summits, and MICE programmes",
        "- Enterprise product launches, executive board summits, and ceremonies",
        "- Corporate annual days, Dinner & Dance galas, and employee awards nights",
        "- Experiential marketing, exhibitions, trade show stalls, and brand activations",
        "",
        "## Core commercial and brand pages",
        "",
    ]
    for it in core_items:
        llms_txt_lines.append(f"- [{it['title']}]({it['url']})")

    llms_txt_lines.extend(["", "## Guides, handbooks and trust resources", ""])
    for it in guide_items:
        llms_txt_lines.append(f"- [{it['title']}]({it['url']})")

    llms_full_lines = [
        "# Framez Events & Productions: Full Site Context",
        "",
        "> Frame Events and Productions Private Limited (India HQ) and Frame Events & Productions Pte. Ltd. (Singapore), operating publicly as Framez and Framez Events & Productions (https://framez.sg), is an enterprise B2B corporate event management, experiential marketing, and technical production agency serving Singapore and India. This file provides factual navigation context for crawlers and answer engines and is distinct from unrelated consumer ticketing apps or photography studios.",
        "",
        "## Company Profile, Entity Disambiguation & Verified Dual-HQ NAP",
        "",
        "- **Legal Entities:** Frame Events and Productions Private Limited (India) / Frame Events & Productions Pte. Ltd. (Singapore)",
        "- **Brand & Alternate Names:** Framez, Framez Events & Productions",
        "- **Commercial Focus:** B2B corporate events, MICE conferences, product launches, Dinner & Dance galas, awards nights, exhibitions, and brand activations",
        "- **ISO Certifications:** ISO 9001:2015 Quality Management (https://framez.sg/FRAMEZ%20ISO%209001%20Certificate.pdf) and ISO 27001:2013 Information Security (https://framez.sg/FRAMEZ%20ISO%2027001%20Certificate.pdf)",
        "- **Compliance & Data Protection:** Singapore PDPA attendee data handling, NDA-protected enterprise broadcasts, and published Health & Safety commitment (https://framez.sg/Framez-Public-Statement-on-Health-and-Safety-Commitment)",
        "- **Singapore Office:** 30 Cecil Street, #19-08 Prudential Tower, Singapore 049712",
        "- **India Headquarters (Bengaluru):** B/2, GANGA, 3rd Floor, 5th Block, KHB Colony, Koramangala, Bengaluru, Karnataka 560095, India",
        "- **Email:** info@framez.sg",
        "- **Phone:** +91-9448066560",
        "- **Website:** https://framez.sg",
        "- **Social:** LinkedIn (https://www.linkedin.com/company/frame-events-productions), Instagram (https://www.instagram.com/weareframez/), Facebook (https://www.facebook.com/frameeventsandproductions)",
        "",
        "## Core commercial and brand pages",
        "",
    ]
    for it in core_items:
        llms_full_lines.append(f"- [{it['title']}]({it['url']}): {it['desc']}")

    llms_full_lines.extend(["", "## Guides, handbooks and trust resources", ""])
    for it in guide_items:
        llms_full_lines.append(f"- [{it['title']}]({it['url']}): {it['desc']}")

    llms_full_lines.extend([
        "",
        "## How to engage",
        "",
        "1. Share your event type, target dates, city (Singapore or India), and expected delegate count via https://framez.sg/get-in-touch or https://framez.sg/book-a-demo.",
        "2. Framez prepares a scoped technical and operational proposal specifying inclusions, exclusions, and line-item production costs.",
        "3. Delivery covers venue coordination, staging and AV engineering, vendor management, compliance documentation, and on-ground show calling.",
        "",
    ])

    new_files = {
        "llms.txt": _strip_dashes("\n".join(llms_txt_lines).rstrip() + "\n"),
        "llms-full.txt": _strip_dashes("\n".join(llms_full_lines).rstrip() + "\n"),
    }

    updated_files = []
    sha_map = {}
    stamp = now_utc().strftime("%Y%m%dT%H%M%SZ")
    bdir = BACKUP_DIR / f"llms-sync-{stamp}"

    for fname, content in new_files.items():
        sha = hashlib.sha256(content.encode("utf-8")).hexdigest()
        sha_map[fname] = sha
        if upload:
            cur = remote_get("public_html", fname) or ""
        else:
            try:
                _, cur, _ = fetch(cfg["site"].rstrip("/") + "/" + fname)
            except Exception:
                cur = ""
        if cur.strip() == content.strip():
            continue
        if upload:
            bdir.mkdir(parents=True, exist_ok=True)
            if cur:
                (bdir / fname).write_text(cur, encoding="utf-8")
            ok = remote_put("public_html", fname, content)
            if not ok:
                raise RuntimeError(f"sync_llms_files: cPanel upload failed for {fname}")
            rb = remote_get("public_html", fname) or ""
            if hashlib.sha256(rb.encode("utf-8")).hexdigest() != sha:
                raise RuntimeError(f"sync_llms_files: SHA-256 readback mismatch on {fname}")
            updated_files.append(fname)
            log(f"llms: uploaded & SHA-256 verified {fname} ({len(core_items) + len(guide_items)} URLs)")
        else:
            updated_files.append(fname)

    res = {
        "status": "ok",
        "generated_at": now_utc().isoformat(),
        "total_urls": len(core_items) + len(guide_items),
        "core_urls": len(core_items),
        "guide_urls": len(guide_items),
        "updated_files": updated_files,
        "uploaded": bool(upload and updated_files),
        "sha256": sha_map,
    }
    state["last_llms_sync_at"] = res["generated_at"]
    state["last_llms_sync"] = res
    if upload and updated_files:
        append_ledger({"event": "llms_files_synced", **res})
    return res


def _extract_llms_urls(cfg, txt):
    """Extract normalized framez.sg page URLs referenced inside an llms.txt file."""
    urls, seen = [], set()
    skip_ext = (".pdf", ".txt", ".xml", ".png", ".jpg", ".jpeg", ".webp", ".svg", ".css", ".js")
    for raw in re.findall(r"https://framez\.sg[^\s\)\]>\"']*", txt or "", re.I):
        cleaned = raw.rstrip(".,;:")
        low = cleaned.lower()
        if any(low.endswith(ext) for ext in skip_ext) or "/assets/" in low:
            continue
        norm = _normalize_site_url(cfg, cleaned)
        if norm and norm not in seen:
            seen.add(norm)
            urls.append(norm)
    return urls


def _extract_page1_zero_ctr(gsc_data):
    """Identify Page-1 (position <= 10.0) queries and pages with zero clicks from latest-gsc.json."""
    w28 = (gsc_data or {}).get("window_28d") or {}
    query_to_page = {}
    query_best_imp = {}
    for row in (w28.get("query_page_pairs") or {}).get("rows") or []:
        keys = row.get("keys") or []
        if len(keys) >= 2:
            q, p = keys[0], keys[1]
            imp = row.get("impressions", 0)
            if imp > query_best_imp.get(q, -1):
                query_best_imp[q] = imp
                query_to_page[q] = p

    def _scan_queries(section_key, country_tag):
        out = []
        for row in (w28.get(section_key) or {}).get("rows") or []:
            q = (row.get("keys") or [""])[0]
            clicks = row.get("clicks", 0)
            imp = row.get("impressions", 0)
            pos = row.get("position", 99.0)
            if imp >= 1 and clicks == 0 and pos <= 10.0:
                out.append({
                    "query": q,
                    "impressions": imp,
                    "clicks": clicks,
                    "ctr": 0.0,
                    "position": round(pos, 1),
                    "country": country_tag,
                    "page": query_to_page.get(q, ""),
                })
        out.sort(key=lambda x: (-x["impressions"], x["position"], x["query"]))
        return out

    global_q = _scan_queries("top_queries", "all")
    sgp_q = _scan_queries("singapore_queries", "sgp")
    ind_q = _scan_queries("india_queries", "ind")

    pages_p1 = []
    for row in (w28.get("top_pages") or {}).get("rows") or []:
        page = (row.get("keys") or [""])[0]
        clicks = row.get("clicks", 0)
        imp = row.get("impressions", 0)
        pos = row.get("position", 99.0)
        if imp >= 1 and clicks == 0 and pos <= 10.0:
            pages_p1.append({
                "page": page,
                "impressions": imp,
                "clicks": clicks,
                "ctr": 0.0,
                "position": round(pos, 1),
            })
    pages_p1.sort(key=lambda x: (-x["impressions"], x["position"], x["page"]))

    return {
        "gsc_available": bool(w28),
        "queries": global_q,
        "singapore_queries": sgp_q,
        "india_queries": ind_q,
        "pages": pages_p1,
        "total_query_alerts": len(global_q),
        "total_singapore_alerts": len(sgp_q),
        "total_india_alerts": len(ind_q),
        "total_page_alerts": len(pages_p1),
        "total_alerts": len(global_q) + len(pages_p1),
    }


def _expected_schema_for_slug(slug):
    """Return expected JSON-LD schema role checks for a given slug."""
    service_slugs = {
        "our-events-and-services",
        "corporate-event-management-company",
        "event-management-company-in-bangalore",
        "event-management-company-in-india",
        "event-management-company-in-singapore",
        "event-planner",
        "event-marketing-services",
        "experiential-marketing-brand-activations",
        "conference-and-mice-event-management",
        "exhibition-and-trade-show-management",
        "dinner-and-dance-event-management-singapore",
        "product-launch-event-management",
        "corporate-annual-day-and-awards-night-management",
    }
    utility_slugs = {"", "about-us", "clientele", "blog", "get-in-touch", "book-a-demo"}
    for w in STAGED_WAVES:
        sp = w.get("spec") or {}
        if sp.get("kind") == "service" and sp.get("slug"):
            service_slugs.add(sp["slug"])

    if slug in service_slugs:
        expected = ["Organization", "Service", "FAQPage"]
        if "singapore" in slug or "bangalore" in slug or "corporate-event-management-company" == slug:
            expected.append("ProfessionalService")
        return "service", expected
    if slug in utility_slugs:
        return "utility", ["Organization"]
    if slug == "Framez-Public-Statement-on-Health-and-Safety-Commitment":
        return "trust", ["Organization", "Article"]
    return "guide", ["Organization", "Article", "FAQPage"]


def geo_aeo_audit(cfg, state):
    """Audit all live sitemap URLs for GEO/AEO readiness, schema, llms parity, mixed content, jQuery, scripts, images, and Page-1 zero-CTR alerts."""
    log("geo_audit: start")
    status, xml_text, _ = fetch(cfg["sitemap_url"])
    if status != 200:
        raise RuntimeError("geo_audit: sitemap fetch failed HTTP %s" % status)
    entries = parse_sitemap(xml_text)
    sitemap_urls = [_normalize_site_url(cfg, e["loc"]) for e in entries if e.get("loc")]

    base = cfg["site"].rstrip("/")
    llms_texts = {}
    for lf in ("llms.txt", "llms-full.txt"):
        try:
            st_l, body_l, _ = fetch(f"{base}/{lf}")
            llms_texts[lf] = body_l if st_l == 200 else ""
        except Exception:
            llms_texts[lf] = ""

    llms_urls = _extract_llms_urls(cfg, llms_texts["llms.txt"])
    llms_full_urls = _extract_llms_urls(cfg, llms_texts["llms-full.txt"])
    sitemap_set = set(sitemap_urls)

    def _check_llms_proof(txt):
        low = (txt or "").lower()
        return {
            "has_nap": ("prudential tower" in low and "koramangala" in low and "+91-9448066560" in low),
            "has_iso": ("9001:2015" in low and "27001:2013" in low),
            "has_entity": ("frame events and productions private limited" in low and "framez" in low),
            "has_em_en_dash": ("\u2014" in (txt or "") or "\u2013" in (txt or "")),
        }

    llms_proof = _check_llms_proof(llms_texts["llms.txt"])
    llms_full_proof = _check_llms_proof(llms_texts["llms-full.txt"])
    em_en_dash_files = [lf for lf, txt in llms_texts.items() if "\u2014" in txt or "\u2013" in txt]

    missing_in_llms_txt = [u for u in sitemap_urls if u not in set(llms_urls)]
    missing_in_llms_full_txt = [u for u in sitemap_urls if u not in set(llms_full_urls)]
    extra_in_llms_txt = [u for u in llms_urls if u not in sitemap_set]
    extra_in_llms_full_txt = [u for u in llms_full_urls if u not in sitemap_set]

    gsc_data = load_json(REPORT_DIR / "latest-gsc.json", {})
    p1_alerts = _extract_page1_zero_ctr(gsc_data)
    p1_page_map = {_normalize_site_url(cfg, p["page"]): p for p in p1_alerts["pages"]}

    page_results = []
    schema_counts = {
        "Organization": 0,
        "ProfessionalService": 0,
        "FAQPage": 0,
        "Service": 0,
        "Article": 0,
        "SpeakableSpecification": 0,
        "BreadcrumbList": 0,
    }
    schema_checks_passed = 0
    schema_checks_total = 0

    mixed_maps_pages = []
    mixed_asset_pages = []
    dup_jquery_pages = []
    blocking_pages = []
    total_blocking_scripts = 0
    script_credit_sum = 0.0
    total_images = 0
    total_missing_dims = 0
    total_missing_lazy = 0
    missing_schema_pages = []

    for url in sitemap_urls:
        try:
            st, html, _ = fetch(url)
        except Exception as e:
            page_results.append({"url": url, "status": 0, "error": str(e)})
            continue

        slug = url_to_slug(cfg, url)
        role, expected_types = _expected_schema_for_slug(slug)
        ld_types, ld_invalid, has_speakable = _extract_jsonld_info(html)
        types_set = set(ld_types)

        has_org = "Organization" in types_set
        has_prof = "ProfessionalService" in types_set
        has_faq = "FAQPage" in types_set
        has_service = "Service" in types_set
        has_article = bool({"Article", "TechArticle"} & types_set)
        has_crumb = "BreadcrumbList" in types_set

        if has_org:
            schema_counts["Organization"] += 1
        if has_prof:
            schema_counts["ProfessionalService"] += 1
        if has_faq:
            schema_counts["FAQPage"] += 1
        if has_service:
            schema_counts["Service"] += 1
        if has_article:
            schema_counts["Article"] += 1
        if has_speakable:
            schema_counts["SpeakableSpecification"] += 1
        if has_crumb:
            schema_counts["BreadcrumbList"] += 1

        present_map = {
            "Organization": has_org,
            "ProfessionalService": has_prof,
            "FAQPage": has_faq,
            "Service": has_service,
            "Article": has_article,
        }
        missing_exp = [t for t in expected_types if not present_map.get(t, False)]
        schema_checks_total += len(expected_types)
        schema_checks_passed += (len(expected_types) - len(missing_exp))
        if missing_exp:
            missing_schema_pages.append({"url": url, "role": role, "missing": missing_exp})

        maps_http = re.findall(r"http://maps\.google\.com[^\s\"'<>]*", html, re.I)
        insecure_srcs = re.findall(
            r"""<(?:script|iframe|img|source|video|audio)\b[^>]*\bsrc\s*=\s*["'](http://[^"']+)["']""",
            html,
            re.I,
        )
        insecure_css = re.findall(
            r"""<link\b[^>]*rel\s*=\s*["'][^"']*stylesheet[^"']*["'][^>]*href\s*=\s*["'](http://[^"']+)["']""",
            html,
            re.I,
        )
        mixed_assets = sorted(set(maps_http + insecure_srcs + insecure_css))
        if maps_http:
            mixed_maps_pages.append({"url": url, "matches": sorted(set(maps_http))})
        if mixed_assets:
            mixed_asset_pages.append({"url": url, "urls": mixed_assets})

        script_tags = re.findall(r"<script\b([^>]*)>", html, re.I)
        jquery_scripts = []
        blocking_scripts = []
        for attrs in script_tags:
            src_m = re.search(r"""\bsrc\s*=\s*["']([^"']+)["']""", attrs, re.I)
            if not src_m:
                continue
            src = src_m.group(1)
            if re.search(r"(?:^|/)(?:jquery(?:-\d+\.\d+(?:\.\d+)?)?(?:\.min)?\.js)(?:[?#]|$)", src, re.I):
                jquery_scripts.append(src)
            if not re.search(r"\b(async|defer)\b", attrs, re.I) and not re.search(
                r"""\btype\s*=\s*["']module["']""", attrs, re.I
            ):
                blocking_scripts.append(src)

        jq_joined = " ".join(jquery_scripts).lower()
        duplicate_jquery = len(jquery_scripts) > 1 or ("3.3.1" in jq_joined and "3.5.1" in jq_joined)
        if duplicate_jquery:
            dup_jquery_pages.append({"url": url, "scripts": jquery_scripts})

        bcount = len(blocking_scripts)
        total_blocking_scripts += bcount
        if bcount > 0:
            blocking_pages.append({"url": url, "blocking_count": bcount, "scripts": blocking_scripts[:10]})
        if bcount == 0:
            script_credit_sum += 1.0
        elif bcount <= 2:
            script_credit_sum += 0.5

        imgs = re.findall(r"<img\b[^>]*>", html, re.I)
        missing_dims = sum(
            1 for im in imgs
            if not (re.search(r"\bwidth\s*=", im, re.I) and re.search(r"\bheight\s*=", im, re.I))
        )
        missing_lazy = sum(
            1 for im in imgs
            if not re.search(r"""\bloading\s*=\s*["']?lazy["']?""", im, re.I)
        )
        total_images += len(imgs)
        total_missing_dims += missing_dims
        total_missing_lazy += missing_lazy

        p1_info = p1_page_map.get(url)
        page_results.append({
            "url": url,
            "status": st,
            "role": role,
            "jsonld_types": sorted(types_set),
            "jsonld_invalid": ld_invalid,
            "has_organization": has_org,
            "has_professional_service": has_prof,
            "has_faq_page": has_faq,
            "has_service": has_service,
            "has_article": has_article,
            "has_speakable": has_speakable,
            "missing_expected_schema": missing_exp,
            "mixed_content_maps_google": sorted(set(maps_http)),
            "mixed_content_assets": mixed_assets,
            "jquery_scripts": jquery_scripts,
            "duplicate_jquery": duplicate_jquery,
            "blocking_script_count": bcount,
            "blocking_scripts": blocking_scripts,
            "images_total": len(imgs),
            "images_missing_dimensions": missing_dims,
            "images_missing_lazy": missing_lazy,
            "page1_zero_ctr": p1_info,
        })

    n_pages = max(len(page_results), 1)
    n_sitemap = max(len(sitemap_urls), 1)

    schema_score = round(25.0 * (schema_checks_passed / max(schema_checks_total, 1)), 1)
    cov_txt = (len(sitemap_urls) - len(missing_in_llms_txt)) / n_sitemap
    cov_full = (len(sitemap_urls) - len(missing_in_llms_full_txt)) / n_sitemap
    proof_pts = 0.0
    for pr in (llms_proof, llms_full_proof):
        if pr["has_nap"]:
            proof_pts += 0.75
        if pr["has_iso"]:
            proof_pts += 0.75
        if pr["has_entity"]:
            proof_pts += 0.75
        if not pr["has_em_en_dash"]:
            proof_pts += 0.75
    llms_parity_score = round(7.0 * cov_txt + 7.0 * cov_full + proof_pts, 1)
    mixed_content_score = round(15.0 * (1.0 - (len(mixed_asset_pages) / n_pages)), 1)
    script_hygiene_score = round(
        7.5 * (1.0 - (len(dup_jquery_pages) / n_pages)) + 7.5 * (script_credit_sum / n_pages),
        1,
    )
    if total_images > 0:
        dims_ratio = (total_images - total_missing_dims) / total_images
        lazy_ratio = (total_images - total_missing_lazy) / total_images
        image_hygiene_score = round(7.5 * dims_ratio + 7.5 * lazy_ratio, 1)
    else:
        image_hygiene_score = 15.0

    if p1_alerts["gsc_available"]:
        penalty = min(10.0, p1_alerts["total_page_alerts"] * 1.0 + p1_alerts["total_query_alerts"] * 0.25)
        page1_ctr_score = round(max(0.0, 10.0 - penalty), 1)
    else:
        page1_ctr_score = 0.0

    readiness_breakdown = {
        "schema_completeness_max25": schema_score,
        "llms_parity_proof_max20": llms_parity_score,
        "mixed_content_hygiene_max15": mixed_content_score,
        "script_jquery_hygiene_max15": script_hygiene_score,
        "image_dims_lazy_max15": image_hygiene_score,
        "page1_ctr_hygiene_max10": page1_ctr_score,
    }
    readiness_score = round(sum(readiness_breakdown.values()), 1)

    report = {
        "generated_at": now_utc().isoformat(),
        "site": cfg["site"],
        "sitemap_urls": len(sitemap_urls),
        "audited_urls": len(page_results),
        "readiness_score": readiness_score,
        "readiness_breakdown": readiness_breakdown,
        "schema_summary": {
            "counts": schema_counts,
            "checks_passed": schema_checks_passed,
            "checks_total": schema_checks_total,
            "missing_schema_pages": missing_schema_pages,
        },
        "llms_parity": {
            "sitemap_url_count": len(sitemap_urls),
            "llms_txt_urls": len(llms_urls),
            "llms_full_txt_urls": len(llms_full_urls),
            "missing_in_llms_txt": missing_in_llms_txt,
            "missing_in_llms_full_txt": missing_in_llms_full_txt,
            "extra_in_llms_txt": extra_in_llms_txt,
            "extra_in_llms_full_txt": extra_in_llms_full_txt,
            "llms_txt_parity_ok": len(missing_in_llms_txt) == 0,
            "llms_full_txt_parity_ok": len(missing_in_llms_full_txt) == 0,
            "llms_txt_proof": llms_proof,
            "llms_full_txt_proof": llms_full_proof,
            "em_en_dash_files": em_en_dash_files,
        },
        "technical_findings": {
            "mixed_content_maps_google_pages": mixed_maps_pages,
            "mixed_content_asset_pages": mixed_asset_pages,
            "duplicate_jquery_pages": dup_jquery_pages,
            "pages_with_blocking_scripts": len(blocking_pages),
            "total_blocking_scripts": total_blocking_scripts,
            "blocking_scripts_pages": blocking_pages,
            "images_total": total_images,
            "images_missing_dimensions": total_missing_dims,
            "images_missing_lazy": total_missing_lazy,
            "pages_missing_image_dimensions": [
                {"url": r["url"], "missing": r["images_missing_dimensions"], "total": r["images_total"]}
                for r in page_results if r.get("images_missing_dimensions")
            ],
            "pages_missing_image_lazy": [
                {"url": r["url"], "missing": r["images_missing_lazy"], "total": r["images_total"]}
                for r in page_results if r.get("images_missing_lazy")
            ],
        },
        "page1_zero_ctr_alerts": p1_alerts,
        "pages": page_results,
    }

    stamp = now_utc().strftime("%Y-%m-%d")
    save_json(REPORT_DIR / f"geo-audit-{stamp}.json", report)
    save_json(REPORT_DIR / "latest-geo-audit.json", report)

    state["last_geo_audit_at"] = report["generated_at"]
    state["last_geo_audit_summary"] = {
        "readiness_score": readiness_score,
        "audited_urls": len(page_results),
        "schema_counts": schema_counts,
        "llms_txt_parity_ok": report["llms_parity"]["llms_txt_parity_ok"],
        "llms_full_txt_parity_ok": report["llms_parity"]["llms_full_txt_parity_ok"],
        "mixed_content_maps_google_count": len(mixed_maps_pages),
        "duplicate_jquery_count": len(dup_jquery_pages),
        "pages_with_blocking_scripts": len(blocking_pages),
        "total_blocking_scripts": total_blocking_scripts,
        "images_total": total_images,
        "images_missing_dimensions": total_missing_dims,
        "images_missing_lazy": total_missing_lazy,
        "page1_zero_ctr_query_alerts": p1_alerts["total_query_alerts"],
        "page1_zero_ctr_page_alerts": p1_alerts["total_page_alerts"],
        "page1_zero_ctr_sgp_alerts": p1_alerts["total_singapore_alerts"],
        "page1_zero_ctr_ind_alerts": p1_alerts["total_india_alerts"],
    }
    log(
        "geo_audit: done, score=%.1f/100, maps_http=%d, dup_jquery=%d, blocking=%d scripts/%d pages, missing_dims=%d, p1_zero_ctr=%d"
        % (
            readiness_score,
            len(mixed_maps_pages),
            len(dup_jquery_pages),
            total_blocking_scripts,
            len(blocking_pages),
            total_missing_dims,
            p1_alerts["total_alerts"],
        )
    )
    return report


def write_live_status_md(summary):
    s, e = active_cycle_window()
    today_act = summary.get("daily_action") or {}
    act_title = today_act.get("title") or today_act.get("action_id") or "Scheduled via Cron"
    act_status = today_act.get("status", "pending")
    geo = summary.get("geo_audit") or {}
    geo_score = geo.get("readiness_score", "N/A")
    llms_ok = f"llms.txt={geo.get('llms_txt_parity_ok', 'N/A')}, llms-full.txt={geo.get('llms_full_txt_parity_ok', 'N/A')}"
    md = [
        "# Framez Live Cycle Status (Auto-Updated by Cron)",
        "",
        f"* **Active Monthly Cycle:** `{s}` to `{e}`",
        f"* **Last Automated Run:** `{summary.get('generated_at')}`",
        f"* **Today's Daily Action ({today_sgt()}):** `{act_status}` ({act_title})",
        f"* **Sitemap URLs Live:** `{(summary.get('sitemap') or {}).get('urls')}` (Broken: `{(summary.get('audit') or {}).get('broken')}`)",
        f"* **GEO/AEO Readiness Score:** `{geo_score}/100` ({llms_ok})",
        f"* **GEO/AEO Technical Alerts:** `http://maps.google.com` pages=`{geo.get('mixed_content_maps_google_count', 'N/A')}`, duplicate jQuery pages=`{geo.get('duplicate_jquery_count', 'N/A')}`, blocking scripts=`{geo.get('total_blocking_scripts', 'N/A')}` across `{geo.get('pages_with_blocking_scripts', 'N/A')}` pages, missing img dims=`{geo.get('images_missing_dimensions', 'N/A')}`, missing lazy=`{geo.get('images_missing_lazy', 'N/A')}`",
        f"* **Page-1 Zero-CTR Alerts:** `{geo.get('page1_zero_ctr_query_alerts', 'N/A')}` queries (`sgp={geo.get('page1_zero_ctr_sgp_alerts', 'N/A')}`, `ind={geo.get('page1_zero_ctr_ind_alerts', 'N/A')}`), `{geo.get('page1_zero_ctr_page_alerts', 'N/A')}` pages",
        f"* **GSC API Sync (`sc-domain:framez.sg`):** `{summary.get('gsc')}`",
        f"* **GA4 API Sync (`547082278`):** `{summary.get('ga4')}`",
        f"* **DeepSeek v4.1 Flash Daily Engine (OpenDesign):** `{summary.get('deepseek', 'N/A')}` (Latency: `{summary.get('deepseek_latency', 'N/A')}s`)",
        f"* **Verified Form Leads (`leads_log.json`):** `{(summary.get('leads') or {}).get('verified_total')}`",
        f"* **Blocked Spam Bots (`leads_spam_log.json`):** `{(summary.get('leads') or {}).get('spam_blocked_total')}`",
        f"* **GitHub Repository:** https://github.com/princejain756/framezseo",
        f"* **Active Cycle Ledger:** `reports/cycle-{s}-to-{e}-ledger.jsonl`",
        "",
    ]
    (JOB / "LIVE_STATUS.md").write_text("\n".join(md))


def maybe_refresh_cycle_report():
    for gen in (JOB / "scripts" / "generate_nov_dec_report.py", JOB / "generate_nov_dec_report.py"):
        if gen.exists():
            try:
                subprocess.run([sys.executable, str(gen)], check=True, timeout=60)
                log("report: refreshed FRAMEZ_NOVEMBER_DECEMBER_2026_SEO_AEO_GEO_REPORT.md")
                return
            except Exception as e:
                log(f"report: warning ({e})")
                return


def git_sync_to_github(summary):
    """Commits and pushes daily SEO, GEO and ledger updates to GitHub."""
    git_dir = JOB / ".git"
    if not git_dir.exists():
        log("git: no .git repository found in job folder, skipping git sync")
        return {"status": "skipped", "reason": "no_git_repo"}

    try:
        st = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(JOB),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30,
        )
        if not st.stdout.strip():
            log("git: working tree clean, nothing to commit")
            return {"status": "clean"}

        subprocess.run(
            ["git", "add", "reports/", "docs/", "LIVE_STATUS.md", "MEMORY.md", "scripts/"],
            cwd=str(JOB),
            check=True,
            timeout=30,
        )

        today_str = datetime.date.today().isoformat()
        act = summary.get("daily_action", {})
        if isinstance(act, dict):
            act_note = act.get("target_page") or act.get("status") or "daily micro-action"
        else:
            act_note = "daily updates"
        commit_msg = _strip_dashes(f"SEO daily automated sync: {today_str} ({act_note})")

        commit_env = os.environ.copy()
        commit_env["GIT_AUTHOR_NAME"] = "Prince Jain"
        commit_env["GIT_AUTHOR_EMAIL"] = "princejain756@gmail.com"
        commit_env["GIT_COMMITTER_NAME"] = "Prince Jain"
        commit_env["GIT_COMMITTER_EMAIL"] = "princejain756@gmail.com"

        commit = subprocess.run(
            [
                "git",
                "-c", "user.name=Prince Jain",
                "-c", "user.email=princejain756@gmail.com",
                "commit",
                "--author=Prince Jain <princejain756@gmail.com>",
                "-m", commit_msg,
            ],
            cwd=str(JOB),
            env=commit_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30,
        )
        log(f"git commit: {commit.stdout.strip() or commit.stderr.strip()}")
        if commit.returncode != 0:
            return {"status": "skipped", "detail": commit.stdout.strip() or commit.stderr.strip()}

        push = subprocess.run(
            ["git", "push", "origin", "main"],
            cwd=str(JOB),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=60,
        )
        log(f"git push: {push.stdout.strip() or 'ok'}")
        return {"status": "pushed", "commit": commit_msg}
    except Exception as e:
        log(f"git: warning during sync ({e})")
        return {"status": "error", "error": str(e)}


def run_all():
    cfg = config()
    state = load_json(STATE_PATH, {"hashes": {}, "deployed_waves": {}})

    # 1. Release any scheduled major wave due today
    waves = release_due_waves(cfg, state)

    # 2. Execute scheduled daily micro-action if applicable for today
    daily_act = None
    changed_daily = []
    try:
        from daily_actions import execute_daily_action_for_date
        daily_act = execute_daily_action_for_date(today_sgt(), remote_get, remote_put, log)
        if daily_act.get("status") == "ok" and daily_act.get("target_url"):
            changed_daily.append(daily_act["target_url"])
        state["last_daily_action"] = daily_act
    except Exception as e:
        log(f"daily_action: warning ({e})")
        daily_act = {"status": "error", "error": str(e)}

    # 3. Reconcile sitemap, crawl audit, and llms.txt / llms-full.txt parity
    smap = sitemap_sync(cfg, state)
    rep = audit(cfg, state)
    try:
        llms_res = sync_llms_files(cfg, state, upload=True)
    except Exception as e:
        log(f"llms: warning ({e})")
        llms_res = {"status": "error", "error": str(e)}

    changed = list(set(rep["changed_urls"] + smap.get("added", []) + changed_daily))
    idx = indexnow(cfg, state, changed)
    gsc = gsc_snapshot(cfg, state)
    ga4 = ga4_snapshot(cfg, state)
    leads = leads_snapshot(state)

    # 4. Run full GEO/AEO readiness & technical hygiene audit with fresh GSC & llms state
    try:
        geo_aeo_audit(cfg, state)
    except Exception as e:
        log(f"geo_audit: warning ({e})")

    # 5. OpenDesign DeepSeek v4.1 Flash (Normal) Daily Intelligence
    try:
        from deepseek_daily_seo import run_daily_deepseek_task
        dres = run_daily_deepseek_task(JOB)
        state["last_deepseek_run"] = dres
    except Exception as e:
        log(f"deepseek: warning ({e})")
        dres = {"status": "error", "error": str(e)}

    state["last_run_at"] = now_utc().isoformat()
    save_json(STATE_PATH, state)

    summary = {
        "generated_at": state["last_run_at"],
        "waves_deployed_this_run": [w["url"] for w in waves],
        "daily_action": daily_act,
        "audit": state.get("last_audit_summary"),
        "geo_audit": state.get("last_geo_audit_summary"),
        "llms_sync": llms_res,
        "sitemap": smap,
        "indexnow": idx,
        "gsc": gsc.get("status"),
        "ga4": ga4.get("status"),
        "deepseek": dres.get("status"),
        "deepseek_latency": dres.get("latency_seconds"),
        "deepseek_summary": dres.get("executive_summary"),
        "leads": {
            "verified_total": leads.get("verified_leads_total"),
            "spam_blocked_total": leads.get("spam_blocked_total"),
        },
    }
    save_json(REPORT_DIR / "latest-run.json", summary)
    append_ledger({"event": "daily_cron_run", **summary})
    maybe_freeze_monthly_boundary(summary, gsc, ga4, leads)
    write_live_status_md(summary)
    maybe_refresh_cycle_report()
    git_res = git_sync_to_github(summary)
    summary["git_sync"] = git_res
    save_json(REPORT_DIR / "latest-run.json", summary)
    log("done")
    return summary


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    cmd = argv[1]
    cfg = config()
    state = load_json(STATE_PATH, {"hashes": {}, "deployed_waves": {}})

    if cmd == "status":
        print(json.dumps({
            "last_run_at": state.get("last_run_at"),
            "deployed_waves": list((state.get("deployed_waves") or {}).keys()),
            "last_daily_action": state.get("last_daily_action"),
            "audit": state.get("last_audit_summary"),
            "geo_audit": state.get("last_geo_audit_summary"),
            "llms_sync": state.get("last_llms_sync"),
            "sitemap": state.get("last_sitemap_summary"),
            "indexnow": state.get("last_indexnow"),
            "gsc": state.get("gsc_status"),
            "ga4": state.get("ga4_status"),
            "deepseek": state.get("last_deepseek_run"),
            "leads": state.get("last_leads_snapshot"),
        }, indent=2))
        return 0

    with open(LOCK_PATH, "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            log("another run is active, exiting")
            return 0

        if cmd == "audit":
            audit(cfg, state)
            save_json(STATE_PATH, state)
            print(json.dumps(state.get("last_audit_summary"), indent=2))
        elif cmd == "geo_audit":
            geo_aeo_audit(cfg, state)
            save_json(STATE_PATH, state)
            print(json.dumps(state.get("last_geo_audit_summary"), indent=2))
        elif cmd == "sync_llms":
            res = sync_llms_files(cfg, state, upload=True)
            save_json(STATE_PATH, state)
            print(json.dumps(res, indent=2))
        elif cmd == "sitemap":
            s = sitemap_sync(cfg, state)
            save_json(STATE_PATH, state)
            print(json.dumps(s, indent=2))
        elif cmd == "indexnow":
            rep = load_json(REPORT_DIR / "latest-audit.json", {})
            print(json.dumps(indexnow(cfg, state, rep.get("changed_urls", [])), indent=2))
            save_json(STATE_PATH, state)
        elif cmd == "gsc":
            print(json.dumps(gsc_snapshot(cfg, state), indent=2))
            save_json(STATE_PATH, state)
        elif cmd == "ga4":
            print(json.dumps(ga4_snapshot(cfg, state), indent=2))
            save_json(STATE_PATH, state)
        elif cmd == "leads":
            print(json.dumps(leads_snapshot(state), indent=2))
            save_json(STATE_PATH, state)
        elif cmd == "deepseek":
            from deepseek_daily_seo import run_daily_deepseek_task
            res = run_daily_deepseek_task(JOB)
            state["last_deepseek_run"] = res
            save_json(STATE_PATH, state)
            print(json.dumps(res, indent=2))
        elif cmd == "daily_action":
            from daily_actions import execute_daily_action_for_date
            res = execute_daily_action_for_date(today_sgt(), remote_get, remote_put, log)
            state["last_daily_action"] = res
            save_json(STATE_PATH, state)
            print(json.dumps(res, indent=2))
        elif cmd == "release_due":
            res = release_due_waves(cfg, state)
            save_json(STATE_PATH, state)
            print(json.dumps(res, indent=2))
        elif cmd == "git_sync":
            last_run = load_json(REPORT_DIR / "latest-run.json", {})
            res = git_sync_to_github(last_run)
            print(json.dumps(res, indent=2))
        elif cmd == "all":
            print(json.dumps(run_all(), indent=2))
        else:
            print("unknown command: %s" % cmd)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
