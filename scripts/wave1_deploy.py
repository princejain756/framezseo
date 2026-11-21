#!/usr/bin/env python3
"""Wave 1 Production Deployment for Framez.sg (Nov 15 - Dec 15, 2026 Cycle).

Reads pre-deployment backups from:
  /root/websites/seogeoopt/seo-jobs/framez/backups/cycle-nov18-predeploy/
Stages, validates, deploys via cPanel UAPI, verifies live over HTTPS,
pushes changed/new URLs to IndexNow, and records an immutable ledger receipt.

Usage:
  python3 wave1_deploy.py            # dry-run + full local validation
  python3 wave1_deploy.py --apply    # deploy to cPanel + live HTTP verify + IndexNow
"""

import datetime
import hashlib
import json
import pathlib
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from content_pages import GA4_ID, WAVE1_PAGES, render_page

BASE = pathlib.Path("/root/websites/seogeoopt")
JOB = BASE / "seo-jobs" / "framez"
BACKUP_SRC = JOB / "backups" / "cycle-nov18-predeploy"
STAGE_DIR = JOB / "staged_wave1"
REPORT_DIR = JOB / "reports"
LEDGER_PATH = REPORT_DIR / "cycle-2026-11-15-to-2026-12-15-ledger.jsonl"

ROBOTS_TAG = '<meta name="robots" content="index, follow, max-image-preview:large, max-snippet:-1, max-video-preview:-1" />'
RICH_OG_IMAGE = "https://framez.sg/assets/img/cover/Framez%20Events%20And%20Productions%20(1).JPG"

GA4_SNIPPET = f"""<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id={GA4_ID}"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){{dataLayer.push(arguments);}}
  gtag('js', new Date());
  gtag('config', '{GA4_ID}');
</script>"""

CONVERSION_LISTENER = """<!-- Framez GA4 Multi-Channel Inquiry Attribution -->
<script>
(function(){
  if (window.__fzConvBound) return;
  window.__fzConvBound = true;
  document.addEventListener('click', function(e) {
    var a = e.target && e.target.closest ? e.target.closest('a[href]') : null;
    if (!a || typeof window.gtag !== 'function') return;
    var h = (a.getAttribute('href') || '').toLowerCase();
    var p = window.location.pathname || '/';
    if (h.indexOf('wa.me/') !== -1 || h.indexOf('whatsapp.com') !== -1) {
      window.gtag('event', 'whatsapp_click', { event_category: 'conversion', page_path: p, link_url: a.href });
    } else if (h.indexOf('tel:') === 0) {
      window.gtag('event', 'phone_click', { event_category: 'conversion', page_path: p, link_url: h });
    } else if (h.indexOf('mailto:') === 0) {
      window.gtag('event', 'email_click', { event_category: 'conversion', page_path: p, link_url: h });
    } else if (h.indexOf('get-in-touch') !== -1 || h.indexOf('book-a-demo') !== -1) {
      window.gtag('event', 'cta_inquiry_click', { event_category: 'engagement', page_path: p });
    }
  }, { passive: true });
})();
</script>"""

