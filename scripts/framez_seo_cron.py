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

    ld_types, ld_invalid = [], 0
    for block in re.findall(r'application/ld\+json[^>]*>(.*?)</script>', html, re.S):
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
                else:
                    ld_invalid += 1
        except Exception:
            ld_invalid += 1

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

        for lf in ("llms.txt", "llms-full.txt"):
            lcur = remote_get("public_html", lf) or ""
            if lcur:
                (wbackup / lf).write_text(lcur)
                if slug not in lcur:
                    line = f"- [{spec['h1']}](https://framez.sg/{slug})\n"
                    touched_files[lf] = lcur.rstrip() + "\n" + line

        # 3. Upload and SHA-256 verify each file
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


def gsc_query(site_enc, headers, start_date, end_date, dimensions=None, row_limit=25):
    payload = {"startDate": start_date, "endDate": end_date, "rowLimit": row_limit}
    if dimensions:
        payload["dimensions"] = dimensions
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

    out["window_7d"] = {"start": start_7d, "end": end_iso, "totals": gsc_query(site_enc, headers, start_7d, end_iso)}
    out["window_28d"] = {
        "start": start_28d,
        "end": end_iso,
        "totals": gsc_query(site_enc, headers, start_28d, end_iso),
        "countries": gsc_query(site_enc, headers, start_28d, end_iso, ["country"], 15),
        "top_queries": gsc_query(site_enc, headers, start_28d, end_iso, ["query"], 30),
        "top_pages": gsc_query(site_enc, headers, start_28d, end_iso, ["page"], 30),
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


def write_live_status_md(summary):
    s, e = active_cycle_window()
    today_act = summary.get("daily_action") or {}
    act_title = today_act.get("title") or today_act.get("action_id") or "Scheduled via Cron"
    act_status = today_act.get("status", "pending")
    md = [
        "# Framez Live Cycle Status (Auto-Updated by Cron)",
        "",
        f"* **Active Monthly Cycle:** `{s}` to `{e}`",
        f"* **Last Automated Run:** `{summary.get('generated_at')}`",
        f"* **Today's Daily Action ({today_sgt()}):** `{act_status}` ({act_title})",
        f"* **Sitemap URLs Live:** `{(summary.get('sitemap') or {}).get('urls')}` (Broken: `{(summary.get('audit') or {}).get('broken')}`)",
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
        commit_msg = f"SEO daily automated sync: {today_str} ({act_note})"

        commit_env = os.environ.copy()
        commit_env["GIT_AUTHOR_NAME"] = "Prince Jain"
        commit_env["GIT_AUTHOR_EMAIL"] = "princejain756@gmail.com"
        commit_env["GIT_COMMITTER_NAME"] = "Prince Jain"
        commit_env["GIT_COMMITTER_EMAIL"] = "princejain756@gmail.com"

        commit = subprocess.run(
            ["git", "commit", "-m", commit_msg],
            cwd=str(JOB),
            env=commit_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30,
        )
        log(f"git commit: {commit.stdout.strip()}")

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

    # 3. Reconcile sitemap and crawl audit
    smap = sitemap_sync(cfg, state)
    rep = audit(cfg, state)
    changed = list(set(rep["changed_urls"] + smap.get("added", []) + changed_daily))
    idx = indexnow(cfg, state, changed)
    gsc = gsc_snapshot(cfg, state)
    ga4 = ga4_snapshot(cfg, state)
    leads = leads_snapshot(state)

    # 4. OpenDesign DeepSeek v4.1 Flash (Normal) Daily Intelligence
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
