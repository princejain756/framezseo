#!/usr/bin/env python3
"""DeepSeek v4.1 Flash Daily SEO, GEO and AEO Intelligence Engine for Framez.sg.

Connects to OpenDesign DeepSeek v4.1 Flash (Normal):
  Base URL: https://amr-link.open-design.ai/v1/chat/completions
  Model: deepseek-v4.1-flash (strictly normal, not eco)
  API Key: Read from /root/.commandcode/opendesign-api-key.secret or environment

Ingests:
  - latest-gsc.json (queries, impressions, clicks, ctr, positions, countries)
  - latest-ga4.json (sessions, users, engagement, channels, conversion events)
  - latest-audit.json (live URLs, word counts, technical health)
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
    model = (
        os.environ.get("DEEPSEEK_MODEL")
        or env_vars.get("DEEPSEEK_MODEL")
        or DEFAULT_MODEL
    )
    if str(model).startswith("deepseek/"):
        model = str(model)[len("deepseek/"):]
    # Strict guard: ensure it never uses an eco variant
    if "eco" in str(model).lower():
        model = "deepseek-v4.1-flash"

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


def extract_telemetry_digest(base_dir):
    rep = base_dir / "reports"
    gsc = load_json_file(rep / "latest-gsc.json")
    ga4 = load_json_file(rep / "latest-ga4.json")
    audit = load_json_file(rep / "latest-audit.json")
    leads = load_json_file(rep / "latest-leads.json")

    # Extract 28d GSC summary
    w28 = gsc.get("window_28d", {})
    totals_row = (w28.get("totals", {}).get("rows") or [{}])[0]
    total_clicks = totals_row.get("clicks", 0)
    total_impressions = totals_row.get("impressions", 0)
    avg_ctr = totals_row.get("ctr", 0.0)
    avg_position = totals_row.get("position", 0.0)

    # Top queries
    raw_query_rows = (w28.get("top_queries", {}).get("rows") or [])
    top_queries = []
    opportunity_queries = []
    for r in raw_query_rows:
        q_name = (r.get("keys") or [""])[0]
        q_clicks = r.get("clicks", 0)
        q_imps = r.get("impressions", 0)
        q_ctr = r.get("ctr", 0.0)
        q_pos = r.get("position", 0.0)
        item = {
            "query": q_name,
            "clicks": q_clicks,
            "impressions": q_imps,
            "ctr": round(q_ctr, 4),
            "position": round(q_pos, 1)
        }
        if len(top_queries) < 15:
            top_queries.append(item)
        # Opportunity queries: High impressions (>20) with CTR < 5% or ranking position 5 to 35
        if q_imps >= 20 and (q_ctr < 0.05 or (5.0 <= q_pos <= 35.0)):
            if len(opportunity_queries) < 10:
                opportunity_queries.append(item)

    # Countries
    country_rows = (w28.get("countries", {}).get("rows") or [])
    top_countries = []
    for c in country_rows[:5]:
        top_countries.append({
            "country": (c.get("keys") or [""])[0].upper(),
            "clicks": c.get("clicks", 0),
            "impressions": c.get("impressions", 0)
        })

    # GA4 28d totals
    ga4_totals = (ga4.get("totals_28d", {}).get("rows") or [{}])[0]
    ga4_metric_vals = [m.get("value", "0") for m in ga4_totals.get("metricValues", [])]
    ga4_summary = {
        "active_users": ga4_metric_vals[0] if len(ga4_metric_vals) > 0 else "0",
        "new_users": ga4_metric_vals[1] if len(ga4_metric_vals) > 1 else "0",
        "sessions": ga4_metric_vals[2] if len(ga4_metric_vals) > 2 else "0",
        "screen_page_views": ga4_metric_vals[3] if len(ga4_metric_vals) > 3 else "0",
        "engagement_rate": ga4_metric_vals[4] if len(ga4_metric_vals) > 4 else "0",
    }

    # GA4 channels
    channel_rows = ga4.get("channels_28d", {}).get("rows") or []
    top_channels = []
    for ch in channel_rows[:5]:
        ch_name = (ch.get("dimensionValues") or [{}])[0].get("value", "")
        m_vals = [m.get("value", "0") for m in ch.get("metricValues", [])]
        top_channels.append({
            "channel": ch_name,
            "sessions": m_vals[0] if m_vals else "0"
        })

    # Technical audit summary
    audit_summary = {
        "live_pages_count": len(audit.get("pages", {})),
        "broken_links_count": len(audit.get("broken_links", [])),
        "changed_urls": audit.get("changed_urls", [])[:5]
    }

    # Leads summary
    leads_summary = {
        "verified_leads_total": leads.get("verified_leads_total", 0),
        "spam_blocked_total": leads.get("spam_blocked_total", 0)
    }

    return {
        "date_sgt": today_sgt_str(),
        "gsc": {
            "clicks": total_clicks,
            "impressions": total_impressions,
            "ctr": round(avg_ctr, 4),
            "position": round(avg_position, 1),
            "top_queries": top_queries,
            "opportunity_queries": opportunity_queries,
            "top_countries": top_countries
        },
        "ga4": ga4_summary,
        "channels": top_channels,
        "audit": audit_summary,
        "leads": leads_summary
    }


def get_upcoming_wave_info():
    today = today_sgt_str()
    waves = [
        {
            "wave": "Wave 2",
            "date": "2026-11-21",
            "slug": "conference-and-mice-event-management",
            "title": "Conference & MICE Event Management Singapore | Frame Events",
            "target_keywords": ["conference management company", "mice event management", "corporate conference organizers singapore"],
            "focus": "Large corporate conferences, association conventions, MICE logistics, breakout sessions, Marina Bay Sands and Suntec venues."
        },
        {
            "wave": "Wave 3",
            "date": "2026-11-25",
            "slug": "exhibition-and-trade-show-management",
            "title": "Exhibition & Trade Show Management Singapore | Custom Booth Design",
            "target_keywords": ["exhibition management company", "trade show booth fabrication singapore", "expo event organizer"],
            "focus": "Trade show stall fabrication, B2B exhibition organizer, visitor registration, Singapore EXPO and Sands Expo."
        },
        {
            "wave": "Wave 4",
            "date": "2026-11-29",
            "slug": "year-end-corporate-town-hall-and-kickoff-guide",
            "title": "Corporate Town Hall & Sales Kickoff Production Guide Singapore",
            "target_keywords": ["corporate town hall event planner", "sales kickoff event organizers", "all hands production singapore"],
            "focus": "Q4 all-hands town halls, annual sales kickoffs (SKO), multi-country hybrid broadcasts, CEO keynote stage AV."
        },
        {
            "wave": "Wave 5",
            "date": "2026-12-03",
            "slug": "bangalore-corporate-event-venue-and-logistics-checklist",
            "title": "Bangalore Corporate Event Venue & Logistics Checklist | Frame Events",
            "target_keywords": ["corporate event organizers bangalore", "event management company in bangalore", "bangalore conference venues"],
            "focus": "Bangalore tech corridor events, Koramangala and Whitefield venues, IT tech summits and annual corporate retreats."
        },
        {
            "wave": "Wave 6",
            "date": "2026-12-07",
            "slug": "sustainable-corporate-events-esg-guide-singapore-india",
            "title": "Sustainable Corporate Events & ESG Guide | Green MICE Singapore & India",
            "target_keywords": ["sustainable event management", "green mice singapore", "esg corporate events"],
            "focus": "Singapore Green Plan 2030 compliance, zero-waste corporate events, carbon footprint reduction for MNC conferences."
        }
    ]

    for w in waves:
        if w["date"] >= today:
            return w
    return waves[-1]


def build_deepseek_prompt(digest, next_wave):
    system_instruction = (
        "You are the Lead SEO, Generative Engine Optimization (GEO), and Answer Engine Optimization (AEO) Strategist for Framez Events & Productions (https://framez.sg). "
        "Framez is a premier corporate event management and production company with dual regional operations: "
        "Singapore Headquarters at Prudential Tower (30 Cecil Street, Raffles Place) and India Headquarters in Bangalore (Koramangala). "
        "Your goal is to provide daily high-precision keyword, CTR, schema, and Generative AI citation recommendations. "
        "Strict rules for your output:\n"
        "1. Return ONLY a valid JSON object matching the requested schema. Do not use code fences, markdown wrapping, or commentary text.\n"
        "2. Do NOT use any em dashes or en dashes in any text. Use colons, commas, or standard hyphens.\n"
        "3. Provide realistic, highly technical, and commercial insights tailored to corporate event buyers in Singapore and Bangalore.\n"
        "4. Emphasize Generative AI citation hooks (Perplexity, ChatGPT Search, Google AI Overviews) by referencing specific entities, statistics, and FAQ structures.\n"
        "IMPORTANT: Do not overthink. Output ONLY the raw JSON object immediately."
    )

    user_content = f"""