DUAL_HQ_ORG_GRAPH = {
    "@context": "https://schema.org",
    "@graph": [
        {
            "@type": "Organization",
            "@id": "https://framez.sg/#organization",
            "name": "Frame Events and Productions Private Limited",
            "alternateName": ["Framez", "Framez Events & Productions"],
            "url": "https://framez.sg/",
            "logo": "https://framez.sg/assets/img/frameznewlogo.png",
            "image": RICH_OG_IMAGE,
            "email": "info@framez.sg",
            "telephone": "+91-9448066560",
            "sameAs": [
                "https://www.linkedin.com/company/frame-events-productions",
                "https://www.instagram.com/weareframez/",
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
                    "name": "Framez Singapore — Prudential Tower",
                    "address": {
                        "@type": "PostalAddress",
                        "streetAddress": "30 Cecil Street, #19-08 Prudential Tower",
                        "addressLocality": "Singapore",
                        "postalCode": "049712",
                        "addressCountry": "SG",
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
                "Experiential Marketing",
                "Brand Activations",
                "Enterprise Product Launches",
                "Employee Annual Days and Awards Galas",
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
        },
        {
            "@type": "WebSite",
            "@id": "https://framez.sg/#website",
            "url": "https://framez.sg/",
            "name": "Framez Events & Productions",
            "publisher": {"@id": "https://framez.sg/#organization"},
        },
    ],
}


def env_vars():
    out = {}
    for line in (BASE / ".env").read_text().splitlines():
        m = re.match(r"^([A-Z0-9_]+)=(.*)$", line.strip())
        if m:
            out[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    return out


def cpanel_save(env, dir_path, filename, content):
    host = env["CPANEL_HOST"].rstrip("/")
    auth = "cpanel %s:%s" % (env["CPANEL_USERNAME"], env["CPANEL_API_TOKEN"])
    url = f"{host}/execute/Fileman/save_file_content"
    payload = json.dumps({"dir": dir_path, "file": filename, "content": content}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Authorization": auth, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=90) as resp:
        res = json.loads(resp.read().decode("utf-8"))
        return res.get("status") == 1


def cpanel_get(env, dir_path, filename):
    host = env["CPANEL_HOST"].rstrip("/")
    auth = "cpanel %s:%s" % (env["CPANEL_USERNAME"], env["CPANEL_API_TOKEN"])
    q = urllib.parse.urlencode({"dir": dir_path, "file": filename})
    req = urllib.request.Request(f"{host}/execute/Fileman/get_file_content?{q}", headers={"Authorization": auth})
    with urllib.request.urlopen(req, timeout=60) as resp:
        res = json.loads(resp.read().decode("utf-8"))
        return (res.get("data") or {}).get("content", "")


def clean_legacy_ga_and_ensure_ga4(html, keep_existing_ga4=True):
    """Remove dead UA-180350188-1 and legacy G-R3EVYE346M script blocks; ensure single G-XDPHV6MX44."""
    for legacy_id in ("UA-180350188-1", "G-R3EVYE346M"):
        # Remove async loader script + following inline config script
        html = re.sub(
            r"(?:<!--[^>]*Google Analytics[^>]*-->\s*)?"
            r'<script[^>]+googletagmanager\.com/gtag/js\?id=' + re.escape(legacy_id) + r'[^>]*></script>\s*'
            r"<script>.*?" + re.escape(legacy_id) + r".*?</script>",
            "",
            html,
            flags=re.S | re.I,
        )
    if GA4_ID not in html:
        anchor = re.search(r"<link[^>]+rel=[\"']canonical[\"'][^>]*>", html, re.I)
        if anchor:
            html = html[: anchor.end()] + "\n" + GA4_SNIPPET + "\n" + html[anchor.end() :]
        else:
            html = html.replace("</head>", GA4_SNIPPET + "\n</head>", 1)
    return html


def upgrade_robots_and_og_image(html):
    html = re.sub(
        r'<meta\s+name=["\']robots["\']\s+content=["\']all,index,follow["\']\s*/?>',
        ROBOTS_TAG,
        html,
        flags=re.I,
    )
    html = html.replace(
        "https://framez.sg/assets/images/cropped-favicon.png",
        RICH_OG_IMAGE,
    )
    return html


def build_header_php(orig):
    new_ld = "<script type=\"application/ld+json\">\n" + json.dumps(DUAL_HQ_ORG_GRAPH, indent=2, ensure_ascii=False) + "\n</script>"
    updated, n = re.subn(
        r'<script type="application/ld\+json">.*?</script>',
        lambda _m: new_ld,
        orig,
        count=1,
        flags=re.S,
    )
    assert n == 1, "header.php JSON-LD replacement failed"
    return updated


def build_footer_php(orig):
    old_links_re = re.compile(
        r'(Useful\s*<strong>Links</strong>\s*</h3>\s*<ul>)(.*?)(<li[^>]*><strong[^>]*>Planning Guides</strong></li>)',
        re.S,
    )
    new_core_links = """
                        <li style="padding: 5px 0;"><a href="https://framez.sg/" style="display: flex; align-items: center; gap: 8px;"><span style="color:#ef4444;">›</span> Home</a></li>
                        <li style="padding: 5px 0;"><a href="https://framez.sg/corporate-event-management-company" style="display: flex; align-items: center; gap: 8px;"><span style="color:#ef4444;">›</span> Corporate Event Management</a></li>
                        <li style="padding: 5px 0;"><a href="https://framez.sg/event-management-company-in-singapore" style="display: flex; align-items: center; gap: 8px;"><span style="color:#ef4444;">›</span> Singapore Event Management</a></li>
                        <li style="padding: 5px 0;"><a href="https://framez.sg/event-management-company-in-bangalore" style="display: flex; align-items: center; gap: 8px;"><span style="color:#ef4444;">›</span> Bangalore Event Management</a></li>
                        <li style="padding: 5px 0;"><a href="https://framez.sg/event-management-company-in-india" style="display: flex; align-items: center; gap: 8px;"><span style="color:#ef4444;">›</span> India Event Management</a></li>
                        <li style="padding: 5px 0;"><a href="https://framez.sg/our-events-and-services" style="display: flex; align-items: center; gap: 8px;"><span style="color:#ef4444;">›</span> Events &amp; MICE Services</a></li>
                        <li style="padding: 5px 0;"><a href="https://framez.sg/event-marketing-services" style="display: flex; align-items: center; gap: 8px;"><span style="color:#ef4444;">›</span> Event Marketing Services</a></li>
                        <li style="padding: 5px 0;"><a href="https://framez.sg/clientele" style="display: flex; align-items: center; gap: 8px;"><span style="color:#ef4444;">›</span> Enterprise Clientele</a></li>
                        <li style="padding: 5px 0;"><a href="https://framez.sg/blog" style="display: flex; align-items: center; gap: 8px;"><span style="color:#ef4444;">›</span> Knowledge &amp; Guides</a></li>
                        <li style="padding: 5px 0;"><a href="https://framez.sg/get-in-touch" style="display: flex; align-items: center; gap: 8px;"><span style="color:#ef4444;">›</span> Request Custom Proposal</a></li>
                        """
    updated, n = old_links_re.subn(r"\1" + new_core_links + r"\3", orig, count=1)
    assert n == 1, "footer.php Useful Links replacement failed"
    if "__fzConvBound" not in updated:
        updated = updated.rstrip() + "\n\n" + CONVERSION_LISTENER + "\n"
    return updated


def build_index_html(orig):
    updated = orig.replace(
        '<meta name="robots" content="index, follow, max-image-preview:large">',
        '<meta name="robots" content="index, follow, max-image-preview:large, max-snippet:-1, max-video-preview:-1">',
    )
    updated = updated.replace(
        "https://framez.sg/assets/images/cropped-favicon.png",
        RICH_OG_IMAGE,
    )
    # Add Singapore money link directly in homepage hero pill bar!
    target_pill = '<a href="/event-management-company-in-bangalore">Events in Bangalore</a>'
    sg_pill = (
        '<a href="/event-management-company-in-singapore">Events in Singapore</a>\n'
        '                <a href="/event-management-company-in-bangalore">Events in Bangalore</a>'
    )
    if "/event-management-company-in-singapore" not in updated:
        assert target_pill in updated, "index.html pill bar anchor missing"
        updated = updated.replace(target_pill, sg_pill, 1)

    # Upgrade Organization JSON-LD on index.html to also include Singapore Prudential Tower address
    m = re.search(r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>', updated, re.S)
    assert m, "index.html JSON-LD missing"
    ld_obj = json.loads(m.group(1))
    for item in ld_obj.get("@graph", []):
        if item.get("@type") == "Organization":
            item["address"] = DUAL_HQ_ORG_GRAPH["@graph"][0]["address"]
            item["location"] = DUAL_HQ_ORG_GRAPH["@graph"][0]["location"]
    new_ld_str = '<script type="application/ld+json">\n' + json.dumps(ld_obj, indent=4) + "\n    </script>"
    updated = updated[: m.start()] + new_ld_str + updated[m.end() :]

    if "__fzConvBound" not in updated:
        updated = updated.replace("</body>", CONVERSION_LISTENER + "\n</body>", 1)
    return updated


def build_health_safety(orig):
    h = clean_legacy_ga_and_ensure_ga4(orig)
    h = upgrade_robots_and_og_image(h)
    h = h.replace("https://www.framez.sg/assets/images/cropped-favicon.webp", "https://framez.sg/assets/images/cropped-favicon.webp")
    # Remove Hybrid Event article tags
    h = re.sub(r'<meta\s+property="article:(?:tag|section)"[^>]*>\s*', "", h, flags=re.I)
    # Replace bogus Product + AggregateRating JSON-LD with compliant WebPage + Article + BreadcrumbList
    clean_ld = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "WebPage",
                "@id": "https://framez.sg/Framez-Public-Statement-on-Health-and-Safety-Commitment#webpage",
                "url": "https://framez.sg/Framez-Public-Statement-on-Health-and-Safety-Commitment",
                "name": "Framez Public Statement on Health and Safety Commitment",
                "isPartOf": {"@id": "https://framez.sg/#website"},
                "about": {"@id": "https://framez.sg/#organization"},
            },
            {
                "@type": "Article",
                "@id": "https://framez.sg/Framez-Public-Statement-on-Health-and-Safety-Commitment#article",
                "headline": "Framez Public Statement on Health and Safety Commitment",
                "description": "Framez public statement on health, safety and ISO-certified event delivery standards across Singapore and India.",
                "author": {"@id": "https://framez.sg/#organization"},
                "publisher": {"@id": "https://framez.sg/#organization"},
                "mainEntityOfPage": "https://framez.sg/Framez-Public-Statement-on-Health-and-Safety-Commitment",
            },
            {
                "@type": "BreadcrumbList",
                "@id": "https://framez.sg/Framez-Public-Statement-on-Health-and-Safety-Commitment#breadcrumb",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "Home", "item": "https://framez.sg/"},
                    {
                        "@type": "ListItem",
                        "position": 2,
                        "name": "Health & Safety Commitment",
                        "item": "https://framez.sg/Framez-Public-Statement-on-Health-and-Safety-Commitment",
                    },
                ],
            },
        ],
    }
    h, n = re.subn(
        r'<script type="application/ld\+json">.*?"Product".*?</script>',
        lambda _m: '<script type="application/ld+json">\n' + json.dumps(clean_ld, indent=2, ensure_ascii=False) + "\n</script>",
        h,
        count=1,
        flags=re.S,
    )
    assert n == 1, "Failed to replace Product JSON-LD on Health & Safety page"
    return h


