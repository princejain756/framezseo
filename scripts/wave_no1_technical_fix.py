#!/usr/bin/env python3
"""No.1 Technical SEO, GEO, AEO & CWV Overhaul Deployment for Framez.sg.

Standalone, idempotent deployment script covering 6 technical & commercial fixes:
  1. Legacy JS/CSS bloat & mixed-content removal across core .php pages
  2. header.php cleanup (<meta charset> outside <header>) & upgraded Organization JSON-LD
  3. index.html brand #1 & CWV upgrade (hreflang fix, title/schema, decoding="async")
  4. Commercial title/H1 cannibalization & Page-1 zero-CTR rescue + book-a-demo expansion
  5. llms.txt & llms-full.txt 29-URL parity, dual-HQ NAP, ISO proof & disambiguation
  6. .htaccess mod_expires/mod_deflate CWV caching check (preserving PHP handler & 301/security)

Safety:
  - Default mode (--dry-run) fetches live/cached files read-only via SSH/local cache,
    applies & validates all transforms locally, writes dry-run artifacts & diffs, and
    never uploads to cPanel.
  - --apply mode runs on 72.61.173.127 (where /root/websites/seogeoopt/.env lives),
    creates backups/no1-overhaul-2026-11-21/ with SHA-256 MANIFEST.json before upload,
    uploads via cPanel UAPI, verifies SHA-256 read-back and live HTTP 200/301, pushes
    changed canonical URLs to IndexNow, and logs an immutable cycle ledger receipt.
"""

import datetime
import difflib
import hashlib
import html as html_lib
import json
import pathlib
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
JOB = SCRIPT_DIR.parent if SCRIPT_DIR.name == "scripts" else SCRIPT_DIR
BASE = JOB.parent.parent if (JOB.parent and JOB.parent.name == "seo-jobs") else pathlib.Path("/root/websites/seogeoopt")
BACKUP_ROOT = JOB / "backups" / "no1-overhaul-2026-11-21"
REPORT_DIR = JOB / "reports"
LEDGER_PATH = REPORT_DIR / "cycle-2026-11-15-to-2026-12-15-ledger.jsonl"

SSH_HOST = "root@72.61.173.127"
SERVER_SCRIPT_DIR = "/root/websites/seogeoopt/seo-jobs/framez/scripts"
GA4_ID = "G-XDPHV6MX44"
TURNSTILE_SITEKEY = "0x4AAAAAAExBdPWHAqYTWVlc"

BANNED_BUZZWORDS_RE = re.compile(
    r"\b(leverage|utilize|facilitate|streamline|robust|seamless(?:ly)?|delve|navigat(?:e|ing)|"
    r"unlock|harness|foster(?:ing)?|cultivate|landscape|ecosystem|journey|game-changer|deep dive)\b",
    re.I,
)

LEGACY_CLEANUP_FILES = [
    "event-management-company-in-bangalore.php",
    "corporate-event-management-company.php",
    "our-events-and-services.php",
    "about-us.php",
    "clientele.php",
    "blog.php",
    "book-a-demo.php",
    "get-in-touch.php",
    "experiential-marketing-brand-activations.php",
    "Framez-Public-Statement-on-Health-and-Safety-Commitment.php",
    "thank-you.php",
]

PAGE1_RESCUE_FILES = [
    "corporate-product-launch-event-architecture.php",
    "corporate-event-budget-planning-guide.php",
    "annual-day-and-awards-night-planning-guide.php",
    "event-planner.php",
]

ALL_TARGET_FILES = [
    "header.php",
    "index.html",
    ".htaccess",
    "llms.txt",
    "llms-full.txt",
    "event-management-company-in-singapore.php",
    *LEGACY_CLEANUP_FILES,
    *PAGE1_RESCUE_FILES,
]

SITEMAP_29_URLS = [
    ("Home", "https://framez.sg/", "Main corporate overview, services, regional hubs, and direct inquiry form"),
    ("Corporate Event Management", "https://framez.sg/corporate-event-management-company", "End-to-end corporate event management, staging, and AV production"),
    ("Event Management Company in Singapore", "https://framez.sg/event-management-company-in-singapore", "Singapore corporate events, APAC conferences, D&D galas, and venue operations"),
    ("Event Management Company in Bangalore", "https://framez.sg/event-management-company-in-bangalore", "Bengaluru HQ corporate event production across Koramangala, Whitefield, and ORR"),
    ("Event Management Company in India", "https://framez.sg/event-management-company-in-india", "Pan-India corporate event execution, multi-city roadshows, and summits"),
    ("Conference & MICE Event Management", "https://framez.sg/conference-and-mice-event-management", "B2B conferences, plenary staging, breakout tracks, and MICE logistics"),
    ("Events and Services", "https://framez.sg/our-events-and-services", "Full corporate service catalogue covering MICE, launches, and activations"),
    ("Event Marketing Services", "https://framez.sg/event-marketing-services", "Pre-event registration funnels, trade booth traffic, and CRM lead handoff"),
    ("Event Planner", "https://framez.sg/event-planner", "Turnkey B2B corporate event planning, venue sourcing, and show-calling"),
    ("Experiential Marketing & Brand Activations", "https://framez.sg/experiential-marketing-brand-activations", "Interactive brand activations, pop-ups, and roadshow builds"),
    ("About Us", "https://framez.sg/about-us", "Company background, production experience, and delivery team"),
    ("Clientele", "https://framez.sg/clientele", "Enterprise client portfolio across technology, BFSI, and APAC conventions"),
    ("Blog & Guides", "https://framez.sg/blog", "Index of corporate event planning guides, handbooks, and checklists"),
    ("Contact / Get in Touch", "https://framez.sg/get-in-touch", "Direct corporate event inquiry form and office contact details"),
    ("Book a Demo / Brief Consultation", "https://framez.sg/book-a-demo", "Schedule a consultation and review the enterprise RFP scope checklist"),
    ("Health & Safety Commitment", "https://framez.sg/Framez-Public-Statement-on-Health-and-Safety-Commitment", "Public statement on health, safety, and ISO-certified delivery standards"),
    ("Corporate Event Budget Planning Guide", "https://framez.sg/corporate-event-budget-planning-guide", "Cost categories, fixed vs per-guest pricing, change orders, and quote checklist"),
    ("Annual Day & Awards Night Planning Guide", "https://framez.sg/annual-day-and-awards-night-planning-guide", "Recognition goals, award approvals, run-of-show, and inclusive guest planning"),
    ("Corporate Event ROI Measurement Guide", "https://framez.sg/corporate-event-roi-measurement-guide", "Attendance denominators, lead quality tiers, attribution rules, and closeout"),
    ("Singapore Corporate Event Planning Checklist", "https://framez.sg/singapore-corporate-event-planning-checklist", "Singapore venue access, PDPA attendee data, licences, and weather backups"),
    ("2027 Corporate Event Planning Handbook", "https://framez.sg/corporate-event-planning-handbook-2027", "APAC budgeting, venue sourcing matrices, AV specs, and ROI benchmarks"),
    ("Experiential Brand Activations Framework", "https://framez.sg/experiential-brand-activations-framework", "Five experiential campaign models and engagement measurement benchmarks"),
    ("Executive Offsite Retreat Blueprint", "https://framez.sg/executive-offsite-retreat-blueprint", "CXO offsite sourcing, security, and agenda structuring in South India and SE Asia"),
    ("B2B Event Agency RFP Evaluation Guide", "https://framez.sg/b2b-event-agency-rfp-evaluation-guide", "Procurement scoring rubrics, RFP templates, and contract checks"),
    ("Corporate Product Launch Event Architecture", "https://framez.sg/corporate-product-launch-event-architecture", "10-week launch protocol, reveal mechanics, press room, and pipeline capture"),
    ("High-Security CXO Board Summit Protocol", "https://framez.sg/high-security-cxo-board-summit-protocol", "TSCM sweeps, confidentiality tiers, close protection, and duty of care"),
    ("Festive Corporate Gala & Diwali Celebrations", "https://framez.sg/festive-corporate-gala-diwali-celebrations", "Corporate Diwali gala staging, decor fire safety, and inclusive design"),
    ("Corporate Family Day Carnival Safety & Logistics", "https://framez.sg/corporate-family-day-carnival-safety-logistics", "Child-safe zones, vendor vetting, crowd engineering, and medical planning"),
    ("Corporate Event Trends in Singapore", "https://framez.sg/corporate-event-trends-singapore", "Singapore MICE production shifts, hybrid AV, and sustainability priorities"),
]

