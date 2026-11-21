#!/usr/bin/env python3
"""DeepSeek v4.1 Flash Daily SEO, GEO and AEO Intelligence Engine for Framez.sg.

Connects to OpenDesign DeepSeek v4.1 Flash (Normal):
  Base URL: https://amr-link.open-design.ai/v1/chat/completions
  Model: deepseek-v4.1-flash (strictly normal, not eco)
  API Key: Read from /root/.commandcode/opendesign-api-key.secret or environment

Ingests:
  - latest-gsc.json (queries, singapore_queries, india_queries, query_page_pairs, pages, countries)
  - latest-ga4.json (sessions, users, engagement, channels, conversion events)
  - latest-audit.json (live URLs, word counts, technical health)
  - latest-geo-audit.json (schema completeness, llms.txt parity, mixed content, jQuery, blocking scripts, image hygiene, Page-1 zero-CTR alerts)
  - latest-leads.json (verified leads, blocked spam)
  - Active wave schedule and roadmap from content_pages.py

Generates:
  - Daily Keyword and Search Intent Analysis (high-impression low-CTR queries)
  - Generative Engine Optimization (GEO) and AEO Citation Opportunities
  - Micro-optimizations for live commercial pages (titles, metas, FAQ schema)
  - Pre-flight semantic guidance for upcoming content wave releases

Persists:
  - reports/latest-deepseek-insights.json
  - reports/deepseek-daily-insights.jsonl (appended daily)
  - reports/deepseek-insights-summary.md
  - Appends to active cycle ledger (reports/cycle-2026-11-15-to-2026-12-15-ledger.jsonl)
"""

import datetime
import json
import os
import pathlib
import re
import sys
import time
import urllib.request

BASE_DIR = pathlib.Path(__file__).resolve().parent
JOB_DIR = BASE_DIR.parent if BASE_DIR.name == "scripts" else BASE_DIR
REPORT_DIR = JOB_DIR / "reports"
ROOT_ENV_PATH = pathlib.Path("/root/websites/seogeoopt/.env")
OPENDESIGN_KEY_FILE = pathlib.Path("/root/.commandcode/opendesign-api-key.secret")

DEFAULT_BASE_URL = "https://amr-link.open-design.ai/v1/chat/completions"
DEFAULT_MODEL = "deepseek-v4.1-flash"


def read_env_file(path):
    out = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip().strip("'\"")
    return out


def get_api_credentials():
    env_vars = {}
    if ROOT_ENV_PATH.exists():
        env_vars = read_env_file(ROOT_ENV_PATH)

    secret_key = None
    if OPENDESIGN_KEY_FILE.exists():
        try:
            secret_key = OPENDESIGN_KEY_FILE.read_text(encoding="utf-8").strip()
        except Exception:
            pass

    api_key = (
        os.environ.get("OPENDESIGN_API_KEY")
        or secret_key
        or env_vars.get("OPENDESIGN_API_KEY")
        or os.environ.get("COMMANDCODE_API_KEY")
        or env_vars.get("COMMANDCODE_API_KEY")
        or ""
    )
    base_url = (
        os.environ.get("OPENDESIGN_BASE_URL")
        or env_vars.get("OPENDESIGN_BASE_URL")
        or DEFAULT_BASE_URL
    )
    if not base_url or "open-design.ai" not in base_url:
        base_url = DEFAULT_BASE_URL
    model = (
        os.environ.get("DEEPSEEK_MODEL")
        or env_vars.get("DEEPSEEK_MODEL")
        or DEFAULT_MODEL
    )
    for prefix in ("opendesign/", "deepseek/"):
        if str(model).startswith(prefix):
            model = str(model)[len(prefix):]
    # Strict guard: ensure it strictly uses normal deepseek-v4.1-flash and never an eco variant
    if "eco" in str(model).lower() or str(model) != DEFAULT_MODEL:
        model = DEFAULT_MODEL

    return api_key, base_url, model


def load_json_file(path, default=None):
    if default is None:
        default = {}
    p = pathlib.Path(path)
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def append_jsonl_file(path, data):
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False) + "\n")


def now_iso_utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def today_sgt_str():
    # Singapore is UTC+8
    sgt = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=8)
    return sgt.strftime("%Y-%m-%d")


