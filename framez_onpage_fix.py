#!/usr/bin/env python3
"""One-time on-page technical SEO fixes for framez.sg.

Repairs the issues found by the audit:
  * missing meta robots on handbook/service pages
  * missing Open Graph / Twitter Card tags
  * duplicate alt attributes (invalid HTML) on event-planner.php
  * empty alt text on the shared "get to know us" image

Follows Framez/HOW_TO_MAKE_WEBSITE_CHANGES.md: download, modify, upload,
verify. Originals are backed up under seo-jobs/framez/backups/onpage-<ts>/.

Usage:
  framez_onpage_fix.py            # dry run, shows what would change
  framez_onpage_fix.py --apply    # back up, upload, verify live
"""

import datetime
import json
import pathlib
import re
import sys
import urllib.parse
import urllib.request

BASE = pathlib.Path("/root/websites/seogeoopt")
JOB = BASE / "seo-jobs" / "framez"
BACKUP_DIR = JOB / "backups"
REMOTE_DIR = "public_html"
ROBOTS = '<meta name="robots" content="index, follow, max-image-preview:large, max-snippet:-1, max-video-preview:-1">'
ALT_TEXT = "Framez events team planning a corporate event in Bangalore and Singapore"

ROBOTS_PAGES = [
    "corporate-event-planning-handbook-2027.php",
    "experiential-brand-activations-framework.php",
    "executive-offsite-retreat-blueprint.php",
    "b2b-event-agency-rfp-evaluation-guide.php",
    "corporate-event-trends-singapore.php",
    "experiential-marketing-brand-activations.php",
]
TWITTER_PAGES = [
    "event-management-company-in-india.php",
    "event-planner.php",
    "corporate-event-trends-singapore.php",
    "Framez-Public-Statement-on-Health-and-Safety-Commitment.php",
]
OG_PAGES = [
    "corporate-event-trends-singapore.php",
]
OG_FILL_PAGES = ["Framez-Public-Statement-on-Health-and-Safety-Commitment.php"]
ALT_PAGES = [
    "about-us.php",
    "blog.php",
    "corporate-event-management-company.php",
    "event-marketing-services.php",
]
DUP_ALT_PAGES = ["event-planner.php"]
CANONICAL_PAGES = {
    "Framez-Public-Statement-on-Health-and-Safety-Commitment.php":
        "Framez's public statement on health, safety and ISO-certified event delivery standards across Singapore and India.",
}
META_OVERRIDES = {
    "about-us.php": {
        "description": "Framez Events &amp; Productions is a corporate event management and production agency in Bangalore and Singapore for conferences, launches and activations.",
    },
    "corporate-event-management-company.php": {
        "title": "Event Management Company Bangalore &amp; Singapore | Framez",
    },
    "get-in-touch.php": {
        "title": "Contact Framez | Corporate Events Bangalore &amp; Singapore",
    },
    "annual-day-and-awards-night-planning-guide.php": {
        "description": "Plan a company annual day or awards night: recognition goals, award approvals, rehearsal scheduling, inclusive guest planning and a sample run-of-show.",
    },
    "singapore-corporate-event-planning-checklist.php": {
        "description": "A practical checklist for corporate events in Singapore: venue access, production scheduling, transport, PDPA data, licences, wet-weather plans and suppliers.",
    },
    "corporate-event-planning-handbook-2027.php": {
        "title": "Corporate Event Planning Handbook 2027: Budget, Venue &amp; ROI",
        "description": "Enterprise corporate event planning handbook for Singapore and APAC: line-item budgeting, venue sourcing matrices, AV standards and ROI attribution.",
    },
    "experiential-brand-activations-framework.php": {
        "title": "Experiential Brand Activation Frameworks | Framez",
        "description": "Five proven experiential activation frameworks. Compare ROI, dwell time and lead capture against traditional digital ads in Singapore and India.",
    },
    "executive-offsite-retreat-blueprint.php": {
        "title": "Executive Offsite Blueprint | Luxury Corporate Retreats",
        "description": "Plan luxury executive offsites in Bangalore, Coorg and Singapore: venue selection, security, agenda design and team building.",
    },
    "b2b-event-agency-rfp-evaluation-guide.php": {
        "title": "B2B Event Agency RFP &amp; Evaluation Guide | Framez",
        "description": "For procurement teams: how to draft an event RFP and score B2B event agencies in Singapore and India, with rubrics and contract checks.",
    },
    "corporate-product-launch-event-architecture.php": {
        "title": "Corporate Product Launch Event Architecture | Framez",
        "description": "Enterprise product launch architecture: reveal engineering, broadcast standards, press operations and pipeline capture in Bangalore and Singapore.",
    },
    "high-security-cxo-board-summit-protocol.php": {
        "title": "High-Security CXO &amp; Board Summit Protocol | Framez",
        "description": "Board summit security: TSCM sweeps, confidentiality tiers, close protection and executive duty-of-care for CXO events in Singapore and Bangalore.",
    },
    "festive-corporate-gala-diwali-celebrations.php": {
        "title": "Corporate Diwali Gala &amp; Festive Events | Framez",
        "description": "Corporate Diwali gala production: authentic festive design, inclusive programming, decor fire safety and budget benchmarks in Bangalore and Singapore.",
    },
    "corporate-family-day-carnival-safety-logistics.php": {
        "title": "Corporate Family Day Carnival Safety &amp; Logistics | Framez",
        "description": "Family Day carnival safety and logistics: child-safe zones, vendor vetting, crowd engineering and medical planning in Bangalore and Singapore.",
    },
    "corporate-event-trends-singapore.php": {
        "title": "Corporate Event Trends in Singapore | MICE &amp; Experiential",
    },
    "Framez-Public-Statement-on-Health-and-Safety-Commitment.php": {
        "description": "Framez public statement on health, safety and ISO-certified event delivery standards across Singapore and India.",
    },
}