CANONICAL_ORG_NODE = {
    "@type": "Organization",
    "@id": "https://framez.sg/#organization",
    "name": "Frame Events and Productions Private Limited",
    "legalName": "Frame Events and Productions Private Limited",
    "alternateName": [
        "Framez",
        "Framez Events & Productions",
        "Frame Events and Productions",
        "Frame Events",
    ],
    "url": "https://framez.sg/",
    "logo": "https://framez.sg/assets/img/frameznewlogo.png",
    "image": "https://framez.sg/assets/img/cover/Framez%20Events%20And%20Productions%20(1).JPG",
    "email": "info@framez.sg",
    "telephone": "+91-9448066560",
    "description": "B2B corporate event management, MICE conference production, product launches, and brand activation agency operating from Bengaluru and Singapore.",
    "sameAs": [
        "https://www.linkedin.com/company/frame-events-productions",
        "https://www.instagram.com/framez.events",
        "https://www.facebook.com/frameeventsandproductions",
    ],
    "address": [
        {
            "@type": "PostalAddress",
            "name": "Framez Singapore Office",
            "streetAddress": "30 Cecil Street, #19-08 Prudential Tower",
            "addressLocality": "Singapore",
            "postalCode": "049712",
            "addressCountry": "SG",
        },
        {
            "@type": "PostalAddress",
            "name": "Framez India Headquarters",
            "streetAddress": "B/2, GANGA, 3rd Floor, 5th Block, KHB Colony, Koramangala",
            "addressLocality": "Bengaluru",
            "addressRegion": "Karnataka",
            "postalCode": "560095",
            "addressCountry": "IN",
        },
    ],
    "location": [
        {
            "@type": "Place",
            "name": "Framez Singapore: Prudential Tower",
            "address": {
                "@type": "PostalAddress",
                "streetAddress": "30 Cecil Street, #19-08 Prudential Tower",
                "addressLocality": "Singapore",
                "postalCode": "049712",
                "addressCountry": "SG",
            },
            "geo": {
                "@type": "GeoCoordinates",
                "latitude": 1.2816,
                "longitude": 103.8505,
            },
        },
        {
            "@type": "Place",
            "name": "Framez Bengaluru Headquarters",
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
        },
    ],
    "areaServed": [
        {"@type": "Country", "name": "Singapore"},
        {"@type": "Country", "name": "India"},
        {"@type": "City", "name": "Singapore"},
        {"@type": "City", "name": "Bengaluru"},
    ],
    "knowsAbout": [
        "Corporate Event Management",
        "MICE Event Production",
        "Conference Management",
        "Exhibition and Trade Show Management",
        "Experiential Marketing",
        "Brand Activations",
        "Enterprise Product Launches",
        "Employee Annual Days and Awards Galas",
        "Dinner and Dance Events Singapore",
    ],
    "hasCredential": [
        {
            "@type": "EducationalOccupationalCredential",
            "credentialCategory": "certification",
            "name": "ISO 9001:2015 Quality Management System",
            "url": "https://framez.sg/FRAMEZ%20ISO%209001%20Certificate.pdf",
        },
        {
            "@type": "EducationalOccupationalCredential",
            "credentialCategory": "certification",
            "name": "ISO 27001:2013 Information Security Management System",
            "url": "https://framez.sg/FRAMEZ%20ISO%2027001%20Certificate.pdf",
        },
    ],
    "contactPoint": [
        {
            "@type": "ContactPoint",
            "telephone": "+91-9448066560",
            "email": "info@framez.sg",
            "contactType": "sales and customer service",
            "areaServed": ["SG", "IN"],
            "availableLanguage": ["en"],
        }
    ],
}


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def clean_unicode_dashes(text):
    """Replace em/en dashes (literal and JSON-escaped) with clean ASCII punctuation."""
    text = text.replace("\\u2014", ": ").replace("\\u2013", "-")
    text = re.sub(r"(\S)\s*\u2014\s*(\S)", lambda m: f"{m.group(1)}: {m.group(2)}" if m.group(1) == ">" or m.group(2).isupper() else f"{m.group(1)}, {m.group(2)}", text)
    text = text.replace("\u2014", ":")
    text = re.sub(r"(?<=[0-9A-Za-z+$])\s*\u2013\s*(?=[0-9A-Za-z+$])", "-", text)
    text = text.replace("\u2013", "-")
    return text


def sync_head_seo_tags(html, title_escaped, desc_escaped=None):
    """Update <title>, og:title, twitter:title, and optionally meta/og/twitter descriptions."""
    html, n = re.subn(r"<title[^>]*>.*?</title>", f"<title>{title_escaped}</title>", html, count=1, flags=re.S | re.I)
    if n != 1:
        raise RuntimeError("Failed to replace <title>")

    html = re.sub(
        r'(<meta\s+property=["\']og:title["\']\s+content=["\'])[^"\']*(["\'])',
        rf"\g<1>{title_escaped}\g<2>",
        html,
        count=1,
        flags=re.I,
    )
    html = re.sub(
        r'(<meta\s+name=["\']twitter:title["\']\s+content=["\'])[^"\']*(["\'])',
        rf"\g<1>{title_escaped}\g<2>",
        html,
        count=1,
        flags=re.I,
    )

    if desc_escaped is not None:
        html, dn = re.subn(
            r'(<meta\s+name=["\']description["\']\s+content=["\'])[^"\']*(["\'])',
            rf"\g<1>{desc_escaped}\g<2>",
            html,
            count=1,
            flags=re.S | re.I,
        )
        if dn != 1:
            html, dn2 = re.subn(
                r'<meta\s+name=["\']description["\'][^>]*content=["\'][^"\']*["\'][^>]*>',
                f'<meta name="description" content="{desc_escaped}" />',
                html,
                count=1,
                flags=re.S | re.I,
            )
            if dn2 != 1:
                raise RuntimeError("Failed to replace meta description")
        html = re.sub(
            r'(<meta\s+property=["\']og:description["\']\s+content=["\'])[^"\']*(["\'])',
            rf"\g<1>{desc_escaped}\g<2>",
            html,
            count=1,
            flags=re.S | re.I,
        )
        html = re.sub(
            r'(<meta\s+name=["\']twitter:description["\']\s+content=["\'])[^"\']*(["\'])',
            rf"\g<1>{desc_escaped}\g<2>",
            html,
            count=1,
            flags=re.S | re.I,
        )
    return html


def update_first_jsonld(html, mutator):
    """Parse the first application/ld+json block, apply mutator(obj), and serialize back cleanly."""
    m = re.search(r'(<script\s+type=["\']application/ld\+json["\'][^>]*>\s*)(.*?)(\s*</script>)', html, re.S | re.I)
    if not m:
        raise RuntimeError("Missing JSON-LD block")
    obj = json.loads(m.group(2))
    mutator(obj)
    new_json = json.dumps(obj, indent=2, ensure_ascii=False)
    return html[: m.start(2)] + new_json + html[m.end(2) :]


def clean_legacy_bloat(html):
    """Remove insecure Google Maps mixed content, duplicate jQuery 3.3.1, and unused legacy scripts."""
    remove_patterns = [
        r'\s*<!--\s*map jquery include\s*-->\s*',
        r'\s*<!--\s*multy count down - jqury include\s*-->\s*',
        r'\s*<!--\s*color panal - jqury include\s*-->\s*',
        r'\s*<script[^>]+src=["\']https?://maps\.google\.com/maps/api/js[^"\']*["\'][^>]*>\s*</script>',
        r'\s*<script[^>]+src=["\'][^"\']*gmap3\.min\.js[^"\']*["\'][^>]*>\s*</script>',
        r'\s*<script[^>]+src=["\'][^"\']*style-switcher\.js[^"\']*["\'][^>]*>\s*</script>',
        r'\s*<script[^>]+src=["\'][^"\']*jquery\.countdown\.js[^"\']*["\'][^>]*>\s*</script>',
        r'\s*<script[^>]+src=["\'][^"\']*jquery-3\.3\.1\.min\.js[^"\']*["\'][^>]*>\s*</script>',
    ]
    for pat in remove_patterns:
        html = re.sub(pat, "\n", html, flags=re.I)

    # Defer remaining non-critical bottom assets/js scripts cleanly in document order
    defer_scripts = (
        "popper.min.js",
        "bootstrap.min.js",
        "slick.min.js",
        "owl.carousel.min.js",
        "atc.min.js",
        "jquery.magnific-popup.min.js",
        "isotope.pkgd.min.js",
        "jarallax.min.js",
        "jquery.mCustomScrollbar.concat.min.js",
        "imagesloaded.pkgd.min.js",
        "custom.js",
        "myjs1.js",
    )

    def add_defer(match):
        tag = match.group(0)
        if any(name in tag for name in defer_scripts) and not re.search(r"\bdefer\b", tag, re.I):
            return tag.replace("<script ", "<script defer ", 1)
        return tag

    html = re.sub(r'<script\b[^>]+src=["\']assets/js/[^"\']+["\'][^>]*>', add_defer, html, flags=re.I)

    # Non-render-blocking load for secondary animation/carousel CSS plugins
    defer_css = (
        "slick.css",
        "slick-theme.css",
        "animate.css",
        "owl.carousel.min.css",
        "owl.theme.default.min.css",
        "magnific-popup.css",
    )

    def defer_stylesheet(match):
        tag = match.group(0)
        if any(css in tag for css in defer_css) and "onload=" not in tag.lower():
            return re.sub(r"\s*/?>$", ' media="print" onload="this.media=\'all\'">', tag)
        return tag

    html = re.sub(r'<link\b[^>]+rel=["\']stylesheet["\'][^>]+>', defer_stylesheet, html, flags=re.I)
    html = re.sub(r'style="padding:60px 0;"\s+style="background:', 'style="background:', html)
    return html


def transform_header_php(orig):
    """Remove stray <meta charset> inside <header> and upgrade Organization entity graph."""
    h = re.sub(r'(<header\b[^>]*>)\s*<meta\s+charset=["\']utf-8["\']\s*/?>', r"\1", orig, count=1, flags=re.I)
    if "decoding=" not in h:
        h = h.replace(
            '<img src="assets/img/frameznewlogo.png"',
            '<img decoding="async" src="assets/img/frameznewlogo.png"',
            1,
        )

    def mutate_header(obj):
        obj["@graph"] = [
            CANONICAL_ORG_NODE,
            {
                "@type": "WebSite",
                "@id": "https://framez.sg/#website",
                "url": "https://framez.sg/",
                "name": "Frame Events and Productions Private Limited",
                "alternateName": "Framez Events & Productions",
                "publisher": {"@id": "https://framez.sg/#organization"},
            },
        ]

    h = update_first_jsonld(h, mutate_header)
    return clean_unicode_dashes(h)