def strip_dashes(text):
    """Replace em and en dashes with standard punctuation."""
    if text is None:
        return ""
    cleaned = re.sub(r"\s*\u2014\s*", ": ", str(text))
    return cleaned.replace("\u2013", "-")


def sanitize_dashes_recursive(obj):
    """Recursively strip em and en dashes across dicts, lists, and strings."""
    if isinstance(obj, str):
        return strip_dashes(obj)
    if isinstance(obj, list):
        return [sanitize_dashes_recursive(item) for item in obj]
    if isinstance(obj, dict):
        return {strip_dashes(k) if isinstance(k, str) else k: sanitize_dashes_recursive(v) for k, v in obj.items()}
    return obj


def _normalize_gsc_query_rows(rows, query_to_page=None):
    out = []
    qmap = query_to_page or {}
    for r in rows or []:
        q_name = (r.get("keys") or [""])[0]
        if not q_name:
            continue
        item = {
            "query": q_name,
            "clicks": r.get("clicks", 0),
            "impressions": r.get("impressions", 0),
            "ctr": round(float(r.get("ctr", 0.0)), 4),
            "position": round(float(r.get("position", 0.0)), 1),
        }
        if q_name in qmap:
            item["page"] = qmap[q_name]
        out.append(item)
    return out


def build_telemetry_digest(base_dir=None):
    """Build a compact telemetry digest from GSC (global/SG/IN/Page-1), GA4, technical audit, GEO audit, and leads."""
    base_path = pathlib.Path(base_dir) if base_dir is not None else JOB_DIR
    rep = base_path / "reports"
    gsc = load_json_file(rep / "latest-gsc.json")
    ga4 = load_json_file(rep / "latest-ga4.json")
    audit = load_json_file(rep / "latest-audit.json")
    geo_audit = load_json_file(rep / "latest-geo-audit.json")
    leads = load_json_file(rep / "latest-leads.json")

    w28 = gsc.get("window_28d") or {}
    totals_row = ((w28.get("totals") or {}).get("rows") or [{}])[0]
    total_clicks = totals_row.get("clicks", 0)
    total_impressions = totals_row.get("impressions", 0)
    avg_ctr = totals_row.get("ctr", 0.0)
    avg_position = totals_row.get("position", 0.0)

    # Map query -> primary landing page using query_page_pairs
    query_to_page = {}
    query_best_imp = {}
    for pair in ((w28.get("query_page_pairs") or {}).get("rows") or []):
        keys = pair.get("keys") or []
        if len(keys) >= 2:
            q_name, p_url = keys[0], keys[1]
            imp = pair.get("impressions", 0)
            if imp > query_best_imp.get(q_name, -1):
                query_best_imp[q_name] = imp
                query_to_page[q_name] = p_url

    all_query_items = _normalize_gsc_query_rows((w28.get("top_queries") or {}).get("rows"), query_to_page)
    top_queries = sorted(all_query_items, key=lambda x: (-x["clicks"], -x["impressions"]))[:20]
    opportunity_queries = sorted(
        [x for x in all_query_items if x["impressions"] >= 10 and (x["ctr"] < 0.05 or 4.0 <= x["position"] <= 35.0)],
        key=lambda x: (-x["impressions"], x["position"]),
    )[:15]

    sg_items = _normalize_gsc_query_rows((w28.get("singapore_queries") or {}).get("rows"), query_to_page)
    singapore_queries = sorted(sg_items, key=lambda x: (-x["impressions"], -x["clicks"]))[:20]
    singapore_opportunity_queries = sorted(
        [x for x in sg_items if x["impressions"] >= 3 and (x["clicks"] == 0 or x["ctr"] < 0.05 or x["position"] <= 40.0)],
        key=lambda x: (-x["impressions"], x["position"]),
    )[:15]
    singapore_totals = {
        "query_count": len(sg_items),
        "sum_impressions": sum(x["impressions"] for x in sg_items),
        "sum_clicks": sum(x["clicks"] for x in sg_items),
    }

    in_items = _normalize_gsc_query_rows((w28.get("india_queries") or {}).get("rows"), query_to_page)
    india_queries = sorted(in_items, key=lambda x: (-x["impressions"], -x["clicks"]))[:20]
    india_opportunity_queries = sorted(
        [x for x in in_items if x["impressions"] >= 3 and (5.0 <= x["position"] <= 35.0 or x["ctr"] < 0.05)],
        key=lambda x: (-x["impressions"], x["position"]),
    )[:15]
    india_totals = {
        "query_count": len(in_items),
        "sum_impressions": sum(x["impressions"] for x in in_items),
        "sum_clicks": sum(x["clicks"] for x in in_items),
    }

    # Top pages and Page-1 zero-CTR alerts (position <= 10.0, clicks == 0)
    raw_page_rows = (w28.get("top_pages") or {}).get("rows") or []
    top_pages = []
    page1_zero_ctr_pages = []
    for r in raw_page_rows:
        p_url = (r.get("keys") or [""])[0]
        p_clicks = r.get("clicks", 0)
        p_imps = r.get("impressions", 0)
        p_ctr = round(float(r.get("ctr", 0.0)), 4)
        p_pos = round(float(r.get("position", 0.0)), 1)
        p_item = {"page": p_url, "clicks": p_clicks, "impressions": p_imps, "ctr": p_ctr, "position": p_pos}
        top_pages.append(p_item)
        if p_imps >= 1 and p_clicks == 0 and p_pos <= 10.0:
            page1_zero_ctr_pages.append(p_item)

    top_pages = sorted(top_pages, key=lambda x: (-x["impressions"], -x["clicks"]))[:15]
    page1_zero_ctr_pages = sorted(page1_zero_ctr_pages, key=lambda x: (-x["impressions"], x["position"]))[:15]

    p1_query_seen = {}
    for scope, rows_list in (("sgp", sg_items), ("ind", in_items), ("all", all_query_items)):
        for item in rows_list:
            if item["impressions"] >= 1 and item["clicks"] == 0 and item["position"] <= 10.0:
                q_key = (item["query"], scope)
                if q_key not in p1_query_seen:
                    p1_query_seen[q_key] = {**item, "country": scope}
    page1_zero_ctr_queries = sorted(
        p1_query_seen.values(),
        key=lambda x: (-x["impressions"], x["position"]),
    )[:20]

    # Fallback to latest-geo-audit.json Page-1 alerts if GSC query lists were absent
    geo_p1 = geo_audit.get("page1_zero_ctr_alerts") or {}
    if not page1_zero_ctr_queries and geo_p1.get("queries"):
        page1_zero_ctr_queries = geo_p1.get("queries", [])[:20]
    if not page1_zero_ctr_pages and geo_p1.get("pages"):
        page1_zero_ctr_pages = geo_p1.get("pages", [])[:15]

    # Countries
    country_rows = (w28.get("countries") or {}).get("rows") or []
    top_countries = []
    for c in country_rows[:10]:
        top_countries.append({
            "country": (c.get("keys") or [""])[0].upper(),
            "clicks": c.get("clicks", 0),
            "impressions": c.get("impressions", 0),
            "ctr": round(float(c.get("ctr", 0.0)), 4),
            "position": round(float(c.get("position", 0.0)), 1),
        })

    # GA4 28d totals
    ga4_totals = ((ga4.get("totals_28d") or {}).get("rows") or [{}])[0]
    ga4_metric_vals = [m.get("value", "0") for m in ga4_totals.get("metricValues", [])]
    ga4_summary = {
        "active_users": ga4_metric_vals[0] if len(ga4_metric_vals) > 0 else "0",
        "new_users": ga4_metric_vals[1] if len(ga4_metric_vals) > 1 else "0",
        "sessions": ga4_metric_vals[2] if len(ga4_metric_vals) > 2 else "0",
        "screen_page_views": ga4_metric_vals[3] if len(ga4_metric_vals) > 3 else "0",
        "key_events": ga4_metric_vals[4] if len(ga4_metric_vals) > 4 else "0",
    }

    # GA4 channels
    channel_rows = (ga4.get("channels_28d") or {}).get("rows") or []
    top_channels = []
    for ch in channel_rows[:5]:
        ch_name = (ch.get("dimensionValues") or [{}])[0].get("value", "")
        m_vals = [m.get("value", "0") for m in ch.get("metricValues", [])]
        top_channels.append({
            "channel": ch_name,
            "active_users": m_vals[0] if len(m_vals) > 0 else "0",
            "sessions": m_vals[1] if len(m_vals) > 1 else (m_vals[0] if m_vals else "0"),
        })

    # Technical audit summary (pages is a list in latest-audit.json)
    audit_pages = audit.get("pages", [])
    audit_pages_count = len(audit_pages) if isinstance(audit_pages, (list, dict)) else 0
    audit_summary = {
        "live_pages_count": audit_pages_count,
        "broken_links_count": len(audit.get("broken", audit.get("broken_links", []))),
        "pages_with_issues": audit.get("pages_with_issues", 0),
        "issue_counts": audit.get("issue_counts", {}),
        "changed_urls": audit.get("changed_urls", [])[:5],
    }

    # GEO/AEO audit digest from latest-geo-audit.json
    geo_tech = geo_audit.get("technical_findings") or {}
    geo_llms = geo_audit.get("llms_parity") or {}
    geo_schema = geo_audit.get("schema_summary") or {}
    geo_audit_summary = {
        "available": bool(geo_audit),
        "readiness_score": geo_audit.get("readiness_score"),
        "readiness_breakdown": geo_audit.get("readiness_breakdown", {}),
        "schema_counts": geo_schema.get("counts", {}),
        "missing_schema_pages": (geo_schema.get("missing_schema_pages") or [])[:10],
        "llms_txt_parity_ok": geo_llms.get("llms_txt_parity_ok"),
        "llms_full_txt_parity_ok": geo_llms.get("llms_full_txt_parity_ok"),
        "missing_in_llms_txt": (geo_llms.get("missing_in_llms_txt") or [])[:10],
        "missing_in_llms_full_txt": (geo_llms.get("missing_in_llms_full_txt") or [])[:10],
        "em_en_dash_files": geo_llms.get("em_en_dash_files", []),
        "mixed_content_maps_google_pages": [p.get("url") for p in (geo_tech.get("mixed_content_maps_google_pages") or [])[:10]],
        "duplicate_jquery_pages": [p.get("url") for p in (geo_tech.get("duplicate_jquery_pages") or [])[:10]],
        "pages_with_blocking_scripts": geo_tech.get("pages_with_blocking_scripts", 0),
        "total_blocking_scripts": geo_tech.get("total_blocking_scripts", 0),
        "images_total": geo_tech.get("images_total", 0),
        "images_missing_dimensions": geo_tech.get("images_missing_dimensions", 0),
        "images_missing_lazy": geo_tech.get("images_missing_lazy", 0),
    }

    leads_summary = {
        "verified_leads_total": leads.get("verified_leads_total", 0),
        "spam_blocked_total": leads.get("spam_blocked_total", 0),
    }

    return sanitize_dashes_recursive({
        "date_sgt": today_sgt_str(),
        "gsc": {
            "clicks": total_clicks,
            "impressions": total_impressions,
            "ctr": round(float(avg_ctr), 4),
            "position": round(float(avg_position), 1),
            "top_queries": top_queries,
            "opportunity_queries": opportunity_queries,
            "singapore_totals": singapore_totals,
            "singapore_queries": singapore_queries,
            "singapore_opportunity_queries": singapore_opportunity_queries,
            "india_totals": india_totals,
            "india_queries": india_queries,
            "india_opportunity_queries": india_opportunity_queries,
            "top_pages": top_pages,
            "page1_zero_ctr_queries": page1_zero_ctr_queries,
            "page1_zero_ctr_pages": page1_zero_ctr_pages,
            "top_countries": top_countries,
        },
        "ga4": ga4_summary,
        "channels": top_channels,
        "audit": audit_summary,
        "geo_audit": geo_audit_summary,
        "leads": leads_summary,
    })