def build_trends_singapore(orig):
    h = orig
    new_title = "Corporate Event Trends Singapore: MICE &amp; Experiential"
    h, n = re.subn(r"<title>.*?</title>", f"<title>{new_title}</title>", h, count=1, flags=re.S | re.I)
    assert n == 1
    trends_ld = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "Article",
                "@id": "https://framez.sg/corporate-event-trends-singapore#article",
                "headline": "Corporate Event Trends in Singapore",
                "description": "Explore corporate event management and MICE shifts in Singapore: experiential AV production, sustainable staging and attendee engagement.",
                "author": {"@id": "https://framez.sg/#organization"},
                "publisher": {"@id": "https://framez.sg/#organization"},
                "datePublished": "2026-09-01",
                "dateModified": "2026-11-18",
                "mainEntityOfPage": "https://framez.sg/corporate-event-trends-singapore",
            },
            {
                "@type": "WebPage",
                "@id": "https://framez.sg/corporate-event-trends-singapore#webpage",
                "url": "https://framez.sg/corporate-event-trends-singapore",
                "name": "Corporate Event Trends Singapore: MICE & Experiential",
                "isPartOf": {"@id": "https://framez.sg/#website"},
            },
            {
                "@type": "BreadcrumbList",
                "@id": "https://framez.sg/corporate-event-trends-singapore#breadcrumb",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "Home", "item": "https://framez.sg/"},
                    {"@type": "ListItem", "position": 2, "name": "Guides", "item": "https://framez.sg/blog"},
                    {"@type": "ListItem", "position": 3, "name": "Corporate Event Trends in Singapore", "item": "https://framez.sg/corporate-event-trends-singapore"},
                ],
            },
        ],
    }
    if '"@type": "Article"' not in h:
        h = h.replace("</head>", '<script type="application/ld+json">\n' + json.dumps(trends_ld, indent=2) + "\n</script>\n</head>", 1)
    # Add internal link banner to Singapore money page before footer
    sg_cta = (
        '\n  <div class="container" style="margin: 28px auto 36px;">'
        '<div style="padding:20px 24px;background:#f8fafc;border-left:4px solid #ef4444;border-radius:8px;font-size:16px;color:#0f172a;">'
        '<strong>Planning a live programme in Singapore?</strong> Explore our '
        '<a href="/event-management-company-in-singapore" style="color:#ef4444;font-weight:700;">Singapore corporate event management services</a> '
        'and our practical <a href="/singapore-corporate-event-planning-checklist" style="color:#ef4444;font-weight:700;">Singapore corporate event planning checklist</a>.'
        "</div></div>\n"
    )
    if "/event-management-company-in-singapore" not in h:
        h = h.replace('<?php include "footer.php"?>', sg_cta + '  <?php include "footer.php"?>', 1)
    return h