def transform_index_html(orig):
    """Upgrade index.html for legal brand #1 ranking, clean hreflang, dual-HQ NAP & CWV."""
    h = re.sub(r'\s*<link\s+rel=["\']alternate["\']\s+hreflang=["\'][^"\']+["\'][^>]*>\s*', "\n    ", orig, flags=re.I)
    h = re.sub(r"\n{3,}", "\n\n", h)

    new_title = "Frame Events &amp; Productions (Framez) | Corporate Events"
    h = sync_head_seo_tags(h, new_title)

    def mutate_home_ld(obj):
        new_graph = []
        for item in obj.get("@graph", []):
            t = item.get("@type")
            if t == "Organization":
                new_graph.append(CANONICAL_ORG_NODE)
            elif t == "WebSite":
                item["name"] = "Frame Events and Productions Private Limited"
                item["alternateName"] = "Framez Events & Productions"
                item["publisher"] = {"@id": "https://framez.sg/#organization"}
                new_graph.append(item)
            elif t == "WebPage":
                item["name"] = "Frame Events & Productions (Framez) | Corporate Events"
                new_graph.append(item)
            else:
                new_graph.append(item)
        obj["@graph"] = new_graph

    h = update_first_jsonld(h, mutate_home_ld)

    # Ensure decoding="async" on navbar logo & safe attributes on non-hero images
    h = h.replace(
        '<img alt="Frame Events and Productions Private Limited Logo"',
        '<img decoding="async" alt="Frame Events and Productions Private Limited Logo"',
    ) if 'decoding="async" alt="Frame Events and Productions Private Limited Logo"' not in h else h

    def ensure_non_hero_img_attrs(match):
        tag = match.group(0)
        if "fetchpriority" in tag.lower() or "Frame Events and Productions Private Limited Logo" in tag:
            return tag
        if "decoding=" not in tag.lower():
            tag = tag.replace("<img ", '<img decoding="async" ', 1)
        if "loading=" not in tag.lower():
            tag = tag.replace("<img ", '<img loading="lazy" ', 1)
        return tag

    h = re.sub(r"<img\b[^>]*>", ensure_non_hero_img_attrs, h, flags=re.S | re.I)

    # Upgrade fz-context brand clarity + MICE internal link without em dashes
    h = h.replace(
        "Framez plans and produces corporate events in Bangalore and Singapore \u2014 conferences, product launches, annual days and brand activations.",
        "Frame Events and Productions Private Limited (Framez) plans and produces corporate events in Bangalore and Singapore, including conferences, product launches, annual days, and brand activations.",
    )
    if "/conference-and-mice-event-management" not in h:
        h = h.replace(
            '<a href="/corporate-event-management-company">Corporate event management</a>',
            '<a href="/corporate-event-management-company">Corporate event management</a>\n                <a href="/conference-and-mice-event-management">Conferences &amp; MICE</a>',
            1,
        )

    # Ensure Singapore Prudential Tower NAP appears visibly alongside Bengaluru in Locations card
    if "30 Cecil Street, #19-08 Prudential Tower, Singapore 049712" not in h[: h.find("<footer")]:
        blr_loc_marker = 'Koramangala, Bengaluru - 560095</span>\n                                </li>'
        sg_loc_li = (
            blr_loc_marker
            + '\n                                <li class="flex items-start gap-3" style="margin-top:8px;">\n'
            '                                    <i class="fas fa-map-marker-alt text-brand-purple mt-1"></i>\n'
            '                                    <span class="text-slate-200" style="color:#e2e8f0 !important;">30 Cecil Street, #19-08 Prudential Tower, Singapore 049712</span>\n'
            "                                </li>"
        )
        if blr_loc_marker in h:
            h = h.replace(blr_loc_marker, sg_loc_li, 1)

    h = h.replace('onclick="toggleFramezChat()">\ufffd</button>', 'onclick="toggleFramezChat()">&times;</button>')
    return clean_unicode_dashes(h)


def transform_corp_emc(orig):
    """Fix commercial title cannibalization & add SG/BLR/MICE links on corporate-event-management-company.php."""
    h = clean_legacy_bloat(orig)
    new_title = "Corporate Event Management Company | Frame Events (Framez)"
    new_desc = (
        "B2B corporate event management by Frame Events (Framez) in Singapore and Bangalore: "
        "conferences, product launches, annual days, and MICE production."
    )
    h = sync_head_seo_tags(h, new_title, new_desc)

    def mutate_ld(obj):
        for item in obj.get("@graph", []):
            if item.get("@type") == "WebPage":
                item["name"] = new_title

    h = update_first_jsonld(h, mutate_ld)

    if "/conference-and-mice-event-management" not in h:
        target = 'See the <a href="/corporate-event-budget-planning-guide">event budget planning guide</a> for structuring quotes, browse <a href="/our-events-and-services">all services</a>, or <a href="/get-in-touch">share your brief</a>.'
        replacement = (
            'Explore our regional <a href="/event-management-company-in-singapore">Singapore event management</a> and '
            '<a href="/event-management-company-in-bangalore">Bangalore event management</a> hubs, '
            '<a href="/conference-and-mice-event-management">conference and MICE services</a>, '
            'the <a href="/corporate-event-budget-planning-guide">event budget planning guide</a>, '
            'or <a href="/book-a-demo">book a brief consultation</a>.'
        )
        if target in h:
            h = h.replace(target, replacement, 1)

    return clean_unicode_dashes(h)


def transform_bangalore(orig):
    """Fix H1/title cannibalization, inject Koramangala ProfessionalService + GeoCoordinates & MICE link."""
    h = clean_legacy_bloat(orig)
    new_title = "Corporate Event Management Company in Bangalore | Framez"
    new_desc = (
        "Corporate event management company in Bangalore from our Koramangala HQ: "
        "conferences, product launches, annual days, and activations across Whitefield &amp; ORR."
    )
    h = sync_head_seo_tags(h, new_title, new_desc)

    h = re.sub(
        r"<h1([^>]*)>.*?</h1>",
        r"<h1\1>Corporate Event Management Company in Bangalore</h1>",
        h,
        count=1,
        flags=re.S | re.I,
    )

    blr_local_node = {
        "@type": "ProfessionalService",
        "@id": "https://framez.sg/event-management-company-in-bangalore#bangalore-office",
        "name": "Frame Events and Productions Private Limited: Bengaluru HQ",
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
        "areaServed": [
            {"@type": "City", "name": "Bengaluru"},
            {"@type": "City", "name": "Bangalore"},
        ],
    }

    def mutate_ld(obj):
        graph = [item for item in obj.get("@graph", []) if item.get("@type") != "ProfessionalService"]
        for item in graph:
            if item.get("@type") == "WebPage":
                item["name"] = new_title
        graph.append(blr_local_node)
        obj["@graph"] = graph

    h = update_first_jsonld(h, mutate_ld)

    if "/conference-and-mice-event-management" not in h:
        old_link_line = (
            'Read more about our <a href="/corporate-event-management-company">corporate event management</a> scope, '
            'explore <a href="/event-management-company-in-singapore">Singapore corporate event management</a>, '
            'plan an <a href="/annual-day-and-awards-night-planning-guide">annual day or awards night</a>, '
            'or <a href="/get-in-touch">contact the team</a> with your brief.'
        )
        new_link_block = (
            'Our Bengaluru headquarters is located at <strong>B/2, GANGA, 3rd Floor, 5th Block, KHB Colony, Koramangala, Bengaluru 560095</strong>, '
            'supporting corporate venues across Whitefield, Outer Ring Road, Electronic City, Central Business District, and BIEC. '
            'Explore our <a href="/conference-and-mice-event-management">conference and MICE event management</a> services, '
            '<a href="/corporate-event-management-company">corporate event management</a> scope, '
            '<a href="/event-management-company-in-singapore">Singapore corporate event management</a>, '
            '<a href="/annual-day-and-awards-night-planning-guide">annual day and awards night guide</a>, '
            'or <a href="/book-a-demo">schedule a brief consultation</a>.'
        )
        if old_link_line in h:
            h = h.replace(old_link_line, new_link_block, 1)

    return clean_unicode_dashes(h)


