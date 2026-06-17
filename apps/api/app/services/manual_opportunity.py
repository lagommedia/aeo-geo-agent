from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

import httpx
from sqlalchemy.orm import Session

from app.models.opportunity import QueryOpportunity
from app.services.adapters.ahrefs_adapter import AhrefsAdapter
from app.services.adapters.gsc_adapter import GSCAdapter
from app.services.adapters.semrush_adapter import SEMrushAdapter
from app.services.briefs import generate_brief, infer_funnel, recommend_snippets
from app.services.detectors import detect_rising_query
from app.services.ingestion import _load_gsc_records
from app.services.strategist_engine import classify_opportunity_type, score_with_strategist


def _safe_query_text(value: str, limit: int = 500) -> str:
    return (value or "").strip().lower()[:limit]


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", (text or "").lower()))


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def _text_similarity(a: str, b: str) -> float:
    a_l = (a or "").strip().lower()
    b_l = (b or "").strip().lower()
    if not a_l or not b_l:
        return 0.0
    sim = _jaccard(_tokens(a_l), _tokens(b_l))
    if (a_l in b_l or b_l in a_l) and sim < 0.72:
        sim = 0.72
    return sim


def _link_tokens(link: str) -> set[str]:
    if not link:
        return set()
    parsed = urlparse(link)
    path = parsed.path or link
    return _tokens(path.replace("-", " ").replace("_", " "))


def _fetch_site_urls(website_url: str, limit: int = 120) -> list[str]:
    base = website_url.strip()
    if not base:
        return []
    if not base.startswith("http"):
        base = f"https://{base}"

    parsed = urlparse(base)
    origin = f"{parsed.scheme}://{parsed.netloc}"

    urls: list[str] = []

    try:
        r = httpx.get(urljoin(origin, "/sitemap.xml"), timeout=15.0)
        if r.status_code < 300:
            locs = re.findall(r"<loc>(.*?)</loc>", r.text, flags=re.IGNORECASE)
            for loc in locs:
                if loc and urlparse(loc).netloc == parsed.netloc:
                    urls.append(loc.strip())
    except Exception:
        pass

    if not urls:
        try:
            r = httpx.get(origin, timeout=15.0)
            if r.status_code < 300:
                hrefs = re.findall(r'href=["\']([^"\']+)["\']', r.text, flags=re.IGNORECASE)
                for href in hrefs:
                    full = urljoin(origin, href)
                    p = urlparse(full)
                    if p.netloc == parsed.netloc and p.scheme in {"http", "https"}:
                        urls.append(full)
        except Exception:
            pass

    deduped = []
    seen = set()
    for u in urls:
        if u in seen:
            continue
        seen.add(u)
        deduped.append(u)
        if len(deduped) >= limit:
            break
    return deduped


def _best_url_match(query_text: str, site_urls: list[str]) -> tuple[str | None, float]:
    q = _tokens(query_text)
    best_url = None
    best_sim = 0.0
    for url in site_urls:
        sim = _jaccard(q, _link_tokens(url))
        if sim > best_sim:
            best_sim = sim
            best_url = url
    return best_url, best_sim


def _rank_snapshot(timeseries: list[dict]) -> tuple[float | None, float, float]:
    if not timeseries:
        return None, 0.0, 0.0
    ordered = sorted(timeseries, key=lambda x: x.get("date", ""))
    latest = ordered[-1]
    positions = [float(x.get("position", 0) or 0) for x in ordered if float(x.get("position", 0) or 0) > 0]
    best_position = min(positions) if positions else None
    latest_impr = float(latest.get("impressions", 0) or 0)
    latest_clicks = float(latest.get("clicks", 0) or 0)
    return best_position, latest_impr, latest_clicks


def _best_gsc_query_match(query_text: str, gsc_records: list[dict]) -> tuple[dict | None, str | None, float]:
    best_row = None
    best_query = None
    best_sim = 0.0

    for row in gsc_records:
        candidate = str(row.get("query_text") or "").strip().lower()
        if not candidate:
            continue
        sim = _text_similarity(query_text, candidate)
        if sim > best_sim:
            best_sim = sim
            best_row = row
            best_query = candidate

    if best_sim < 0.35:
        return None, None, best_sim
    return best_row, best_query, best_sim