def env_file():
    values = {}
    for line in (BASE / ".env").read_text().splitlines():
        m = re.match(r"^([A-Z0-9_]+)=(.*)$", line.strip())
        if m:
            values[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    return values


ENV = env_file()
HOST = ENV.get("CPANEL_HOST", "https://framez.sg:2083").rstrip("/")
AUTH = "cpanel %s:%s" % (ENV.get("CPANEL_USERNAME", ""), ENV.get("CPANEL_API_TOKEN", ""))


def cpanel(function, params, method="GET"):
    url = HOST + "/execute/Fileman/" + function
    headers = {"Authorization": AUTH}
    if method == "GET":
        url += "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers=headers)
    else:
        headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=json.dumps(params).encode(), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=90) as resp:
        return json.loads(resp.read().decode())


def get_file(name):
    return cpanel("get_file_content", {"dir": REMOTE_DIR, "file": name})["data"]["content"]


def put_file(name, content):
    res = cpanel("save_file_content", {"dir": REMOTE_DIR, "file": name, "content": content}, method="POST")
    return res.get("status") == 1


def one(pattern, html):
    m = re.search(pattern, html, re.S | re.I)
    return m.group(1).strip() if m else ""


def ensure_robots(html, changes):
    if re.search(r'name=["\']robots["\']', html, re.I):
        return html
    anchor = re.search(r'<meta\s+http-equiv=["\']x-ua-compatible["\'][^>]*>', html, re.I)
    if not anchor:
        anchor = re.search(r'<meta\s+charset=["\'][^"\']+["\'][^>]*>', html, re.I)
    if not anchor:
        raise RuntimeError("no <head> anchor found")
    insert = anchor.group(0) + "\n    " + ROBOTS
    changes.append("insert meta robots")
    return html[: anchor.start()] + insert + html[anchor.end():]