def transform_singapore(orig):
    """Add AEO citation block, Singapore venue matrix, MICE cross-link & SG GeoCoordinates."""
    h = orig.replace("Navigating Singapore venue districts", "Planning across Singapore venue districts")

    def mutate_ld(obj):
        for item in obj.get("@graph", []):
            if item.get("@type") == "ProfessionalService":
                item["name"] = "Framez Events & Productions: Singapore"
                item["geo"] = {
                    "@type": "GeoCoordinates",
                    "latitude": 1.2816,
                    "longitude": 103.8505,
                }

    h = update_first_jsonld(h, mutate_ld)

    aeo_block = (
        '\n      <div id="aeo-citation" class="fzguide-note" style="border-left:4px solid #1e1b4b;color:#0f172a;">'
        '<strong>Entity Citation (Singapore):</strong> Frame Events and Productions Private Limited (Framez) '
        'delivers B2B corporate conferences, MICE conventions, product launches, and Dinner &amp; Dance awards galas '
        'from <strong>30 Cecil Street, #19-08 Prudential Tower, Singapore 049712</strong>, backed by ISO 9001:2015 '
        'and ISO 27001:2013 quality and information security standards alongside full PDPA-aligned attendee operations.'
        '</div>\n'
    )
    if 'id="aeo-citation"' not in h:
        h = h.replace('<nav class="fzguide-toc"', aeo_block + '      <nav class="fzguide-toc"', 1)

    venue_matrix = """
      <h2 id="singapore-venues">Singapore MICE and corporate venue matrix</h2>
      <p>Framez coordinates technical production, rigging plots, electrical sign-offs, and marshalling-yard load-ins across Singapore's primary corporate venues and works alongside our dedicated <a href="/conference-and-mice-event-management">conference and MICE event management</a> team for multi-track conventions:</p>
      <div class="fzguide-tablewrap">
        <table>
          <thead><tr><th>Venue Hub</th><th>Best-Fit Corporate Formats</th><th>Key Production &amp; Load-In Notes</th></tr></thead>
          <tbody>
            <tr><td><strong>Marina Bay Sands Expo</strong></td><td>Regional APAC conferences, large exhibitions, gala dinners (300 to 3,000+ delegates)</td><td>Advance rigging and floor-loading approvals, scheduled marshalling-yard truck slots, and strict overnight build windows.</td></tr>
            <tr><td><strong>Suntec Singapore</strong></td><td>Multi-track B2B summits, partner forums, corporate plenary halls (200 to 2,500+ delegates)</td><td>High-ceiling plenary LED flexibility, concurrent breakout AV synchronization, and central Marina Centre transit access.</td></tr>
            <tr><td><strong>Singapore EXPO</strong></td><td>Trade shows, industrial expos, multi-exhibitor pavilions, large staff town halls</td><td>Heavy-freight hall doors, custom island booth fabrication clearances, and dedicated exhibitor power/rigging cutoffs.</td></tr>
            <tr><td><strong>Raffles City</strong></td><td>CBD leadership summits, investor briefings, Dinner &amp; Dance awards nights (100 to 1,200 delegates)</td><td>Direct MRT access for CBD executives, ballroom chandelier height checks, and rapid daytime-to-gala room turnovers.</td></tr>
          </tbody>
        </table>
      </div>
"""
    if 'id="singapore-venues"' not in h:
        h = h.replace(
            '<li><a href="#singapore-operations">',
            '<li><a href="#singapore-venues">Singapore MICE and corporate venue matrix</a></li>\n          <li><a href="#singapore-operations">',
            1,
        )
        h = h.replace('<h2 id="governance">', venue_matrix + '\n      <h2 id="governance">', 1)

    if '/conference-and-mice-event-management">Conference' not in h:
        h = h.replace(
            '<p class="fzguide-related">Related: ',
            '<p class="fzguide-related">Related: <a href="/conference-and-mice-event-management">Conference &amp; MICE Management</a> · ',
            1,
        )

    return clean_unicode_dashes(h)


def transform_book_a_demo(orig):
    """Expand book-a-demo.php to 850+ words with Enterprise RFP Scope Checklist + FAQPage schema."""
    h = clean_legacy_bloat(orig)

    faq_node = {
        "@type": "FAQPage",
        "@id": "https://framez.sg/book-a-demo#faq",
        "mainEntity": [
            {
                "@type": "Question",
                "name": "What happens after we submit the Framez event brief form?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": "Our production leads in Singapore or Bengaluru review your target dates, format, and headcount, then schedule a focused scoping call to confirm technical requirements and deliver an itemized proposal.",
                },
            },
            {
                "@type": "Question",
                "name": "Which details help Framez prepare an accurate corporate event quote?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": "Sharing the event objective, estimated guest count, city (Singapore, Bengaluru, or pan-India), venue booking status, core AV or stage needs, and target budget band lets us produce a realistic line-item estimate.",
                },
            },
            {
                "@type": "Question",
                "name": "Can Framez support confidential enterprise RFPs under NDA and ISO standards?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": "Yes. Frame Events and Productions Private Limited operates under ISO 9001:2015 quality management and ISO 27001:2013 information security standards and executes client NDAs before reviewing unreleased product or leadership summit briefs.",
                },
            },
            {
                "@type": "Question",
                "name": "How far in advance should we book a briefing for Singapore or Bangalore events?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": "For 200+ delegate conferences, trade booths, or year-end Dinner and Dance galas, booking a briefing 10 to 16 weeks ahead secures preferred ballroom dates and avoids rush fabrication costs.",
                },
            },
            {
                "@type": "Question",
                "name": "Does Framez work alongside venues we have already contracted?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": "Yes. Many corporate clients contract their Singapore convention centre or Bangalore hotel ballroom directly and engage Framez for creative stage design, technical AV engineering, registration operations, and live show-calling.",
                },
            },
        ],
    }

    def mutate_ld(obj):
        graph = [item for item in obj.get("@graph", []) if item.get("@type") != "FAQPage"]
        for item in graph:
            if item.get("@type") == "WebPage" or item.get("@type") == "ContactPage":
                item["name"] = "Book a Demo: Discuss Your Event Brief | Framez"
        graph.append(faq_node)
        obj["@graph"] = graph

    h = update_first_jsonld(h, mutate_ld)

    scope_section = """
		<section id="event-brief-scope" style="background:#f8fafc;padding:56px 20px;color:#0f172a;">
			<div class="container" style="max-width:1040px;">
				<h2 style="font-size:1.9rem;font-weight:800;color:#1e1b4b;margin-bottom:14px;">Enterprise Event Brief &amp; RFP Scope Checklist (Singapore &amp; Bangalore)</h2>
				<p style="font-size:16.5px;line-height:1.75;color:#334155;">Use this consultation form to schedule a working session with producers at <strong>Frame Events and Productions Private Limited (Framez)</strong> from our Singapore office (<strong>30 Cecil Street, #19-08 Prudential Tower, Singapore 049712</strong>) or India headquarters (<strong>B/2, GANGA, 3rd Floor, 5th Block, KHB Colony, Koramangala, Bengaluru 560095</strong>). Whether you are shortlisting agencies for a formal tender or checking production feasibility against a target date, preparing the six items below helps our team return a structured, itemized estimate quickly.</p>

				<div style="overflow-x:auto;margin:24px 0;background:#ffffff;border:1px solid #e2e8f0;border-radius:10px;">
					<table class="table" style="margin-bottom:0;font-size:15px;">
						<thead style="background:#1e1b4b;color:#ffffff;">
							<tr>
								<th>RFP Scope Dimension</th>
								<th>What to Share in Your Brief</th>
								<th>How Framez Evaluates It</th>
							</tr>
						</thead>
						<tbody>
							<tr>
								<td><strong>1. Format &amp; Business Goal</strong></td>
								<td>Conference, MICE summit, product launch, exhibition stall, Dinner &amp; Dance gala, or annual day.</td>
								<td>Defines stage scale, breakout structure, show-calling depth, and measurable success criteria.</td>
							</tr>
							<tr>
								<td><strong>2. City &amp; Venue Corridor</strong></td>
								<td>Singapore (Marina Bay Sands Expo, Suntec, Raffles City, Singapore EXPO) or Bangalore (Koramangala, Whitefield, ORR, CBD, BIEC).</td>
								<td>Maps load-in windows, rigging limits, traffic buffers, and local regulatory approvals.</td>
							</tr>
							<tr>
								<td><strong>3. Delegate Count &amp; Mix</strong></td>
								<td>Estimated in-room headcount, VIP/speaker ratio, and any remote watch-party offices.</td>
								<td>Sizes plenary sightlines, check-in desks, F&amp;B guarantees, and hybrid AV feeds.</td>
							</tr>
							<tr>
								<td><strong>4. Scenic, AV &amp; Exhibition Specs</strong></td>
								<td>LED wall resolution, custom booth footprint, broadcast recording, or interactive demo pods.</td>
								<td>Separates fixed production engineering from optional experiential and media modules.</td>
							</tr>
							<tr>
								<td><strong>5. Governance &amp; Compliance</strong></td>
								<td>ISO 9001:2015, ISO 27001:2013, NDA requirements, PDPA/DPDP data handling, and RAMS filings.</td>
								<td>Locks attendee data controls, security clearance, and site safety documentation upfront.</td>
							</tr>
							<tr>
								<td><strong>6. Budget Band &amp; Decision Date</strong></td>
								<td>Indicative budget ceiling, currency (SGD or INR), and procurement sign-off milestone.</td>
								<td>Ensures proposals match realistic hardware specs with transparent written change-order terms.</td>
							</tr>
						</tbody>
					</table>
				</div>

				<h3 style="font-size:1.35rem;font-weight:700;color:#0f172a;margin-top:28px;">How the Consultation and Proposal Process Works</h3>
				<p style="font-size:16px;line-height:1.75;color:#334155;">Enterprise procurement and marketing teams rarely want generic slide decks during a first call. Our scoping consultations follow a practical three-step sequence built around operational clarity:</p>
				<ol style="font-size:15.5px;line-height:1.8;color:#334155;padding-left:22px;">
					<li><strong>Step 1, Brief &amp; Objective Alignment (20 to 30 Minutes):</strong> We review your event format, audience profile, target city, venue booking status, and internal approval schedule. If the programme involves unreleased products or executive board briefings, we execute a mutual NDA prior to reviewing sensitive decks.</li>
					<li><strong>Step 2, Venue &amp; Technical Feasibility Check:</strong> For shortlisted venues in Singapore (CBD hotels, Marina Bay Sands Expo, Suntec Singapore, Singapore EXPO, or Raffles City) or Bengaluru (Whitefield, Outer Ring Road, CBD, North Bangalore, or Electronic City), our production team flags freight-lift sizes, clear ceiling heights, rigging capacity, dedicated power needs, and acoustic curfews early.</li>
					<li><strong>Step 3, Itemized Scope &amp; Line-Item BoQ Delivery:</strong> Within two to four business days of your briefing, Framez returns an itemized proposal separating fixed production engineering, scenic fabrication, per-guest hospitality or badge operations, optional additions, explicit exclusions, and written change-order terms.</li>
				</ol>

				<h3 style="font-size:1.35rem;font-weight:700;color:#0f172a;margin-top:28px;">Regional Planning Benchmarks: Singapore vs Bangalore</h3>
				<div style="overflow-x:auto;margin:18px 0;background:#ffffff;border:1px solid #e2e8f0;border-radius:10px;">
					<table class="table" style="margin-bottom:0;font-size:14.5px;">
						<thead style="background:#312e81;color:#ffffff;">
							<tr>
								<th>Operational Area</th>
								<th>Singapore Programmes (Prudential Tower Desk)</th>
								<th>Bangalore &amp; India Programmes (Koramangala HQ)</th>
							</tr>
						</thead>
						<tbody>
							<tr>
								<td><strong>Recommended Lead Time</strong></td>
								<td>10 to 16 weeks for 200+ guest conferences, MICE summits, and D&amp;D galas; 4 to 6 weeks for executive roundtables.</td>
								<td>8 to 12 weeks for conferences and annual days; 12 to 16 weeks for multi-city roadshows or 1,000+ employee carnivals.</td>
							</tr>
							<tr>
								<td><strong>Regulatory &amp; Safety Prep</strong></td>
								<td>PDPA attendee consent notices, RAMS filings, venue marshalling-yard booking, and applicable GoBusiness clearances.</td>
								<td>DPDP consent rules, dedicated silent-DG backup for LED walls, venue load-in timing windows, and performance licensing clarity.</td>
							</tr>
							<tr>
								<td><strong>Billing &amp; Cost Structure</strong></td>
								<td>Itemized SGD cost tables covering venue support, AV hardware, custom carpentry, staffing, and contingency reserves.</td>
								<td>Standardized INR GST-compliant Bill of Quantities across single or multi-city hubs with pre-approved variation thresholds.</td>
							</tr>
						</tbody>
					</table>
				</div>

				<h3 style="font-size:1.35rem;font-weight:700;color:#0f172a;margin-top:28px;">Explore Relevant Service Hubs &amp; Planning Guides</h3>
				<p style="font-size:15.5px;line-height:1.7;color:#334155;">If your procurement team is finalizing an internal business case before our call, review our <a href="/corporate-event-management-company" style="color:#ef4444;font-weight:600;">Corporate Event Management</a> overview, <a href="/event-management-company-in-singapore" style="color:#ef4444;font-weight:600;">Singapore Event Management</a>, <a href="/event-management-company-in-bangalore" style="color:#ef4444;font-weight:600;">Bangalore Event Management</a>, <a href="/conference-and-mice-event-management" style="color:#ef4444;font-weight:600;">Conference &amp; MICE Management</a>, <a href="/corporate-event-budget-planning-guide" style="color:#ef4444;font-weight:600;">Corporate Event Budget Planning Guide</a>, and <a href="/b2b-event-agency-rfp-evaluation-guide" style="color:#ef4444;font-weight:600;">B2B Event Agency RFP Evaluation Guide</a>.</p>

				<h3 style="font-size:1.35rem;font-weight:700;color:#0f172a;margin-top:28px;">Frequently Asked Questions About Booking a Consultation</h3>
				<div style="margin-top:14px;">
					<h4 style="font-size:1.05rem;font-weight:700;color:#1e1b4b;">What happens after we submit the Framez event brief form?</h4>
					<p style="font-size:15px;color:#475569;">Our production leads in Singapore or Bengaluru review your target dates, format, and headcount, then schedule a focused scoping call to confirm technical requirements and deliver an itemized proposal.</p>

					<h4 style="font-size:1.05rem;font-weight:700;color:#1e1b4b;margin-top:14px;">Which details help Framez prepare an accurate corporate event quote?</h4>
					<p style="font-size:15px;color:#475569;">Sharing the event objective, estimated guest count, city (Singapore, Bengaluru, or pan-India), venue booking status, core AV or stage needs, and target budget band lets us produce a realistic line-item estimate.</p>

					<h4 style="font-size:1.05rem;font-weight:700;color:#1e1b4b;margin-top:14px;">Can Framez support confidential enterprise RFPs under NDA and ISO standards?</h4>
					<p style="font-size:15px;color:#475569;">Yes. Frame Events and Productions Private Limited operates under ISO 9001:2015 quality management and ISO 27001:2013 information security standards and executes client NDAs before reviewing unreleased product or leadership summit briefs.</p>

					<h4 style="font-size:1.05rem;font-weight:700;color:#1e1b4b;margin-top:14px;">How far in advance should we book a briefing for Singapore or Bangalore events?</h4>
					<p style="font-size:15px;color:#475569;">For 200+ delegate conferences, trade booths, or year-end Dinner and Dance galas, booking a briefing 10 to 16 weeks ahead secures preferred ballroom dates and avoids rush fabrication costs.</p>

					<h4 style="font-size:1.05rem;font-weight:700;color:#1e1b4b;margin-top:14px;">Does Framez work alongside venues we have already contracted?</h4>
					<p style="font-size:15px;color:#475569;">Yes. Many corporate clients contract their Singapore convention centre or Bangalore hotel ballroom directly and engage Framez for creative stage design, technical AV engineering, registration operations, and live show-calling.</p>
				</div>
			</div>
		</section>
"""
    if 'id="event-brief-scope"' not in h:
        h = h.replace(
            '<section id="testimonial5-section"',
            scope_section + '\n\t\t<section id="testimonial5-section"',
            1,
        )

    return clean_unicode_dashes(h)