Daily Telemetry Snapshot (Date: {digest['date_sgt']}):
- GSC (28 Days): {digest['gsc']['clicks']} clicks, {digest['gsc']['impressions']} impressions, {digest['gsc']['ctr']} CTR, avg position {digest['gsc']['position']}.
- Country Split: {json.dumps(digest['gsc']['top_countries'])}
- Top Live Queries: {json.dumps(digest['gsc']['top_queries'][:8])}
- High-Impression Opportunity Queries: {json.dumps(digest['gsc']['opportunity_queries'])}
- GA4 Activity: {digest['ga4']['active_users']} active users, {digest['ga4']['sessions']} sessions, {digest['ga4']['engagement_rate']} engagement rate.
- Lead Status: {digest['leads']['verified_leads_total']} verified leads, {digest['leads']['spam_blocked_total']} blocked bots.
- Next Scheduled Cycle Wave: {json.dumps(next_wave)}

Please provide a structured daily intelligence evaluation with the following JSON schema:
{{
  "analysis_date": "{digest['date_sgt']}",
  "executive_summary": "1-2 concise sentences summarizing the search landscape and top priority for today.",
  "top_keyword_opportunities": [
    {{
      "target_query": "Exact query string from telemetry or high-intent Singapore corporate term",
      "current_metric": "impressions and position from data or estimated baseline",
      "optimization_action": "Specific title/meta or content injection required to capture clicks",
      "target_landing_page": "/slug-of-target-page"
    }}
  ],
  "geo_aeo_citation_strategy": {{
    "ai_engine_focus": "ChatGPT Search, Perplexity AI, Google AI Overviews",
    "recommended_schema_type": "Schema type e.g. Event, FAQPage, HowTo, ProfessionalService",
    "citation_anchor_text": "Exact factual sentence or statistic to embed on the page to trigger LLM citations",
    "target_entities": ["Prudential Tower Singapore", "Marina Bay Sands Expo", "MICE Singapore Tourism Board", "Koramangala Bangalore"]
  }},
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
    return system_instruction, user_content


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

    # Search for outermost JSON object if any preamble exists
    match = re.search(r"(\{.*\})", cleaned, re.DOTALL)
    if match:
        cleaned = match.group(1)

    # Strip any stray en-dashes or em-dashes
    cleaned = cleaned.replace("\u2014", ":").replace("\u2013", "-")
    return json.loads(cleaned)


def generate_markdown_summary(insights):
    exec_summary = insights.get("executive_summary", "Daily DeepSeek v4.1 Flash SEO intelligence generated.")
    kw_ops = insights.get("top_keyword_opportunities", [])
    geo = insights.get("geo_aeo_citation_strategy", {})
    page_opts = insights.get("page_micro_optimizations", [])
    wave_info = insights.get("upcoming_wave_enhancements", {})

    lines = [
        f"# DeepSeek v4.1 Flash Daily SEO & GEO Intelligence Summary",
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
        "",
        "## Page Micro-Optimizations",
    ])

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
        ""
    ])

    md_text = "\n".join(lines).replace("\u2014", ":").replace("\u2013", "-")
    return md_text