def ensure_twitter(html, changes):
    if re.search(r'name=["\']twitter:card["\']', html, re.I):
        return html
    og_url = re.search(r'<meta\s+property=["\']og:url["\'][^>]*>', html, re.I)
    og_site = re.search(r'<meta\s+property=["\']og:site_name["\'][^>]*>', html, re.I)
    anchor = og_site or og_url
    tag = '<meta name="twitter:card" content="summary_large_image">'
    if anchor:
        changes.append("insert twitter:card after og tags")
        return html[: anchor.end()] + "\n\t\t" + tag + html[anchor.end():]
    canonical = re.search(r'<link\s+rel=["\']canonical["\'][^>]*>', html, re.I)
    if canonical:
        changes.append("insert twitter:card after canonical")
        return html[: canonical.end()] + "\n  " + tag + html[canonical.end():]
    raise RuntimeError("no anchor for twitter card")


def ensure_og(html, changes):
    if re.search(r'property=["\']og:title["\']', html, re.I):
        return html
    desc = ""
    m = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content="([^"]*)"', html, re.I | re.S)
    if not m:
        m = re.search(r"<meta[^>]+name=[\"']description[\"'][^>]+content='([^']*)'", html, re.I | re.S)
    if m:
        desc = m.group(1).strip()
    canonical = one(r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']*)', html)
    title = one(r"<title[^>]*>(.*?)</title>", html)
    block = "\n".join([
        '<meta property="og:locale" content="en_SG" />',
        '<meta property="og:type" content="website" />',
        '<meta property="og:title" content="%s" />' % title,
        '<meta property="og:description" content="%s" />' % desc,
        '<meta property="og:url" content="%s" />' % canonical,
        '<meta property="og:site_name" content="Framez" />',
    ])
    anchor = re.search(r'<link\s+rel=["\']canonical["\'][^>]*>', html, re.I)
    if not anchor:
        raise RuntimeError("no canonical anchor for og block")
    changes.append("insert Open Graph block")
    return html[: anchor.end()] + "\n  " + block + html[anchor.end():]


def fix_empty_alt(html, changes):
    target = 'src="assets/images/get_to_know_us-1-1536x1024.webp" alt=""'
    if target not in html:
        return html
    changes.append("fill empty alt text on team image")
    return html.replace(target, 'src="assets/images/get_to_know_us-1-1536x1024.webp" alt="%s"' % ALT_TEXT)


def fix_duplicate_alt(html, changes):
    pattern = re.compile(r'(class="image-fluid"\s+)alt=""\s*')
    count = len(pattern.findall(html))
    if not count:
        return html
    changes.append("remove %d duplicate alt attribute(s)" % count)
    return pattern.sub(r"\1", html)


def fix_empty_canonical(html, changes, description):
    if re.search(r'<link\s+rel=["\']canonical["\']\s+href=["\']\s*["\']', html, re.I):
        html = re.sub(r'<link\s+rel=["\']canonical["\']\s+href=["\']\s*["\'][^>]*>',
                      '<link rel="canonical" href="https://framez.sg/Framez-Public-Statement-on-Health-and-Safety-Commitment" />',
                      html, count=1, flags=re.I)
        changes.append("fill empty canonical")
    if re.search(r'<meta\s+name=["\']description["\']\s+content=["\']\s*["\']', html, re.I):
        html = re.sub(r'<meta\s+name=["\']description["\']\s+content=["\']\s*["\'][^>]*>',
                      '<meta name="description" content="%s" />' % description,
                      html, count=1, flags=re.I)
        changes.append("fill empty meta description")
    return html


def fill_empty_og(html, changes):
    title = one(r"<title[^>]*>(.*?)</title>", html)
    desc = ""
    m = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content="([^"]*)"', html, re.I | re.S)
    if m:
        desc = m.group(1).strip()
    canonical = one(r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']*)', html)
    pairs = [
        ("og:title", title),
        ("og:description", desc),
        ("og:url", canonical),
        ("og:image", "https://framez.sg/assets/img/frameznewlogo.png"),
    ]
    for prop, value in pairs:
        if not value:
            continue
        pattern = re.compile(r'<meta\s+property=["\']' + re.escape(prop)
                             + r'["\'][^>]*content=["\']\s*["\'][^>]*>', re.I)
        new_tag = '<meta property="%s" content="%s">' % (
            prop, value.replace("&", "&amp;").replace('"', "&quot;"))
        html, n = pattern.subn(new_tag, html, count=1)
        if n:
            changes.append("fill empty %s" % prop)
    return html