def _load_competitor_rows() -> list[dict]:
    rows: list[dict] = []
    try:
        rows.extend(SEMrushAdapter().normalize(SEMrushAdapter().fetch()))
    except Exception:
        pass
    try:
        rows.extend(AhrefsAdapter().normalize(AhrefsAdapter().fetch()))
    except Exception:
        pass
    return rows


def _best_competitor_gap(query_text: str, competitor_rows: list[dict]) -> tuple[float, str | None, str | None, float]:
    best_sim = 0.0
    best_gap = 0.0
    best_source = None
    best_query = None

    for row in competitor_rows:
        candidate = str(row.get("query_text") or "").strip().lower()
        if not candidate:
            continue
        sim = _text_similarity(query_text, candidate)
        gap = float(row.get("competitor_gap", 0.0) or 0.0)

        if sim > best_sim or (abs(sim - best_sim) < 1e-9 and gap > best_gap):
            best_sim = sim
            best_gap = gap
            best_source = str(row.get("source") or "")
            best_query = candidate

    if best_sim < 0.35:
        # conservative fallback when no direct integration match exists
        fallback = 0.55 if any(x in query_text for x in ["best", "vs", "software", "tool", "platform"]) else 0.4
        return fallback, None, None, best_sim

    return best_gap, best_source, best_query, best_sim


def _infer_intent(query_text: str) -> str:
    q = (query_text or "").lower()
    if any(x in q for x in ["buy", "pricing", "price", "vendor", "software", "tool", "platform", "service"]):
        return "commercial"
    if any(x in q for x in ["how", "what", "why", "guide", "checklist", "template", "best", "vs"]):
        return "informational"
    return "informational"


def _upsert_by_query_source(db: Session, payload: dict) -> QueryOpportunity:
    existing = (
        db.query(QueryOpportunity)
        .filter(QueryOpportunity.query_text == payload["query_text"], QueryOpportunity.source == payload["source"])
        .one_or_none()
    )
    if existing:
        for key, val in payload.items():
            setattr(existing, key, val)
        return existing

    row = QueryOpportunity(**payload)
    db.add(row)
    return row