# Backward-compatible alias
extract_telemetry_digest = build_telemetry_digest


def get_upcoming_wave_info():
    today = today_sgt_str()
    try:
        for p in (BASE_DIR, JOB_DIR / "scripts", JOB_DIR):
            ps = str(p)
            if p.exists() and ps not in sys.path:
                sys.path.insert(0, ps)
        from content_pages import STAGED_WAVES
        dynamic_waves = []
        for w in STAGED_WAVES:
            sp = w.get("spec") or {}
            dynamic_waves.append({
                "wave": w.get("wave_id", ""),
                "date": w.get("deploy_date", ""),
                "slug": sp.get("slug", ""),
                "title": sp.get("title", ""),
                "target_keywords": sp.get("keywords", []),
                "focus": sp.get("description", ""),
            })
        if dynamic_waves:
            dynamic_waves.sort(key=lambda x: x["date"])
            for dw in dynamic_waves:
                if dw["date"] >= today:
                    return sanitize_dashes_recursive(dw)
            return sanitize_dashes_recursive(dynamic_waves[-1])
    except Exception:
        pass

    waves = [
        {
            "wave": "Wave 2",
            "date": "2026-11-21",
            "slug": "conference-and-mice-event-management",
            "title": "Conference & MICE Event Management Singapore | Framez",
            "target_keywords": ["conference management company", "mice event management", "corporate conference organizers singapore"],
            "focus": "Large corporate conferences, association conventions, MICE logistics, breakout sessions, Marina Bay Sands and Suntec venues.",
        },
        {
            "wave": "Wave 3",
            "date": "2026-11-25",
            "slug": "exhibition-and-trade-show-management",
            "title": "Exhibition & Trade Show Management Singapore | Custom Booth Design",
            "target_keywords": ["exhibition management company", "trade show booth fabrication singapore", "expo event organizer"],
            "focus": "Trade show stall fabrication, B2B exhibition organizer, visitor registration, Singapore EXPO and Sands Expo.",
        },
        {
            "wave": "Wave 4",
            "date": "2026-11-29",
            "slug": "year-end-corporate-town-hall-and-kickoff-guide",
            "title": "Corporate Town Hall & Sales Kickoff Production Guide Singapore",
            "target_keywords": ["corporate town hall event planner", "sales kickoff event organizers", "all hands production singapore"],
            "focus": "Q4 all-hands town halls, annual sales kickoffs (SKO), multi-country hybrid broadcasts, CEO keynote stage AV.",
        },
        {
            "wave": "Wave 5",
            "date": "2026-12-03",
            "slug": "bangalore-corporate-event-venue-and-logistics-checklist",
            "title": "Bangalore Corporate Event Venue & Logistics Checklist | Framez",
            "target_keywords": ["corporate event organizers bangalore", "event management company in bangalore", "bangalore conference venues"],
            "focus": "Bangalore tech corridor events, Koramangala and Whitefield venues, IT tech summits and annual corporate retreats.",
        },
        {
            "wave": "Wave 6",
            "date": "2026-12-07",
            "slug": "sustainable-corporate-events-esg-guide-singapore-india",
            "title": "Sustainable Corporate Events & ESG Guide | Green MICE Singapore & India",
            "target_keywords": ["sustainable event management", "green mice singapore", "esg corporate events"],
            "focus": "Singapore Green Plan 2030 compliance, zero-waste corporate events, carbon footprint reduction for MNC conferences.",
        },
    ]

    for w in waves:
        if w["date"] >= today:
            return w
    return waves[-1]