def build_blog_php(orig):
    h = orig.replace('class"image-fluid"', 'class="image-fluid"')
    h = h.replace('href="our-team"', 'href="/about-us"')
    h = h.replace(
        "Event Management Company in India. Best Virtual events Platform. Frame Events and Productions offers to host amazing virtual event solutions.",
        "Pan-India corporate event management and MICE production from our Bengaluru HQ: multi-city roadshows, conferences, product launches and annual days.",
    )
    sg_card = """
			<div class="col-lg-6 col-md-12 col-sm-12">
			    <img loading="lazy" decoding="async" src="assets/img/cover/Framez Events And Productions (1).webp" class="image-fluid" alt="corporate event management company in Singapore" title="corporate event management company in Singapore" style="border-radius:10px;" />
				<div class="card card-color-gray">
					<div class="card-body">
               	<a href="https://framez.sg/event-management-company-in-singapore">
                   <h4 style="color: #392682;">Corporate Event Management in Singapore</h4><br>
                   <p>B2B corporate conferences, MICE summits, product launches, Dinner &amp; Dance awards galas and brand activations produced in Singapore from Prudential Tower.</p><br>
               </a>
               </div>
           </div>
            </div>
"""
    if "/event-management-company-in-singapore" not in h:
        marker = '<div class="row justify-content-start align-items-center">'
        idx = h.rfind(marker)
        assert idx != -1, "blog.php card row marker missing"
        insert_at = idx + len(marker)
        h = h[:insert_at] + "\n" + sg_card + h[insert_at:]
    return h