def run_daily_deepseek_task(base_dir=None):
    if base_dir is None:
        base_dir = BASE_DIR

    print(f"[{now_iso_utc()}] Starting DeepSeek v4.1 Flash daily SEO intelligence task...")
    api_key, base_url, model = get_api_credentials()

    digest = extract_telemetry_digest(base_dir)
    next_wave = get_upcoming_wave_info()

    system_prompt, user_prompt = build_deepseek_prompt(digest, next_wave)

    try:
        call_res = call_deepseek_v41_flash(system_prompt, user_prompt, api_key, base_url, model)
        latency = call_res["latency_seconds"]
        print(f"[{now_iso_utc()}] Received response from {model} in {latency}s")

        insights = clean_json_response(call_res["raw_content"])
        insights["meta"] = {
            "model": model,
            "latency_seconds": latency,
            "usage": call_res.get("usage"),
            "timestamp_utc": now_iso_utc()
        }

        # Save latest JSON
        rep_dir = base_dir / "reports"
        rep_dir.mkdir(parents=True, exist_ok=True)
        latest_json_path = rep_dir / "latest-deepseek-insights.json"
        latest_json_path.write_text(json.dumps(insights, indent=2, ensure_ascii=False), encoding="utf-8")

        # Append to JSONL ledger
        jsonl_path = rep_dir / "deepseek-daily-insights.jsonl"
        append_jsonl_file(jsonl_path, insights)

        # Generate and save Markdown summary
        md_text = generate_markdown_summary(insights)
        md_path = rep_dir / "deepseek-insights-summary.md"
        md_path.write_text(md_text, encoding="utf-8")

        # Append to active monthly cycle ledger
        cycle_ledger_path = rep_dir / "cycle-2026-11-15-to-2026-12-15-ledger.jsonl"
        append_jsonl_file(cycle_ledger_path, {
            "event": "deepseek_v41_flash_daily_intelligence",
            "timestamp": now_iso_utc(),
            "date_sgt": insights.get("analysis_date"),
            "model": model,
            "latency_seconds": latency,
            "executive_summary": insights.get("executive_summary"),
            "top_keyword_count": len(insights.get("top_keyword_opportunities", [])),
            "micro_optimizations_count": len(insights.get("page_micro_optimizations", []))
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