def build_deepseek_prompt(digest, next_wave):
    system_instruction = (
        "You are the Lead SEO, Generative Engine Optimization (GEO), and Answer Engine Optimization (AEO) Strategist for Framez Events & Productions (https://framez.sg). "
        "Framez is a B2B corporate event management and production company with dual regional operations: "
        "Singapore Office at Prudential Tower (30 Cecil Street, #19-08, Singapore 049712) and India Headquarters in Bangalore (Koramangala). "
        "Your goal is to provide daily high-precision keyword, CTR, schema, technical remediation, and AI citation recommendations based ONLY on the supplied telemetry. "
        "Strict rules for your output:\n"
        "1. Return ONLY a valid JSON object matching the requested schema. Do not use code fences, markdown wrapping, or commentary text.\n"
        "2. Do NOT use any em dashes or en dashes in any text. Use colons, commas, or standard hyphens.\n"
        "3. Write plain, direct technical and commercial copy without corporate filler, inflated claims, or AI buzzwords.\n"
        "4. Never fabricate metrics or mention client revenue figures. Cite only figures observed in the telemetry digest.\n"
        "5. Tailor commercial insights to corporate event buyers in Singapore and Bangalore and emphasize GEO/AEO citation readiness (Perplexity, ChatGPT Search, Google AI Overviews).\n"
        "IMPORTANT: Do not overthink. Output ONLY the raw JSON object immediately."
    )

    gsc = digest["gsc"]
    geo_a = digest.get("geo_audit") or {}
    user_content = f"""
Daily Telemetry Snapshot (Date: {digest['date_sgt']}):
- GSC (28 Days Global): {gsc['clicks']} clicks, {gsc['impressions']} impressions, {gsc['ctr']} CTR, avg position {gsc['position']}.
- Country Split (Top Countries): {json.dumps(gsc['top_countries'])}
- Top Global Queries: {json.dumps(gsc['top_queries'][:10])}
- Global Opportunity Queries: {json.dumps(gsc['opportunity_queries'][:10])}
- Singapore (SGP) Query Totals: {json.dumps(gsc.get('singapore_totals', {}))}
- Top Singapore Queries (SGP): {json.dumps(gsc.get('singapore_queries', [])[:15])}
- Singapore Opportunity Queries (SGP): {json.dumps(gsc.get('singapore_opportunity_queries', [])[:12])}
- India (IND) Query Totals: {json.dumps(gsc.get('india_totals', {}))}
- Top India Queries (IND): {json.dumps(gsc.get('india_queries', [])[:15])}
- India Striking-Distance Queries (IND): {json.dumps(gsc.get('india_opportunity_queries', [])[:12])}
- Page-1 Zero-CTR Queries (Position <= 10, Clicks = 0): {json.dumps(gsc.get('page1_zero_ctr_queries', [])[:15])}
- Page-1 Zero-CTR Landing Pages (Position <= 10, Clicks = 0): {json.dumps(gsc.get('page1_zero_ctr_pages', [])[:12])}
- GEO/AEO Audit Findings (latest-geo-audit.json): {json.dumps(geo_a)}
- Technical Crawl Audit: {json.dumps(digest.get('audit', {}))}
- GA4 Activity: {digest['ga4']['active_users']} active users, {digest['ga4']['sessions']} sessions, {digest['ga4'].get('key_events', '0')} key events.
- Lead Status: {digest['leads']['verified_leads_total']} verified leads, {digest['leads']['spam_blocked_total']} blocked bots.
- Next Scheduled Cycle Wave: {json.dumps(next_wave)}

Please provide a structured daily intelligence evaluation with the following JSON schema:
{{
  "analysis_date": "{digest['date_sgt']}",
  "executive_summary": "1-2 concise sentences summarizing Singapore vs India search visibility, GEO/AEO readiness, and top priority for today.",
  "top_keyword_opportunities": [
    {{
      "target_query": "Exact query string from Singapore, India, or Page-1 zero-CTR telemetry",
      "current_metric": "impressions, clicks, ctr, and position directly from telemetry",
      "optimization_action": "Specific title/meta, FAQ, or internal link injection required to capture clicks",
      "target_landing_page": "/slug-of-target-page"
    }}
  ],
  "geo_aeo_citation_strategy": {{
    "ai_engine_focus": "ChatGPT Search, Perplexity AI, Google AI Overviews",
    "recommended_schema_type": "Schema type e.g. Organization, ProfessionalService, FAQPage, Service, Article",
    "citation_anchor_text": "Exact factual sentence to embed on the page to support LLM citations",
    "target_entities": ["Prudential Tower Singapore", "Marina Bay Sands Expo", "Singapore Tourism Board MICE", "Koramangala Bangalore"]
  }},
  "geo_technical_remediations": [
    {{
      "issue": "Specific finding from latest-geo-audit.json (mixed-content maps.google.com, duplicate jQuery, blocking scripts, missing img dims/lazy, schema gap, or llms.txt parity)",
      "affected_pages": ["/slug"],
      "action": "Concrete technical fix"
    }}
  ],
  "page_micro_optimizations": [
    {{
      "page_slug": "/event-management-company-in-singapore",
      "recommended_title_tag": "Optimized title under 60 chars",
      "recommended_meta_description": "Compelling meta under 155 chars with phone/CTA",
      "content_hook": "Specific H2 or paragraph addition for topical authority"
    }}
  ],
  "upcoming_wave_enhancements": {{
    "wave_title": "{next_wave['wave']}: {next_wave['slug']}",
    "release_date": "{next_wave['date']}",
    "recommended_h2_topics": ["Topic 1", "Topic 2", "Topic 3"],
    "local_singapore_entities": ["Venue or regulation 1", "Venue or regulation 2"],
    "commercial_call_to_action": "Specific CTA for enterprise event planners"
  }}
}}
"""
    return strip_dashes(system_instruction), strip_dashes(user_content)