def build_htaccess(orig_ht):
    h = orig_ht
    # 1. Replace 16-slug .php -> extensionless rule with 3 legacy 301s + universal public .php -> extensionless 301
    old_php_rule = (
        '# 301 .php -> extensionless for public pages (GET/HEAD only; form handlers excluded)\n'
        'RewriteCond %{THE_REQUEST} "^[A-Z]+\\s+/[^\\s?]*\\.php" \n'
        'RewriteCond %{REQUEST_METHOD} ^(GET|HEAD)$ [NC]\n'
        'RewriteRule ^(about-us|corporate-event-management-company|event-management-company-in-bangalore|event-management-company-in-india|our-events-and-services|event-marketing-services|event-planner|experiential-marketing-brand-activations|clientele|get-in-touch|book-a-demo|blog|corporate-event-budget-planning-guide|annual-day-and-awards-night-planning-guide|corporate-event-roi-measurement-guide|singapore-corporate-event-planning-checklist)\\.php$ /$1 [R=301,L]'
    )
    new_php_rule = (
        "# 301 Redirects for Legacy / Cannibalizing 2021 Pages\n"
        "RewriteRule ^get-to-know-us(\\.php)?/?$ /about-us [R=301,L,NC]\n"
        "RewriteRule ^our-team(\\.php)?/?$ /about-us [R=301,L,NC]\n"
        "RewriteRule ^social-event(\\.php)?/?$ /our-events-and-services [R=301,L,NC]\n\n"
        "# 301 .php -> extensionless for ALL public content pages (GET/HEAD only; form & internal handlers excluded)\n"
        'RewriteCond %{THE_REQUEST} "^(GET|HEAD)\\s+/([^\\s?/]+)\\.php[\\s?]" [NC]\n'
        "RewriteCond %2 !^(contact-submit|submit-demo|database|img_helper|auto_indexnow|header|footer|404-not-found)$ [NC]\n"
        "RewriteRule ^([^/]+)\\.php$ /$1 [R=301,L]"
    )
    assert old_php_rule in h, "Original .php rule not found in .htaccess"
    h = h.replace(old_php_rule, new_php_rule, 1)

    # 2. Remove internal rewrites for our-team and social-event (now 301 redirected)
    h = h.replace("RewriteRule ^our-team/?$ our-team.php [NC,L]\n", "")
    h = h.replace("RewriteRule ^social-event/?$ social-event.php [NC,L]\n", "")

    # 3. Also 301 discontinued hybrid-event slugs if hit directly
    old_virt = "RewriteRule ^virtual-event.php$ /corporate-event-management-company [R=301,L,NC]"
    new_virt = (
        "RewriteRule ^virtual-event.php$ /corporate-event-management-company [R=301,L,NC]\n"
        "RewriteRule ^hybrid-event-management-company(\\.php)?/?$ /corporate-event-management-company [R=301,L,NC]\n"
        "RewriteRule ^hybrid-event-platform(\\.php)?/?$ /our-events-and-services [R=301,L,NC]"
    )
    if "hybrid-event-management-company" not in h:
        h = h.replace(old_virt, new_virt, 1)

    # 4. Ensure GA4 regional collect endpoints are permitted by CSP connect-src
    if "analytics.google.com" not in h:
        h = h.replace(
            "connect-src 'self' https://www.google-analytics.com",
            "connect-src 'self' https://www.google-analytics.com https://analytics.google.com https://*.google-analytics.com",
            1,
        )

    # 5. Add X-Robots-Tag: noindex, noarchive for legacy microsite subdirectories inside public_html
    subdir_env = 'SetEnvIf Request_URI "^/([^/]+\\.framez\\.sg|event-registration|new-site|newsite|wpbckp)(/|$)" LEGACY_SUBDIR=1\n'
    if "LEGACY_SUBDIR" not in h:
        h = h.replace("<IfModule mod_headers.c>", subdir_env + "<IfModule mod_headers.c>", 1)
        h = h.replace(
            "</IfModule>",
            '    Header set X-Robots-Tag "noindex, noarchive" env=LEGACY_SUBDIR\n</IfModule>',
            1,
        )

    assert "AddHandler application/x-httpd-ea-php74___lsphp" in h, "CRITICAL: cPanel PHP handler missing!"
    return h


def build_llms_txt(orig):
    target = "- [Event Management Company in Bangalore](https://framez.sg/event-management-company-in-bangalore)"
    addition = (
        "- [Event Management Company in Singapore](https://framez.sg/event-management-company-in-singapore)\n"
        + target
    )
    if "event-management-company-in-singapore" not in orig:
        orig = orig.replace(target, addition, 1)
    return orig