def evaluate_manual_opportunity(db: Session, query_text: str, website_url: str) -> QueryOpportunity:
    query = _safe_query_text(query_text)
    if not query:
        raise ValueError("query_text is required")

    site_urls = _fetch_site_urls(website_url)
    matched_url, url_similarity = _best_url_match(query, site_urls)

    # Live/fallback GSC integration signal at evaluation time (not from stored opportunities).
    try:
        gsc_records = _load_gsc_records(db)
    except Exception:
        gsc_records = GSCAdapter().normalize(GSCAdapter().fetch())

    gsc_row, gsc_match_query, gsc_similarity = _best_gsc_query_match(query, gsc_records)
    gsc_timeseries = list((gsc_row or {}).get("timeseries") or [])
    gsc_links = [str(x) for x in ((gsc_row or {}).get("links") or []) if str(x).strip()]

    best_position, latest_impr, latest_clicks = _rank_snapshot(gsc_timeseries)
    ranking_well = bool(best_position is not None and best_position <= 12 and latest_impr >= 20)
    has_rank_signal = bool((best_position is not None and best_position <= 50) or latest_impr >= 10 or latest_clicks >= 1)

    if not matched_url and gsc_links:
        matched_url = gsc_links[0]
        url_similarity = max(url_similarity, 0.5)

    site_links = set(site_urls)
    for link in gsc_links:
        site_links.add(link)
    if matched_url:
        site_links.add(matched_url)

    has_existing_piece = bool(matched_url or has_rank_signal or url_similarity >= 0.45 or gsc_links)

    competitor_rows = _load_competitor_rows()
    competitor_gap, competitor_source, competitor_match_query, competitor_similarity = _best_competitor_gap(query, competitor_rows)

    opp_type, refresh_needed, _ = classify_opportunity_type(
        query_text=query,
        source="manual",
        competitor_gap=competitor_gap,
        gsc_row=gsc_row,
        site_links=site_links,
    )

    intent = _infer_intent(query)
    funnel = infer_funnel(query, intent)

    if gsc_timeseries:
        trend_score, trend_reason = detect_rising_query(gsc_timeseries)
    else:
        trend_score = 14.0 if "informational" in intent else 18.0
        trend_reason = "No GSC history for exact/near query; using heuristic baseline"

    ai_gap = 0.55 if any(x in query for x in ["how", "best", "vs"]) else 0.35

    score_components, priority, explanation, score_ratings, score_source, score_rationale = score_with_strategist(
        db,
        query_text=query,
        source="manual",
        intent=intent,
        funnel_stage=funnel,
        trend_score=trend_score,
        competitor_gap=competitor_gap,
        ai_citation_gap=ai_gap,
        refresh_needed=refresh_needed,
        gsc_row=gsc_row,
        link_count=(1 if matched_url else 0),
        opportunity_type=opp_type,
    )

    links = [matched_url] if matched_url else []
    brief = generate_brief(query, intent, funnel, [], links)
    snippets = recommend_snippets(intent, query)

    if opp_type == "refresh":
        actions = [
            "Refresh existing page title/H1 for query-match",
            "Add direct AI answer block + FAQ",
            "Improve section depth and citation-ready examples",
            "Strengthen internal links to demo and ROI pages",
        ]
    else:
        actions = [
            "Create net-new page targeting this long-tail prompt",
            "Use structured heading map with explicit answer blocks",
            "Include FAQ + schema for AI answer extraction",
            "Link from related high-authority pages",
        ]

    classification_reason = (
        f"manual_evaluator: has_existing_piece={has_existing_piece} (url_similarity={url_similarity:.2f}, matched_url={matched_url}), "
        f"ranking_well={ranking_well}, best_position={best_position}, impressions={latest_impr:.1f}, clicks={latest_clicks:.1f}, "
        f"gsc_query_similarity={gsc_similarity:.2f}, gsc_match_query={gsc_match_query}, "
        f"competitor_gap={competitor_gap:.2f}, competitor_source={competitor_source}, competitor_match_query={competitor_match_query}, competitor_similarity={competitor_similarity:.2f}"
    )

    payload = {
        "query_text": query,
        "source": "manual",
        "intent": intent,
        "funnel_stage": funnel,
        "trend_score": trend_score,
        "trend_reason": trend_reason,
        "refresh_needed": refresh_needed,
        "refresh_reason": classification_reason if opp_type == "refresh" else "",
        "ai_snippet_reco": snippets,
        "brief": brief,
        "priority_score": priority,
        "priority_explanation": explanation,
        "recommended_actions": actions,
        "links": links,
        "status": "backlog",
        "metadata_json": {
            "opportunity_type": opp_type,
            "classification_reason": classification_reason,
            "classifier_version": "manual_v2",
            "website_url": website_url,
            "matched_url": matched_url,
            "url_similarity": round(url_similarity, 3),
            "gsc_query_similarity": round(gsc_similarity, 3),
            "gsc_match_query": gsc_match_query,
            "gsc_best_position": best_position,
            "gsc_latest_impressions": latest_impr,
            "gsc_latest_clicks": latest_clicks,
            "ranking_well": ranking_well,
            "site_urls_checked": len(site_urls),
            "competitor_gap": competitor_gap,
            "competitor_source": competitor_source,
            "competitor_match_query": competitor_match_query,
            "competitor_similarity": round(competitor_similarity, 3),
            "score_components": score_components,
            "score_ratings": score_ratings,
            "score_source": score_source,
            "score_rationale": score_rationale,
        },
    }

    row = _upsert_by_query_source(db, payload)
    db.commit()
    db.refresh(row)
    return row