def call_deepseek_v41_flash(system_prompt, user_prompt, api_key, base_url, model):
    payload = {
        "model": model,
        "reasoning_effort": "low",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "max_tokens": 8192,
        "temperature": 0.15
    }

    req = urllib.request.Request(
        base_url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "BlankTruthServer/1.2 (framez-seo; https://framez.sg)"
        },
        data=json.dumps(payload).encode("utf-8")
    )

    t0 = time.time()
    with urllib.request.urlopen(req, timeout=90) as resp:
        raw_body = resp.read().decode("utf-8")
        latency = round(time.time() - t0, 2)
        parsed = json.loads(raw_body)
        choice = parsed.get("choices", [{}])[0].get("message", {})
        content = choice.get("content", "").strip()
        usage = parsed.get("usage", {})
        return {
            "status": "ok",
            "latency_seconds": latency,
            "model": model,
            "raw_content": content,
            "usage": usage
        }


def clean_json_response(raw_text):
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    cleaned = cleaned.strip()

    match = re.search(r"(\{.*\})", cleaned, re.DOTALL)
    if match:
        cleaned = match.group(1)

    cleaned = strip_dashes(cleaned)
    parsed = json.loads(cleaned)
    return sanitize_dashes_recursive(parsed)


def generate_markdown_summary(insights):
    insights = sanitize_dashes_recursive(insights or {})
    exec_summary = insights.get("executive_summary", "Daily DeepSeek v4.1 Flash SEO intelligence generated.")
    kw_ops = insights.get("top_keyword_opportunities", [])
    geo = insights.get("geo_aeo_citation_strategy", {})
    geo_rems = insights.get("geo_technical_remediations", [])
    page_opts = insights.get("page_micro_optimizations", [])
    wave_info = insights.get("upcoming_wave_enhancements", {})

    lines = [
        "# DeepSeek v4.1 Flash Daily SEO & GEO Intelligence Summary",
        f"**Date:** {insights.get('analysis_date', today_sgt_str())} (Singapore Time)  ",
        f"**Model:** `{DEFAULT_MODEL}` via OpenDesign Gateway (Normal)  ",
        f"**Generated:** {now_iso_utc()}  ",
        "",
        "## Executive Summary",
        f"{exec_summary}",
        "",
        "## Top Search Opportunities & CTR Enhancements",
    ]

    for idx, kw in enumerate(kw_ops, 1):
        lines.append(f"{idx}. **Query:** `{kw.get('target_query')}`")
        lines.append(f"   * **Current Metric:** {kw.get('current_metric')}")
        lines.append(f"   * **Target Page:** `{kw.get('target_landing_page')}`")
        lines.append(f"   * **Optimization:** {kw.get('optimization_action')}")

    lines.extend([
        "",
        "## Generative Engine & AEO Citation Strategy",
        f"* **Focus Engines:** {geo.get('ai_engine_focus', 'ChatGPT Search, Perplexity AI, Google AI Overviews')}",
        f"* **Recommended Schema:** `{geo.get('recommended_schema_type', 'ProfessionalService, FAQPage')}`",
        f"* **Citation Hook:** \"{geo.get('citation_anchor_text', '')}\"",
        f"* **Target Entities:** {', '.join(geo.get('target_entities', []))}",
    ])

    if geo_rems:
        lines.extend(["", "## GEO Technical Remediations"])
        for rem in geo_rems:
            pages_txt = ", ".join(rem.get("affected_pages") or [])
            lines.append(f"* **{rem.get('issue')}** ({pages_txt}): {rem.get('action')}")

    lines.extend(["", "## Page Micro-Optimizations"])
    for p in page_opts:
        lines.append(f"### Target: `{p.get('page_slug')}`")
        lines.append(f"* **Title:** `{p.get('recommended_title_tag')}`")
        lines.append(f"* **Meta:** `{p.get('recommended_meta_description')}`")
        lines.append(f"* **Content Hook:** {p.get('content_hook')}")

    lines.extend([
        "",
        "## Pre-Flight Guidance for Upcoming Wave",
        f"**Target:** {wave_info.get('wave_title')} (Release Date: {wave_info.get('release_date')})  ",
        f"* **Recommended H2 Topics:** {', '.join(wave_info.get('recommended_h2_topics', []))}",
        f"* **Local Entities:** {', '.join(wave_info.get('local_singapore_entities', []))}",
        f"* **Commercial CTA:** {wave_info.get('commercial_call_to_action')}",
        "",
    ])

    return strip_dashes("\n".join(lines))