def apply_meta(html, changes, meta):
    title = meta.get("title")
    desc = meta.get("description")
    if title:
        new_tag = "<title>%s</title>" % title
        html, n = re.subn(r"<title[^>]*>.*?</title>", new_tag, html, count=1, flags=re.S | re.I)
        if n:
            changes.append("rewrite title (%d chars)" % len(re.sub(r"&amp;", "&", title)))
    if desc:
        new_tag = '<meta name="description" content="%s" />' % desc
        html, n = re.subn(r'<meta[^>]+name=["\']description["\'][^>]*>', new_tag, html, count=1, flags=re.I)
        if n:
            changes.append("rewrite description (%d chars)" % len(re.sub(r"&amp;", "&", desc)))
    return html


def transform(name, html):
    changes = []
    if name in ROBOTS_PAGES:
        html = ensure_robots(html, changes)
    if name in META_OVERRIDES:
        html = apply_meta(html, changes, META_OVERRIDES[name])
    if name in OG_PAGES:
        html = ensure_og(html, changes)
    if name in OG_FILL_PAGES:
        html = fill_empty_og(html, changes)
    if name in TWITTER_PAGES:
        html = ensure_twitter(html, changes)
    if name in ALT_PAGES:
        html = fix_empty_alt(html, changes)
    if name in DUP_ALT_PAGES:
        html = fix_duplicate_alt(html, changes)
    if name in CANONICAL_PAGES:
        html = fix_empty_canonical(html, changes, CANONICAL_PAGES[name])
    return html, changes


def verify_live(name):
    url = "https://framez.sg/" + name[:-4] if name.endswith(".php") else "https://framez.sg/"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 verify"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.status, resp.read().decode("utf-8", "ignore")


def main(argv):
    apply = "--apply" in argv
    files = sorted(set(ROBOTS_PAGES + TWITTER_PAGES + OG_PAGES + OG_FILL_PAGES + ALT_PAGES
                       + DUP_ALT_PAGES + list(CANONICAL_PAGES) + list(META_OVERRIDES)))
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_dir = BACKUP_DIR / ("onpage-%s" % stamp)
    backup_dir.mkdir(parents=True, exist_ok=True)
    total = 0

    for name in files:
        html = get_file(name)
        (backup_dir / name).write_text(html)
        new_html, changes = transform(name, html)
        if not changes:
            print("SKIP %-52s no changes needed" % name)
            continue
        total += len(changes)
        print("%-52s %s" % (name, "; ".join(changes)))
        if apply and new_html != html:
            if not put_file(name, new_html):
                print("  FAILED to upload %s" % name)
                continue
            status, live = verify_live(name)
            ok = status == 200
            if name in ROBOTS_PAGES:
                ok = ok and bool(re.search(r'name=["\']robots["\']', live, re.I))
            if name in TWITTER_PAGES:
                ok = ok and bool(re.search(r'name=["\']twitter:card["\']', live, re.I))
            if name in OG_PAGES:
                ok = ok and bool(re.search(r'property=["\']og:title["\']', live, re.I))
            if name in DUP_ALT_PAGES:
                ok = ok and len(re.findall(r"\balt\s*=", live)) == len(re.findall(r"<img\b", live))
            if name in CANONICAL_PAGES:
                ok = ok and bool(re.search(r'rel=["\']canonical["\'][^>]+href=["\']https://framez\.sg/', live, re.I))
            if name in OG_FILL_PAGES:
                ok = ok and bool(re.search(r'property=["\']og:title["\']\s+content=["\'][^"\']+', live, re.I))
                ok = ok and bool(re.search(r'property=["\']og:url["\']\s+content=["\'][^"\']+', live, re.I))
            print("  live HTTP %s verification: %s" % (status, "PASS" if ok else "CHECK"))

    if apply:
        (backup_dir / "MANIFEST.json").write_text(json.dumps({
            "applied_at": stamp, "files": files, "changes": total,
        }, indent=2))
        print("\nBackup: %s" % backup_dir)
    else:
        print("\nDry run: %d change groups. Re-run with --apply to deploy." % total)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