def transform_page1_zero_ctr(fname, orig):
    """Apply title/meta/CTA upgrades for Page-1 zero-CTR pages & strip em/en dashes + buzzwords."""
    h = orig
    if fname == "corporate-product-launch-event-architecture.php":
        title = "Product Launch Event Planning &amp; Production Guide | Framez"
        desc = (
            "Plan a corporate product launch in Singapore or Bangalore: 10-week checklist, "
            "stage reveal specs, press ops, and budget benchmarks. Request a launch quote."
        )
        h = sync_head_seo_tags(h, title, desc)
        if 'href="https://framez.sg/book-a-demo"' not in h and 'href="/book-a-demo"' not in h:
            old_cta = (
                '<a href="https://framez.sg/clientele" class="btn-cta">See Our Launch Clientele</a>\n'
                '            <a href="https://framez.sg/get-in-touch" class="btn-cta" style="margin-left:12px;">Request a Launch Proposal</a>'
            )
            new_cta = (
                '<a href="/book-a-demo" class="btn-cta">Book a Launch Brief</a>\n'
                '            <a href="/corporate-event-management-company" class="btn-cta" style="margin-left:12px;">Corporate Event Services</a>\n'
                '            <p style="margin-top:16px;font-size:0.95rem;">Explore regional hubs: '
                '<a href="/event-management-company-in-singapore" style="color:#a78bfa;">Singapore Events</a> | '
                '<a href="/event-management-company-in-bangalore" style="color:#a78bfa;">Bangalore Events</a> | '
                '<a href="/conference-and-mice-event-management" style="color:#a78bfa;">Conferences &amp; MICE</a> | '
                '<a href="/clientele" style="color:#a78bfa;">Clientele</a></p>'
            )
            if old_cta in h:
                h = h.replace(old_cta, new_cta, 1)

    elif fname == "corporate-event-budget-planning-guide.php":
        title = "Corporate Event Budget Breakdown &amp; Scope Guide | Framez"
        desc = (
            "Structure a corporate event budget for Singapore and India: fixed vs per-guest costs, "
            "AV &amp; venue line items, change orders, and quote checklist."
        )
        h = sync_head_seo_tags(h, title, desc)

        def mutate_ld(obj):
            for item in obj.get("@graph", []):
                if item.get("@type") == "WebPage":
                    item["name"] = "Corporate Event Budget Breakdown & Scope Guide | Framez"

        h = update_first_jsonld(h, mutate_ld)
        if 'href="/book-a-demo"' not in h:
            h = h.replace(
                '<a class="fzguide-btn" href="/get-in-touch">Discuss Your Event Brief</a>',
                '<a class="fzguide-btn" href="/book-a-demo">Book a Budget Scope Call</a>',
                1,
            )
            h = h.replace(
                '<p class="fzguide-related">Related: ',
                '<p class="fzguide-related">Related: <a href="/corporate-event-management-company">Corporate Event Management</a> · <a href="/event-management-company-in-singapore">Singapore Events</a> · <a href="/event-management-company-in-bangalore">Bangalore Events</a> · ',
                1,
            )

    elif fname == "annual-day-and-awards-night-planning-guide.php":
        title = "Corporate Annual Day &amp; Awards Night Checklist | Framez"
        desc = (
            "Plan a company annual day or awards gala in Singapore or India: award approvals, "
            "run-of-show template, stage rehearsals, and inclusive guest ops."
        )
        h = sync_head_seo_tags(h, title, desc)

        def mutate_ld(obj):
            for item in obj.get("@graph", []):
                if item.get("@type") == "WebPage":
                    item["name"] = "Corporate Annual Day & Awards Night Checklist | Framez"

        h = update_first_jsonld(h, mutate_ld)
        if 'href="/book-a-demo"' not in h:
            h = h.replace(
                '<a class="fzguide-btn" href="/get-in-touch">Discuss Your Event Brief</a>',
                '<a class="fzguide-btn" href="/book-a-demo">Book an Annual Day Brief</a>',
                1,
            )
            h = h.replace(
                '<p class="fzguide-related">Related: ',
                '<p class="fzguide-related">Related: <a href="/corporate-event-management-company">Corporate Event Management</a> · <a href="/event-management-company-in-singapore">Singapore Events</a> · <a href="/event-management-company-in-bangalore">Bangalore Events</a> · ',
                1,
            )

    elif fname == "event-planner.php":
        title = "Corporate Event Planner in Singapore &amp; Bangalore | Framez"
        desc = (
            "Work with an ISO-certified corporate event planner in Singapore and Bangalore: "
            "venue sourcing, stage AV, run-of-show, and itemized quotes."
        )
        h = sync_head_seo_tags(h, title, desc)

        def mutate_ld(obj):
            for item in obj.get("@graph", []):
                if item.get("@type") == "WebPage":
                    item["name"] = "Corporate Event Planner in Singapore & Bangalore | Framez"
                    item["description"] = html_lib.unescape(desc)
                elif item.get("@type") == "Service":
                    item["description"] = html_lib.unescape(desc)

        h = update_first_jsonld(h, mutate_ld)
        h = h.replace("Delegate Journey &amp; Hospitality", "Delegate Arrival &amp; Hospitality")
        if "/conference-and-mice-event-management" not in h:
            h = h.replace(
                '<p class="fzguide-related">Related: ',
                '<p class="fzguide-related">Related: <a href="/conference-and-mice-event-management">Conference &amp; MICE Management</a> · ',
                1,
            )

    return clean_unicode_dashes(h)