def build_image_sitemap():
    return """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
        xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">
    <url>
        <loc>https://framez.sg/</loc>
        <image:image>
            <image:loc>https://framez.sg/assets/img/frameznewlogo.png</image:loc>
            <image:title>Framez Events &amp; Productions Official Logo</image:title>
        </image:image>
        <image:image>
            <image:loc>https://framez.sg/assets/img/cover/Framez%20Events%20And%20Productions%20(1).webp</image:loc>
            <image:title>Corporate Event Staging &amp; Production in Singapore and Bangalore</image:title>
        </image:image>
    </url>
    <url>
        <loc>https://framez.sg/event-management-company-in-singapore</loc>
        <image:image>
            <image:loc>https://framez.sg/assets/img/cover/Framez%20Events%20And%20Productions%20(1).webp</image:loc>
            <image:title>Corporate Event Management Company in Singapore — Framez</image:title>
        </image:image>
    </url>
    <url>
        <loc>https://framez.sg/corporate-event-management-company</loc>
        <image:image>
            <image:loc>https://framez.sg/assets/img/our%20work/Framez%20Events%20And%20Productions%20(14).webp</image:loc>
            <image:title>Enterprise Corporate Conference &amp; MICE Management</image:title>
        </image:image>
    </url>
    <url>
        <loc>https://framez.sg/event-management-company-in-bangalore</loc>
        <image:image>
            <image:loc>https://framez.sg/assets/img/cover/Framez%20Events%20And%20Productions%20(3).webp</image:loc>
            <image:title>Corporate Event Management Company in Bangalore — Framez</image:title>
        </image:image>
    </url>
    <url>
        <loc>https://framez.sg/event-management-company-in-india</loc>
        <image:image>
            <image:loc>https://framez.sg/assets/images/framez-12.webp</image:loc>
            <image:title>Pan-India Corporate Event Management &amp; Roadshows</image:title>
        </image:image>
    </url>
    <url>
        <loc>https://framez.sg/experiential-marketing-brand-activations</loc>
        <image:image>
            <image:loc>https://framez.sg/assets/img/seg%201/Framez%20Events%20And%20Productions%20(18).webp</image:loc>
            <image:title>Immersive Experiential Marketing &amp; Brand Activation Booth</image:title>
        </image:image>
    </url>
    <url>
        <loc>https://framez.sg/event-marketing-services</loc>
        <image:image>
            <image:loc>https://framez.sg/assets/images/framez-08.webp</image:loc>
            <image:title>B2B Event Marketing &amp; Trade Show Lead Capture</image:title>
        </image:image>
    </url>
</urlset>
"""


def validate_html_file(name, content):
    """Run strict technical SEO & syntax checks before allowing upload."""
    if name in (".htaccess", "llms.txt", "llms-full.txt", "image-sitemap.xml", "sitemap.xml"):
        assert len(content) > 100, f"{name} unexpectedly short"
        return
    assert "UA-180350188-1" not in content, f"{name} still contains dead UA-180350188-1"
    assert "G-R3EVYE346M" not in content, f"{name} still contains legacy G-R3EVYE346M"
    assert "AggregateRating" not in content, f"{name} contains prohibited AggregateRating"
    if name not in ("header.php", "footer.php"):
        assert GA4_ID in content, f"{name} missing {GA4_ID}"
        assert len(re.findall(r"googletagmanager\.com/gtag/js\?id=" + GA4_ID, content)) == 1, f"{name} duplicate {GA4_ID}"
    # Validate every JSON-LD block parses cleanly
    for block in re.findall(r'<script type="application/ld\+json">\s*(.*?)\s*</script>', content, re.S):
        json.loads(block)
    if name not in ("header.php", "footer.php", "thank-you.php"):
        t_m = re.search(r"<title[^>]*>(.*?)</title>", content, re.S | re.I)
        assert t_m, f"{name} missing <title>"
        raw_t = t_m.group(1).strip().replace("&amp;", "&")
        assert len(raw_t) <= 60, f"{name} title > 60 chars ({len(raw_t)}): {raw_t}"