def run_daily_deepseek_task(base_dir=None):
    base_dir = pathlib.Path(base_dir) if base_dir is not None else JOB_DIR

    print(f"[{now_iso_utc()}] Starting DeepSeek v4.1 Flash daily SEO intelligence task...")
    api_key, base_url, model = get_api_credentials()
    if not api_key:
        err_msg = "Missing OpenDesign API key (checked env OPENDESIGN_API_KEY and /root/.commandcode/opendesign-api-key.secret)"
        print(f"[{now_iso_utc()}] DeepSeek v4.1 Flash error: {err_msg}")
        return {"status": "error", "error": err_msg, "timestamp": now_iso_utc()}

    digest = build_telemetry_digest(base_dir)
    next_wave = get_upcoming_wave_info()

    system_prompt, user_prompt = build_deepseek_prompt(digest, next_wave)

    try:
        call_res = call_deepseek_v41_flash(system_prompt, user_prompt, api_key, base_url, model)
        latency = call_res["latency_seconds"]
        print(f"[{now_iso_utc()}] Received response from {model} in {latency}s")

        insights = clean_json_response(call_res["raw_content"])
        insights["meta"] = {
            "model": model,
            "gateway": base_url,
            "latency_seconds": latency,
            "usage": call_res.get("usage"),
            "timestamp_utc": now_iso_utc()
        }

        rep_dir = base_dir / "reports"
        rep_dir.mkdir(parents=True, exist_ok=True)
        latest_json_path = rep_dir / "latest-deepseek-insights.json"
        latest_json_path.write_text(json.dumps(insights, indent=2, ensure_ascii=False), encoding="utf-8")

        jsonl_path = rep_dir / "deepseek-daily-insights.jsonl"
        append_jsonl_file(jsonl_path, insights)

        md_text = generate_markdown_summary(insights)
        md_path = rep_dir / "deepseek-insights-summary.md"
        md_path.write_text(md_text, encoding="utf-8")

        cycle_ledger_path = rep_dir / "cycle-2026-11-15-to-2026-12-15-ledger.jsonl"
        append_jsonl_file(cycle_ledger_path, {
            "event": "deepseek_v41_flash_daily_intelligence",
            "timestamp": now_iso_utc(),
            "date_sgt": insights.get("analysis_date"),
            "model": model,
            "latency_seconds": latency,
            "executive_summary": insights.get("executive_summary"),
            "top_keyword_count": len(insights.get("top_keyword_opportunities", [])),
            "micro_optimizations_count": len(insights.get("page_micro_optimizations", [])),
            "geo_remediations_count": len(insights.get("geo_technical_remediations", [])),
        })

        print(f"[{now_iso_utc()}] DeepSeek v4.1 Flash daily run completed successfully.")
        return {
            "status": "ok",
            "date": insights.get("analysis_date"),
            "latency_seconds": latency,
            "executive_summary": insights.get("executive_summary"),
            "latest_json": str(latest_json_path),
            "summary_md": str(md_path)
        }

    except Exception as e:
        err_msg = str(e)
        print(f"[{now_iso_utc()}] DeepSeek v4.1 Flash error: {err_msg}")
        return {
            "status": "error",
            "error": err_msg,
            "timestamp": now_iso_utc()
        }


if __name__ == "__main__":
    result = run_daily_deepseek_task()
    print(json.dumps(result, indent=2))