def transform_remaining_legacy(fname, orig):
    """Clean JS/CSS bloat, banned buzzwords, and em/en dashes on remaining legacy files."""
    if fname == "clientele.php":
        return orig

    h = clean_legacy_bloat(orig)
    if fname == "about-us.php":
        h = h.replace('width="100%"/ style="border-radius:20px;"', 'style="width:100%;border-radius:20px;"')
        h = h.replace(
            "Explore Our Journey: Passion, Creativity, and Excellence",
            "Our Production Standards: Passion, Creativity, and Excellence",
        )
        h = h.replace(
            "transform the event landscape by seamlessly blending state-of-the-art technology with artistic finesse",
            "raise corporate event production standards by combining modern AV engineering with creative staging",
        )
        h = h.replace(
            "Uncover the Framez distinction and unlock the full potential of your upcoming corporate event with us.",
            "Explore the Framez approach and plan your upcoming corporate event with our production team.",
        )
    elif fname == "Framez-Public-Statement-on-Health-and-Safety-Commitment.php":
        h = h.replace("implement robust mitigation strategies", "implement documented mitigation strategies")
        h = h.replace("to foster a shared understanding", "to build a shared understanding")
        h = h.replace(
            "As we navigate the dynamic landscape of events and productions, our unwavering commitment to health and safety remains steadfast. Together, we will continue to uphold the highest standards of safety, fostering an environment where everyone can thrive.",
            "Across all corporate events and live productions, our commitment to health and safety remains constant. Together, we uphold practical site safety standards, maintaining an environment where every crew member, vendor, and guest can participate safely.",
        )
        h = h.replace('href="book-a-demo.php"', 'href="/book-a-demo"')
    elif fname == "our-events-and-services.php":
        if "/conference-and-mice-event-management" not in h:
            h = h.replace(
                'Regional Delivery Hubs:</strong> Framez executes programmes across',
                'Regional Delivery Hubs:</strong> Framez delivers <a href="/conference-and-mice-event-management" style="color:#ef4444;font-weight:700;">conferences and MICE</a> across',
                1,
            )

    return clean_unicode_dashes(h)


def build_llms_txt():
    lines = [
        "# Framez Events & Productions",
        "",
        "> Frame Events and Productions Private Limited (Framez) is an ISO 9001:2015 and ISO 27001:2013 certified B2B corporate event management, MICE production, and experiential brand activation agency operating from Bengaluru, India and Singapore.",
        "",
        "## Entity Disambiguation",
        "",
        "- **Canonical Legal Entity (India HQ)**: Frame Events and Productions Private Limited",
        "- **Singapore Entity**: Frame Events & Productions Pte. Ltd.",
        "- **Brand & Alternate Names**: Framez, Framez Events & Productions, Frame Events and Productions, Frame Events",
        "- **Official Website**: https://framez.sg/",
        "- **Scope**: B2B corporate conferences, MICE programmes, enterprise product launches, Dinner & Dance awards galas, exhibition booths, and experiential brand activations across Singapore, Bengaluru, and APAC (unrelated to consumer picture framing or retail framing businesses).",
        "",
        "## Dual Headquarters & Verified NAP",
        "",
        "- **Singapore Office**: 30 Cecil Street, #19-08 Prudential Tower, Singapore 049712 (Geo: 1.2816, 103.8505)",
        "- **India Headquarters**: B/2, GANGA, 3rd Floor, 5th Block, KHB Colony, Koramangala, Bengaluru, Karnataka 560095, India (Geo: 12.9352, 77.6245)",
        "- **Email**: info@framez.sg",
        "- **Phone**: +91-9448066560",
        "",
        "## Quality & Security Certifications",
        "",
        "- [ISO 9001:2015 Quality Management Certificate](https://framez.sg/FRAMEZ%20ISO%209001%20Certificate.pdf)",
        "- [ISO 27001:2013 Information Security Certificate](https://framez.sg/FRAMEZ%20ISO%2027001%20Certificate.pdf)",
        "- [Public Statement on Health & Safety Commitment](https://framez.sg/Framez-Public-Statement-on-Health-and-Safety-Commitment)",
        "",
        "## Complete 29-URL Sitemap Inventory",
        "",
    ]
    for label, url, _ in SITEMAP_29_URLS:
        lines.append(f"- [{label}]({url})")
    lines.append("")
    return "\n".join(lines)


def build_llms_full_txt():
    lines = [
        "# Framez Events & Productions: Full Site Context",
        "",
        "> Frame Events and Productions Private Limited (Framez) is an ISO 9001:2015 and ISO 27001:2013 certified corporate event management, MICE production, and brand activation agency serving enterprise teams in Singapore, Bengaluru, and across APAC. This file provides structured navigation and verified factual context for crawlers and answer engines.",
        "",
        "## Entity Disambiguation & Company Profile",
        "",
        "- **Legal Name**: Frame Events and Productions Private Limited",
        "- **Singapore Operating Name**: Frame Events & Productions Pte. Ltd.",
        "- **Brand & Alternate Names**: Framez, Framez Events & Productions, Frame Events and Productions, Frame Events",
        "- **Core Services**: B2B corporate conferences, MICE programmes, product launches, executive CXO summits, employee annual days, Dinner & Dance (D&D) awards nights, exhibition booths, and experiential brand activations",
        "- **Disambiguation Note**: Refers solely to the B2B corporate event management and technical production company at https://framez.sg (not consumer photo or framing shops).",
        "- **Certifications**: [ISO 9001:2015 Certificate](https://framez.sg/FRAMEZ%20ISO%209001%20Certificate.pdf) and [ISO 27001:2013 Certificate](https://framez.sg/FRAMEZ%20ISO%2027001%20Certificate.pdf)",
        "- **Singapore Office**: 30 Cecil Street, #19-08 Prudential Tower, Singapore 049712 (GeoCoordinates: 1.2816, 103.8505)",
        "- **India Headquarters**: B/2, GANGA, 3rd Floor, 5th Block, KHB Colony, Koramangala, Bengaluru, Karnataka 560095, India (GeoCoordinates: 12.9352, 77.6245)",
        "- **Email**: info@framez.sg",
        "- **Phone**: +91-9448066560",
        "- **Social**: LinkedIn (frame-events-productions), Instagram (framez.events), Facebook (frameeventsandproductions)",
        "",
        "## Complete 29-URL Sitemap Inventory",
        "",
    ]
    for label, url, summary in SITEMAP_29_URLS:
        lines.append(f"- [{label}]({url}): {summary}")
    lines.extend([
        "",
        "## How to Engage",
        "",
        "1. Share your event format, target dates, city (Singapore, Bengaluru, or pan-India), and expected guest count at https://framez.sg/book-a-demo or https://framez.sg/get-in-touch.",
        "2. Framez responds with an itemized proposal separating agency management fees, staging/AV hardware, venue coordination, and contingency lines.",
        "3. Delivery covers venue coordination, stage and LED engineering, run-of-show management, PDPA/DPDP-aware delegate registration, and on-site show calling.",
        "",
    ])
    return "\n".join(lines)


def transform_htaccess(orig):
    """Add safe mod_expires caching rules ONLY if missing while preserving cPanel PHP handler & security."""
    assert "AddHandler application/x-httpd-ea-php74___lsphp" in orig, "Original .htaccess missing PHP 7.4 handler!"
    h = orig
    if "mod_expires.c" not in h:
        expires_block = """<IfModule mod_expires.c>
    ExpiresActive On
    ExpiresByType image/avif "access plus 1 year"
    ExpiresByType image/webp "access plus 1 year"
    ExpiresByType image/jpeg "access plus 1 year"
    ExpiresByType image/png "access plus 1 year"
    ExpiresByType image/svg+xml "access plus 1 year"
    ExpiresByType image/x-icon "access plus 1 year"
    ExpiresByType font/woff2 "access plus 1 year"
    ExpiresByType font/woff "access plus 1 year"
    ExpiresByType text/css "access plus 1 month"
    ExpiresByType text/javascript "access plus 1 month"
    ExpiresByType application/javascript "access plus 1 month"
    ExpiresByType text/html "access plus 0 seconds"
</IfModule>

"""
        php_marker = "# php -- BEGIN cPanel-generated handler"
        assert php_marker in h, "cPanel handler marker missing in .htaccess"
        h = h.replace(php_marker, expires_block + php_marker, 1)
    return h