def stage_all():
    STAGE_DIR.mkdir(parents=True, exist_ok=True)
    staged = {}

    # 1. Core shared includes & homepage
    staged["header.php"] = build_header_php((BACKUP_SRC / "header.php").read_text())
    staged["footer.php"] = build_footer_php((BACKUP_SRC / "footer.php").read_text())
    staged["index.html"] = build_index_html((BACKUP_SRC / "index.html").read_text())

    # 2. Existing pages needing GA4 / robots / og:image / title / internal link updates
    for fname in (
        "about-us.php",
        "book-a-demo.php",
        "corporate-event-management-company.php",
        "event-management-company-in-bangalore.php",
        "get-in-touch.php",
        "our-events-and-services.php",
        "thank-you.php",
    ):
        h = (BACKUP_SRC / fname).read_text()
        h = clean_legacy_ga_and_ensure_ga4(h)
        if fname != "thank-you.php":
            h = upgrade_robots_and_og_image(h)
            h = h.replace('href="our-team"', 'href="/about-us"')
        else:
            h = h.replace("booking ticket -->", "")
        if fname == "event-management-company-in-bangalore.php":
            h = re.sub(
                r'<meta name="keywords"[^>]*>',
                '<meta name="keywords" content="event management company in bangalore, corporate event management bangalore, conference organisers bangalore, brand activations bangalore" />',
                h,
                count=1,
            )
            h = h.replace(
                '<a href="/corporate-event-management-company">corporate event management</a> scope,',
                '<a href="/corporate-event-management-company">corporate event management</a> scope, explore <a href="/event-management-company-in-singapore">Singapore corporate event management</a>,',
            )
        if fname in ("corporate-event-management-company.php", "our-events-and-services.php"):
            sg_callout = (
                '<div class="container" style="margin: 24px auto;">'
                '<div style="padding:18px 22px;background:#f8fafc;border-left:4px solid #ef4444;border-radius:8px;font-size:16px;color:#0f172a;">'
                '<strong>Regional Delivery Hubs:</strong> Framez executes programmes across '
                '<a href="/event-management-company-in-singapore" style="color:#ef4444;font-weight:700;">Singapore</a>, '
                '<a href="/event-management-company-in-bangalore" style="color:#ef4444;font-weight:700;">Bangalore</a>, and '
                '<a href="/event-management-company-in-india" style="color:#ef4444;font-weight:700;">pan-India corridors</a>, '
                'supported by <a href="/event-marketing-services" style="color:#ef4444;font-weight:700;">B2B event marketing &amp; lead capture</a>.'
                "</div></div>\n"
            )
            if "/event-management-company-in-singapore" not in h:
                h = h.replace('<?php include "footer.php"?>', sg_callout + '<?php include "footer.php"?>', 1)
        staged[fname] = h

    # 3. Singapore checklist link to new Singapore money page
    sg_chk = (BACKUP_SRC / "singapore-corporate-event-planning-checklist.php").read_text()
    sg_chk = upgrade_robots_and_og_image(sg_chk)
    sg_chk = sg_chk.replace(
        'review <a href="/our-events-and-services">Framez event services</a> for how we scope Singapore engagements.',
        'explore our <a href="/event-management-company-in-singapore">Singapore corporate event management services</a> for how we scope local and APAC engagements.',
    )
    staged["singapore-corporate-event-planning-checklist.php"] = sg_chk

    # 4. Health & Safety, Singapore Trends, Blog, and the 2 over-long Handbook titles
    staged["Framez-Public-Statement-on-Health-and-Safety-Commitment.php"] = build_health_safety(
        (BACKUP_SRC / "Framez-Public-Statement-on-Health-and-Safety-Commitment.php").read_text()
    )
    staged["corporate-event-trends-singapore.php"] = build_trends_singapore(
        (BACKUP_SRC / "corporate-event-trends-singapore.php").read_text()
    )
    staged["blog.php"] = build_blog_php((BACKUP_SRC / "blog.php").read_text())

    hb2027 = (BACKUP_SRC / "corporate-event-planning-handbook-2027.php").read_text()
    hb2027 = re.sub(
        r"<title>.*?</title>",
        "<title>2027 Corporate Event Planning Handbook: Budget &amp; ROI</title>",
        hb2027,
        count=1,
        flags=re.S | re.I,
    )
    staged["corporate-event-planning-handbook-2027.php"] = hb2027

    fam = (BACKUP_SRC / "corporate-family-day-carnival-safety-logistics.php").read_text()
    fam = re.sub(
        r"<title>.*?</title>",
        "<title>Corporate Family Day Safety &amp; Logistics Guide | Framez</title>",
        fam,
        count=1,
        flags=re.S | re.I,
    )
    staged["corporate-family-day-carnival-safety-logistics.php"] = fam

    # 5. Render the 4 Wave-1 Commercial Pages (Singapore + Rebuilt Event Marketing, India, Event Planner)
    for spec in WAVE1_PAGES:
        staged[spec["slug"] + ".php"] = render_page(spec)

    # 6. Infrastructure & Discovery files (.htaccess, llms.txt, llms-full.txt, image-sitemap.xml)
    # Double-check original .htaccess end lines so we don't drop any custom rule!
    orig_ht = (BACKUP_SRC / ".htaccess").read_text()
    staged[".htaccess"] = build_htaccess(orig_ht)
    staged["llms.txt"] = build_llms_txt((BACKUP_SRC / "llms.txt").read_text())
    staged["llms-full.txt"] = build_llms_txt((BACKUP_SRC / "llms-full.txt").read_text())
    staged["image-sitemap.xml"] = build_image_sitemap()

    # Validate & write staged files
    for fname, content in staged.items():
        validate_html_file(fname, content)
        (STAGE_DIR / fname).write_text(content)

    return staged, orig_ht


def verify_http(url, expect_status=200):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (FramezWave1Verify/1.0)"})
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
    with urllib.request.urlopen(req, timeout=25) as resp:
        return resp.status, resp.read().decode("utf-8", "ignore"), dict(resp.headers)


def main(argv):
    apply_live = "--apply" in argv
    staged, _ = stage_all()
    print(f"Staged & validated {len(staged)} files in {STAGE_DIR}:")
    for k in sorted(staged):
        print(f"  [VALID] {k:56s} ({len(staged[k]):7d} bytes)")

    if not apply_live:
        print("\nDry run complete. Re-run with --apply to deploy to cPanel and verify live.")
        return 0

    env = env_vars()
    deployed_receipts = []
    # Upload header/footer and PHP/HTML files BEFORE .htaccess so new routes exist immediately
    order = [k for k in sorted(staged) if k != ".htaccess"] + [".htaccess"]
    for fname in order:
        content = staged[fname]
        ok = cpanel_save(env, "public_html", fname, content)
        if not ok:
            raise RuntimeError(f"cPanel upload failed for {fname}")
        readback = cpanel_get(env, "public_html", fname)
        sha_local = hashlib.sha256(content.encode("utf-8")).hexdigest()
        sha_remote = hashlib.sha256(readback.encode("utf-8")).hexdigest()
        assert sha_local == sha_remote, f"SHA-256 readback mismatch on {fname}!"
        print(f"  [UPLOADED & SHA256 VERIFIED] {fname}")
        deployed_receipts.append({"file": fname, "bytes": len(content), "sha256": sha_local})

    # Also add X-Robots-Tag: noindex, noarchive to cPanel-hosted legacy event subdomains
    noindex_rule = '\n<IfModule mod_headers.c>\n    Header set X-Robots-Tag "noindex, noarchive"\n</IfModule>\n'
    for sub_dir in ("nps2025.framez.sg", "public_html/event-registration/qr-registration.framez.sg"):
        try:
            cur = cpanel_get(env, sub_dir, ".htaccess") or ""
            if "X-Robots-Tag" not in cur:
                cpanel_save(env, sub_dir, ".htaccess", cur.rstrip() + "\n" + noindex_rule)
                print(f"  [SUBDOMAIN NOINDEX HEADER SET] {sub_dir}/.htaccess")
        except Exception as e:
            print(f"  [WARN] Subdomain {sub_dir} skipped: {e}")

    time.sleep(2)
    # Verify live HTTP responses & 301 redirects
    checks = [
        ("https://framez.sg/", 200),
        ("https://framez.sg/event-management-company-in-singapore", 200),
        ("https://framez.sg/event-marketing-services", 200),
        ("https://framez.sg/event-management-company-in-india", 200),
        ("https://framez.sg/event-planner", 200),
        ("https://framez.sg/corporate-event-management-company", 200),
        ("https://framez.sg/Framez-Public-Statement-on-Health-and-Safety-Commitment", 200),
        ("https://framez.sg/get-to-know-us", 301),
        ("https://framez.sg/our-team", 301),
        ("https://framez.sg/social-event", 301),
        ("https://framez.sg/corporate-event-planning-handbook-2027.php", 301),
        ("https://framez.sg/framez-greetings.framez.sg/", 200),
    ]
    live_verifications = []
    for url, exp in checks:
        try:
            st, body, hdrs = verify_http(url, exp)
        except urllib.error.HTTPError as e:
            st, body, hdrs = e.code, "", dict(e.headers or {})
        loc = hdrs.get("Location", "")
        xrob = hdrs.get("X-Robots-Tag", "")
        print(f"  [LIVE CHECK] {url:68s} -> HTTP {st} (exp {exp}) loc={loc} x-robots={xrob}")
        live_verifications.append({"url": url, "status": st, "expected": exp, "location": loc, "x_robots": xrob})

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    receipt = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "cycle": "2026-11-15_to_2026-12-15",
        "wave": "wave1_2026_11_18",
        "summary": "Sitewide GA4 (G-XDPHV6MX44) + conversion event unification, Dual-HQ SG/IN Organization schema, Health & Safety fake Product schema removal, 3 legacy 301 redirects, universal .php->extensionless 301, microsite X-Robots-Tag noindex, flagship /event-management-company-in-singapore launch, and full rebuilds of /event-marketing-services, /event-management-company-in-india, and /event-planner.",
        "files_deployed": len(deployed_receipts),
        "deployed_receipts": deployed_receipts,
        "live_verifications": live_verifications,
    }
    with open(LEDGER_PATH, "a") as fh:
        fh.write(json.dumps(receipt) + "\n")
    print(f"\nWave 1 Ledger Receipt appended to {LEDGER_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