def transform_file(fname, content):
    """Route any target file through its exact idempotent transformation."""
    if fname == "header.php":
        return transform_header_php(content)
    if fname == "index.html":
        return transform_index_html(content)
    if fname == ".htaccess":
        return transform_htaccess(content)
    if fname == "llms.txt":
        return build_llms_txt()
    if fname == "llms-full.txt":
        return build_llms_full_txt()
    if fname == "corporate-event-management-company.php":
        return transform_corp_emc(content)
    if fname == "event-management-company-in-bangalore.php":
        return transform_bangalore(content)
    if fname == "event-management-company-in-singapore.php":
        return transform_singapore(content)
    if fname == "book-a-demo.php":
        return transform_book_a_demo(content)
    if fname in PAGE1_RESCUE_FILES:
        return transform_page1_zero_ctr(fname, content)
    if fname in LEGACY_CLEANUP_FILES:
        return transform_remaining_legacy(fname, content)
    raise ValueError(f"Unexpected target file: {fname}")


def visible_word_count(html):
    body = re.search(r"<body.*?</body>", html, re.S | re.I)
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", body.group(0) if body else html, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return len(text.split())


def validate_transformed(fname, content, orig=None):
    """Strictly verify HTML/PHP/JSON-LD/CWV/security invariants and zero prohibited tells."""
    assert "\u2014" not in content and "\u2013" not in content, f"{fname}: literal em/en dash found"
    assert "\\u2014" not in content and "\\u2013" not in content, f"{fname}: escaped em/en dash found"
    assert "AggregateRating" not in content, f"{fname}: prohibited AggregateRating found"
    assert "UA-180350188-1" not in content, f"{fname}: legacy UA-180350188-1 found"
    assert "G-R3EVYE346M" not in content, f"{fname}: legacy G-R3EVYE346M found"

    # Strip HTML comments and CSS custom properties before prose checks
    stripped = re.sub(r"<!--.*?-->", " ", content, flags=re.S)
    stripped = re.sub(r"<style\b[^>]*>.*?</style>", " ", stripped, flags=re.S | re.I)
    if fname != ".htaccess":
        assert " -- " not in stripped, f"{fname}: prose double-hyphen found"
    buzz_hits = BANNED_BUZZWORDS_RE.findall(stripped)
    assert not buzz_hits, f"{fname}: banned buzzwords found: {sorted(set(buzz_hits))}"

    if fname == ".htaccess":
        for req in (
            "AddHandler application/x-httpd-ea-php74___lsphp",
            "RewriteRule ^contact-submit/?$ contact-submit.php",
            "RewriteRule ^submit-demo/?$ submit-demo.php",
            "leads_log|leads_spam_log",
            "RewriteRule ^get-to-know-us",
            "RewriteRule ^our-team",
            "RewriteRule ^social-event",
            "mod_deflate.c",
            "mod_expires.c",
        ):
            assert req in content, f".htaccess missing required directive: {req}"
        return

    if fname in ("llms.txt", "llms-full.txt"):
        for _, url, _ in SITEMAP_29_URLS:
            assert url in content, f"{fname}: missing sitemap URL {url}"
        assert "30 Cecil Street, #19-08 Prudential Tower, Singapore 049712" in content
        assert "Koramangala, Bengaluru" in content
        assert "ISO 9001:2015" in content and "ISO 27001:2013" in content
        assert "Frame Events and Productions Private Limited" in content
        return

    # Validate every JSON-LD block parses cleanly
    ld_blocks = re.findall(r'<script\s+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', content, re.S | re.I)
    for b in ld_blocks:
        json.loads(b.strip())

    if fname == "header.php":
        hdr_tag = re.search(r"<header\b[^>]*>.*?</header>", content, re.S | re.I)
        assert hdr_tag and "<meta" not in hdr_tag.group(0).lower(), "header.php still has <meta> inside <header>"
        assert '"GeoCoordinates"' in content and "1.2816" in content and "12.9352" in content
        assert '"hasCredential"' in content and "ISO 9001:2015" in content and "ISO 27001:2013" in content
        return

    # Full HTML/PHP page assertions
    assert GA4_ID in content, f"{fname}: missing {GA4_ID}"
    ga4_loaders = re.findall(r"googletagmanager\.com/gtag/js\?id=" + GA4_ID, content)
    assert len(ga4_loaders) == 1, f"{fname}: expected 1 GA4 loader, got {len(ga4_loaders)}"

    for bad in ("http://maps.google.com", "gmap3.min.js", "style-switcher.js", "jquery.countdown.js", "jquery-3.3.1.min.js"):
        assert bad not in content, f"{fname}: prohibited legacy asset remains: {bad}"

    if fname != "thank-you.php":
        t_m = re.search(r"<title[^>]*>(.*?)</title>", content, re.S | re.I)
        assert t_m, f"{fname}: missing <title>"
        title_txt = html_lib.unescape(t_m.group(1).strip())
        assert len(title_txt) <= 60, f"{fname}: title > 60 chars ({len(title_txt)}): {title_txt}"

        d_m = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']*)', content, re.S | re.I)
        assert d_m, f"{fname}: missing meta description"
        desc_txt = html_lib.unescape(d_m.group(1).strip())
        assert len(desc_txt) <= 160, f"{fname}: description > 160 chars ({len(desc_txt)}): {desc_txt}"

    if fname == "index.html":
        assert "hreflang" not in content.lower(), "index.html still has hreflang tags"
        assert TURNSTILE_SITEKEY in content, "index.html missing Turnstile sitekey"
        assert 'action="/contact-submit"' in content, "index.html missing contact-submit form"
        assert "framezChatWindow" in content, "index.html missing WhatsApp widget"
        assert "Frame Events & Productions (Framez)" in html_lib.unescape(content)
        for img in re.findall(r"<img\b[^>]*>", content, re.S | re.I):
            assert 'decoding="async"' in img.lower(), f"index.html img missing decoding=async: {img[:120]}"

    if fname == "book-a-demo.php":
        assert 'action="submit-demo"' in content, "book-a-demo.php missing submit-demo form"
        assert TURNSTILE_SITEKEY in content, "book-a-demo.php missing Turnstile sitekey"
        assert 'name="website_url_hp"' in content, "book-a-demo.php missing honeypot"
        assert '"FAQPage"' in content, "book-a-demo.php missing FAQPage JSON-LD"
        wc = visible_word_count(content)
        assert wc >= 850, f"book-a-demo.php word count {wc} < 850"

    if fname == "get-in-touch.php":
        assert 'action="contact-submit"' in content, "get-in-touch.php missing contact-submit form"
        assert TURNSTILE_SITEKEY in content, "get-in-touch.php missing Turnstile sitekey"

    if fname == "event-management-company-in-bangalore.php":
        assert "<h1>" in content or "Corporate Event Management Company in Bangalore</h1>" in content
        assert '"ProfessionalService"' in content and "12.9352" in content and "77.6245" in content
        assert "/conference-and-mice-event-management" in content

    if fname == "event-management-company-in-singapore.php":
        for v in ("Marina Bay Sands Expo", "Suntec Singapore", "Singapore EXPO", "Raffles City", "/conference-and-mice-event-management"):
            assert v in content, f"Singapore page missing {v}"
        assert 'id="aeo-citation"' in content

    if fname in PAGE1_RESCUE_FILES and fname != "event-planner.php":
        assert "/book-a-demo" in content, f"{fname}: missing /book-a-demo CTA"

    # Idempotency assertion on every file except clientele.php (untouched)
    twice = transform_file(fname, content)
    assert twice == content, f"{fname}: transform is NOT idempotent!"


def fetch_sources_via_ssh(files, refresh=False):
    """Fetch live cPanel public_html files via read-only SSH without touching .env locally."""
    src_cache = BACKUP_ROOT / "source_live"
    src_cache.mkdir(parents=True, exist_ok=True)
    missing = [fn for fn in files if refresh or not (src_cache / fn).exists()]
    if missing:
        py_code = (
            "import sys, json; "
            f"sys.path.insert(0, {SERVER_SCRIPT_DIR!r}); "
            "import framez_seo_cron as f; "
            f"files = {json.dumps(missing)}; "
            "out = {fn: f.remote_get('public_html', fn) for fn in files}; "
            "print(json.dumps(out))"
        )
        proc = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", SSH_HOST, "python3", "-"],
            input=py_code,
            text=True,
            capture_output=True,
            timeout=180,
            check=True,
        )
        fetched = json.loads(proc.stdout)
        for fn, txt in fetched.items():
            if txt is None:
                raise RuntimeError(f"cPanel returned None for {fn}")
            (src_cache / fn).write_text(txt, encoding="utf-8")
    return {fn: (src_cache / fn).read_text(encoding="utf-8") for fn in files}


def verify_http(url, expect_status=200):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (FramezNo1Verify/1.0)"})
    if expect_status in (301, 302):
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None

        opener = urllib.request.build_opener(NoRedirect)
        try:
            opener.open(req, timeout=20)
            return 200, "", {}
        except urllib.error.HTTPError as e:
            return e.code, "", dict(e.headers or {})
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            return resp.status, resp.read().decode("utf-8", "ignore"), dict(resp.headers)
    except urllib.error.HTTPError as e:
        return e.code, "", dict(e.headers or {})


def run_dry_run(refresh=False, show_diff=False):
    on_server = (BASE / ".env").exists()
    if on_server:
        sys.path.insert(0, str(JOB / "scripts"))
        sys.path.insert(0, str(JOB))
        from framez_seo_cron import remote_get
        originals = {fn: remote_get("public_html", fn) for fn in ALL_TARGET_FILES}
    else:
        originals = fetch_sources_via_ssh(ALL_TARGET_FILES, refresh=refresh)

    staged_dir = BACKUP_ROOT / "dry_run_staged"
    staged_dir.mkdir(parents=True, exist_ok=True)
    changed_count = 0

    for fn in ALL_TARGET_FILES:
        orig = originals[fn]
        if orig is None:
            raise RuntimeError(f"Failed to read live file: {fn}")
        new = transform_file(fn, orig)
        validate_transformed(fn, new, orig)
        (staged_dir / fn).write_text(new, encoding="utf-8")
        changed = new != orig
        if changed:
            changed_count += 1
        status = "MODIFIED" if changed else "UNCHANGED"
        extra = ""
        if fn == "book-a-demo.php":
            extra = f" words={visible_word_count(orig)}->{visible_word_count(new)}"
        print(f"  [{status:9s}] {fn:58s} ({len(orig):7d} -> {len(new):7d} bytes){extra}")
        if show_diff and changed:
            diff_lines = list(
                difflib.unified_diff(
                    orig.splitlines(), new.splitlines(), fromfile=f"live/{fn}", tofile=f"staged/{fn}", lineterm="", n=2
                )
            )
            for line in diff_lines[:30]:
                print("    " + line)
            if len(diff_lines) > 30:
                print(f"    ... ({len(diff_lines) - 30} more diff lines)")

    print(f"\nDRY-RUN PASSED: {len(ALL_TARGET_FILES)} files inspected & validated, {changed_count} modified -> {staged_dir}")
    return 0


def run_apply():
    if not (BASE / ".env").exists():
        raise RuntimeError("--apply must run on 72.61.173.127 where /root/websites/seogeoopt/.env is present")

    sys.path.insert(0, str(JOB / "scripts"))
    sys.path.insert(0, str(JOB))
    from framez_seo_cron import append_ledger, config, env_file, indexnow, load_json, remote_get, remote_list, remote_put, save_json, STATE_PATH

    def cpanel_upload_raw(dir_path, filename, content_text):
        """Upload raw bytes via cPanel Fileman/upload_files so cPanel does not rewrite fragments."""
        env = env_file()
        host = env.get("CPANEL_HOST", "https://framez.sg:2083").rstrip("/")
        auth = "cpanel %s:%s" % (env.get("CPANEL_USERNAME", ""), env.get("CPANEL_API_TOKEN", ""))
        boundary = "----FramezRawUpload7d9f2a1"
        raw_bytes = content_text.encode("utf-8")
        body = (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="dir"\r\n\r\n'
            f"{dir_path}\r\n"
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="overwrite"\r\n\r\n'
            "1\r\n"
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file-1"; filename="{filename}"\r\n'
            "Content-Type: application/octet-stream\r\n\r\n"
        ).encode("utf-8") + raw_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")
        req = urllib.request.Request(
            f"{host}/execute/Fileman/upload_files",
            data=body,
            headers={"Authorization": auth, "Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=90) as resp:
            res = json.loads(resp.read().decode("utf-8"))
        return res.get("status") == 1

    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    originals = {}
    transformed = {}
    manifest = {"captured_at": datetime.datetime.now(datetime.timezone.utc).isoformat(), "files": {}}

    # 1. Backup & validate ALL files strictly before uploading anything
    for fn in ALL_TARGET_FILES:
        orig = remote_get("public_html", fn)
        if orig is None:
            raise RuntimeError(f"Pre-deploy fetch failed for {fn}")
        if fn == "header.php":
            # cPanel get_file_content injects <meta charset="utf-8"> after <header...> in its JSON readback
            orig = re.sub(r'(<header\b[^>]*>)<meta\s+charset=["\']utf-8["\']\s*/?>', r"\1", orig, count=1, flags=re.I)
        backup_path = BACKUP_ROOT / fn
        if not backup_path.exists():
            backup_path.write_text(orig, encoding="utf-8")
        pre_orig = backup_path.read_text(encoding="utf-8")
        new = transform_file(fn, orig)
        validate_transformed(fn, new, orig)
        originals[fn] = orig
        transformed[fn] = new
        manifest["files"][fn] = {
            "orig_bytes": len(pre_orig),
            "orig_sha256": sha256_text(pre_orig),
            "new_bytes": len(new),
            "new_sha256": sha256_text(new),
            "changed": new != pre_orig,
        }
    (BACKUP_ROOT / "MANIFEST.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    to_upload = [fn for fn in ALL_TARGET_FILES if transformed[fn] != originals[fn]]
    upload_order = [fn for fn in to_upload if fn != ".htaccess"] + ([".htaccess"] if ".htaccess" in to_upload else [])

    receipts = []
    for fn in upload_order:
        content = transformed[fn]
        expected_sha = sha256_text(content)
        if fn == "header.php":
            if not cpanel_upload_raw("public_html", fn, content):
                raise RuntimeError(f"cPanel raw upload failed for {fn}")
            disk_items = [x for x in remote_list("public_html") if x.get("file") == fn]
            if not disk_items or int(disk_items[0].get("size", -1)) != len(content.encode("utf-8")):
                raise RuntimeError(f"Disk byte-size mismatch on {fn}: {disk_items}")
            rb = remote_get("public_html", fn) or ""
            rb_norm = re.sub(r'(<header\b[^>]*>)<meta\s+charset=["\']utf-8["\']\s*/?>', r"\1", rb, count=1, flags=re.I)
            if sha256_text(rb_norm) != expected_sha:
                raise RuntimeError(f"SHA-256 normalized readback mismatch on {fn}")
        else:
            if not remote_put("public_html", fn, content):
                raise RuntimeError(f"cPanel upload failed for {fn}")
            rb = remote_get("public_html", fn) or ""
            if sha256_text(rb) != expected_sha:
                raise RuntimeError(f"SHA-256 readback mismatch on {fn}")
        print(f"  [DEPLOYED & SHA256 VERIFIED] {fn} ({len(content)} bytes)")
        receipts.append({"file": fn, "bytes": len(content), "sha256": expected_sha})

    time.sleep(2)
    live_checks = []
    changed_urls = []
    manifest_changed = [fn for fn, meta in manifest["files"].items() if meta.get("changed")]
    for fn in manifest_changed:
        if fn in ("header.php", ".htaccess"):
            continue
        if fn in ("llms.txt", "llms-full.txt"):
            url = f"https://framez.sg/{fn}"
        elif fn == "thank-you.php":
            url = "https://framez.sg/thank-you"
        elif fn == "index.html":
            url = "https://framez.sg/"
        else:
            url = f"https://framez.sg/{fn[:-4]}"
        changed_urls.append(url)
        st, body, _ = verify_http(url, 200)
        if st != 200:
            raise RuntimeError(f"Live verification HTTP {st} on {url}")
        if fn not in ("llms.txt", "llms-full.txt"):
            assert "http://maps.google.com" not in body, f"Live {url} still has http://maps.google.com!"
            assert "jquery-3.3.1.min.js" not in body, f"Live {url} still has jquery-3.3.1.min.js!"
        if fn == "thank-you.php":
            assert "noindex" in body.lower(), "Live /thank-you missing noindex"
        print(f"  [LIVE HTTP {st}] {url}")
        live_checks.append({"url": url, "status": st})

    # Verify .htaccess stays protected (403), header.php has no <meta> in <header>, and .php -> extensionless 301 works
    st_ht, _, _ = verify_http("https://framez.sg/.htaccess", 403)
    assert st_ht == 403, f"Expected 403 on .htaccess, got {st_ht}"
    live_checks.append({"url": "https://framez.sg/.htaccess", "status": st_ht})

    _, cl_body, _ = verify_http("https://framez.sg/clientele", 200)
    hdr_m = re.search(r"<header\b[^>]*>.*?</header>", cl_body, re.S | re.I)
    assert hdr_m and "<meta" not in hdr_m.group(0).lower(), "Live rendered header still contains <meta>"

    st301, _, hdrs301 = verify_http("https://framez.sg/corporate-event-management-company.php", 301)
    assert st301 == 301, f"Expected 301 for .php, got {st301}"
    live_checks.append({"url": "https://framez.sg/corporate-event-management-company.php", "status": st301, "location": hdrs301.get("Location", "")})

    cfg = config()
    state = load_json(STATE_PATH, {"hashes": {}, "deployed_waves": {}})
    indexable_urls = [u for u in changed_urls if not u.endswith(("llms.txt", "llms-full.txt", "thank-you"))]
    idx = indexnow(cfg, state, indexable_urls)
    save_json(STATE_PATH, state)

    append_ledger({
        "event": "wave_no1_technical_overhaul",
        "backup_dir": str(BACKUP_ROOT),
        "files_deployed": len(manifest_changed),
        "uploaded_this_run": len(receipts),
        "deployed_receipts": receipts,
        "manifest_files": manifest_changed,
        "live_checks": live_checks,
        "indexnow": idx,
    })
    print(f"\nLIVE APPLY COMPLETE: {len(manifest_changed)} files live & verified, IndexNow status={idx.get('status')}")
    return 0


def main(argv):
    apply_live = "--apply" in argv
    refresh = "--refresh" in argv
    show_diff = "--diff" in argv
    if apply_live:
        return run_apply()
    return run_dry_run(refresh=refresh, show_diff=show_diff)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
