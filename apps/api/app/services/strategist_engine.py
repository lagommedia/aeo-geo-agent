from __future__ import annotations

import json
import re
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.services.aeo_geo_agents import run_agent

# Main six strategist criteria used for final scoring.
SCORE_WEIGHTS = {
    "ai_query_volume": 20.0,
    "answer_likelihood": 15.0,
    "commercial_intent": 20.0,
    "ai_citation_gap": 15.0,
    "authority_leverage": 15.0,
    "content_coverage_gap": 15.0,
}

SCORE_CRITERIA_LABELS = {
    "ai_query_volume": "AI Query Volume",
    "answer_likelihood": "Answer Likelihood",
    "commercial_intent": "Commercial / Solution Intent",
    "ai_citation_gap": "AI Citation Gap",
    "authority_leverage": "Authority Leverage",
    "content_coverage_gap": "Content Coverage Gap",
}


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", (text or "").lower()))


def _link_tokens(link: str) -> set[str]:
    if not link:
        return set()
    parsed = urlparse(link)
    path = parsed.path or link
    return _tokens(path.replace("-", " ").replace("_", " "))


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def max_page_similarity(query_text: str, site_links: set[str]) -> float:
    q = _tokens(query_text)
    return max((_jaccard(q, _link_tokens(link)) for link in site_links), default=0.0)


def rank_snapshot(gsc_row: dict | None) -> dict:
    if not gsc_row:
        return {"best_position": None, "latest_position": None, "latest_impressions": 0.0, "latest_clicks": 0.0}

    series = gsc_row.get("timeseries") or []
    if not series:
        return {"best_position": None, "latest_position": None, "latest_impressions": 0.0, "latest_clicks": 0.0}

    ordered = sorted(series, key=lambda x: x.get("date", ""))
    latest = ordered[-1]
    positions = [float(x.get("position", 0) or 0) for x in ordered if float(x.get("position", 0) or 0) > 0]
    best_position = min(positions) if positions else None
    latest_position = float(latest.get("position", 0) or 0) or None
    return {
        "best_position": best_position,
        "latest_position": latest_position,
        "latest_impressions": float(latest.get("impressions", 0) or 0),
        "latest_clicks": float(latest.get("clicks", 0) or 0),
    }


def classify_opportunity_type(
    *,
    query_text: str,
    source: str,
    competitor_gap: float,
    gsc_row: dict | None,
    site_links: set[str],
) -> tuple[str, bool, str]:
    if source == "community":
        return "community", False, "Community-sourced opportunity"

    snapshot = rank_snapshot(gsc_row)
    best = snapshot["best_position"]
    latest_impr = snapshot["latest_impressions"]
    latest_clicks = snapshot["latest_clicks"]

    has_rank_presence = best is not None
    has_rank_signal = has_rank_presence or latest_impr >= 10 or latest_clicks >= 1

    # User rule: if we are already in search results but not page one (>10), this is a refresh opportunity.
    in_search_results_not_page_one = bool(best is not None and best > 10)
    ranking_well = bool(best is not None and best <= 10)

    similarity = max_page_similarity(query_text, site_links)
    has_owned_page_link = bool(gsc_row and isinstance(gsc_row.get("links"), list) and len(gsc_row.get("links") or []) > 0)
    has_existing_piece = has_rank_signal or similarity >= 0.45 or has_owned_page_link

    if has_existing_piece:
        reason = (
            f"Existing rank/impression signal detected (best_position={best}, impressions={latest_impr:.1f}, "
            f"clicks={latest_clicks:.1f}, page_similarity={similarity:.2f}, has_owned_page_link={has_owned_page_link})"
        )
        refresh_needed = True if has_owned_page_link else (in_search_results_not_page_one or (has_rank_presence and not ranking_well))
        return "refresh", refresh_needed, reason

    if competitor_gap >= 0.55:
        return "new", False, f"High competitor gap with low overlap/rank signal (competitor_gap={competitor_gap:.2f})"

    return "new", False, "No meaningful rank signal and low overlap; classify net-new"


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _intent_norm(intent: str) -> float:
    i = (intent or "").lower()
    if i == "transactional":
        return 0.95
    if i == "commercial":
        return 0.85
    if i == "informational":
        return 0.6
    return 0.45


def compute_score_components(
    *,
    query_text: str,
    intent: str,
    trend_score: float,
    competitor_gap: float,
    ai_citation_gap: float,
    refresh_needed: bool,
    gsc_row: dict | None,
    link_count: int,
) -> tuple[dict[str, float], float, str]:
    q = (query_text or "").lower()
    snapshot = rank_snapshot(gsc_row)
    best_pos = snapshot["best_position"]

    query_volume_norm = _clamp(
        (trend_score / 40.0) * 0.75 + (competitor_gap * 0.15) + (0.1 if any(x in q for x in ["how", "best", "vs", "what"]) else 0.0),
        0.0,
        1.0,
    )
    answer_likelihood_norm = _clamp(
        (0.8 if any(x in q for x in ["how", "what", "why", "guide", "best", "vs"]) else 0.55)
        + (0.08 if (intent or "").lower() == "informational" else 0.0),
        0.0,
        1.0,
    )
    commercial_norm = _clamp(_intent_norm(intent), 0.0, 1.0)
    ai_gap_norm = _clamp(
        ai_citation_gap if ai_citation_gap > 0 else (0.45 if any(x in q for x in ["software", "tool", "platform", "services"]) else 0.3),
        0.0,
        1.0,
    )
    authority_norm = _clamp(0.3 + min(link_count, 6) * 0.1 + (0.1 if best_pos and best_pos <= 20 else 0.0), 0.0, 1.0)
    coverage_norm = _clamp(0.82 if refresh_needed else (0.58 if best_pos and best_pos <= 50 else 0.72), 0.0, 1.0)

    norms = {
        "ai_query_volume": query_volume_norm,
        "answer_likelihood": answer_likelihood_norm,
        "commercial_intent": commercial_norm,
        "ai_citation_gap": ai_gap_norm,
        "authority_leverage": authority_norm,
        "content_coverage_gap": coverage_norm,
    }

    components = {k: round(_clamp(norms[k] * SCORE_WEIGHTS[k], 0.0, SCORE_WEIGHTS[k]), 2) for k in SCORE_WEIGHTS}
    total = round(sum(components.values()), 2)
    explanation = ", ".join([f"{k}={components[k]}/{int(SCORE_WEIGHTS[k])}" for k in SCORE_WEIGHTS])
    return components, total, explanation


def strategist_agent_decision(
    db: Session,
    *,
    query_text: str,
    source: str,
    intent: str,
    trend_score: float,
    competitor_gap: float,
    ai_citation_gap: float,
    classification_reason: str,
) -> dict | None:
    prompt = (
        "Return JSON only with keys: opportunity_type, confidence, rationale. "
        "opportunity_type must be one of new, refresh, community. "
        "Use best-practice AEO/GEO/SEO cannibalization logic."
    )
    context = {
        "query_text": query_text,
        "source": source,
        "intent": intent,
        "trend_score": trend_score,
        "competitor_gap": competitor_gap,
        "ai_citation_gap": ai_citation_gap,
        "heuristic_reason": classification_reason,
    }

    try:
        response = run_agent(db, "strategist", prompt, context=context)
        out = response.get("output") or ""
        m = re.search(r"\{[\s\S]*\}", out)
        if not m:
            return None
        payload = json.loads(m.group(0))
        opp_type = str(payload.get("opportunity_type", "")).strip().lower()
        if opp_type not in {"new", "refresh", "community"}:
            return None
        return {
            "opportunity_type": opp_type,
            "confidence": float(payload.get("confidence", 0.0) or 0.0),
            "rationale": str(payload.get("rationale", "")).strip(),
        }
    except Exception:
        return None


def _extract_first_json(text: str) -> dict | None:
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        pass

    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def _ratings_to_points(ratings: dict[str, float]) -> tuple[dict[str, float], float, str]:
    components: dict[str, float] = {}
    for key, weight in SCORE_WEIGHTS.items():
        rating = float(ratings.get(key, 0.0) or 0.0)
        rating = _clamp(rating, 0.0, 10.0)
        components[key] = round((rating / 10.0) * weight, 2)

    total = round(sum(components.values()), 2)
    explanation = ", ".join([f"{k}={components[k]}/{int(SCORE_WEIGHTS[k])}" for k in SCORE_WEIGHTS])
    return components, total, explanation


def _fallback_ratings_from_components(components: dict[str, float]) -> dict[str, float]:
    out: dict[str, float] = {}
    for key, weight in SCORE_WEIGHTS.items():
        val = float(components.get(key, 0.0) or 0.0)
        out[key] = round(_clamp((val / weight) * 10.0, 0.0, 10.0), 2)
    return out


def score_with_strategist(
    db: Session,
    *,
    query_text: str,
    source: str,
    intent: str,
    funnel_stage: str,
    trend_score: float,
    competitor_gap: float,
    ai_citation_gap: float,
    refresh_needed: bool,
    gsc_row: dict | None,
    link_count: int,
    opportunity_type: str,
) -> tuple[dict[str, float], float, str, dict[str, float], str, str | None]:
    snapshot = rank_snapshot(gsc_row)
    prompt = (
        "Score this opportunity for AEO/GEO prioritization. "
        "Use the six required criteria and return JSON only with exact keys: "
        "ratings, rationale. "
        "ratings must contain numeric values 0-10 for: "
        "ai_query_volume, answer_likelihood, commercial_intent, ai_citation_gap, authority_leverage, content_coverage_gap. "
        "Keep rationale concise and specific."
    )
    context = {
        "query_text": query_text,
        "source": source,
        "opportunity_type": opportunity_type,
        "intent": intent,
        "funnel_stage": funnel_stage,
        "trend_score": trend_score,
        "competitor_gap": competitor_gap,
        "ai_citation_gap": ai_citation_gap,
        "refresh_needed": refresh_needed,
        "best_position": snapshot.get("best_position"),
        "latest_position": snapshot.get("latest_position"),
        "latest_impressions": snapshot.get("latest_impressions"),
        "latest_clicks": snapshot.get("latest_clicks"),
        "link_count": link_count,
        "criteria_weights": SCORE_WEIGHTS,
    }

    try:
        response = run_agent(db, "strategist", prompt, context=context)
        payload = _extract_first_json(response.get("output") or "")
        ratings_raw = payload.get("ratings") if isinstance(payload, dict) else None
        if isinstance(ratings_raw, dict):
            ratings = {}
            for key in SCORE_WEIGHTS:
                ratings[key] = round(_clamp(float(ratings_raw.get(key, 0.0) or 0.0), 0.0, 10.0), 2)
            components, total, explanation = _ratings_to_points(ratings)
            rationale = str(payload.get("rationale", "")).strip() if isinstance(payload, dict) else ""
            return components, total, explanation, ratings, "strategist_agent", (rationale or None)
    except Exception:
        pass

    # Deterministic fallback if strategist scoring is unavailable.
    components, total, explanation = compute_score_components(
        query_text=query_text,
        intent=intent,
        trend_score=trend_score,
        competitor_gap=competitor_gap,
        ai_citation_gap=ai_citation_gap,
        refresh_needed=refresh_needed,
        gsc_row=gsc_row,
        link_count=link_count,
    )
    ratings = _fallback_ratings_from_components(components)
    return components, total, explanation, ratings, "heuristic_fallback", None


def decision_confidence(
    *,
    opportunity_type: str,
    competitor_gap: float,
    gsc_row: dict | None,
    site_similarity: float,
) -> float:
    snap = rank_snapshot(gsc_row)
    best = snap["best_position"]
    impr = snap["latest_impressions"]
    clicks = snap["latest_clicks"]

    conf = 0.45
    if opportunity_type == "refresh":
        if best is not None and best <= 20:
            conf += 0.25
        if impr >= 20 or clicks >= 2:
            conf += 0.2
        if site_similarity >= 0.45:
            conf += 0.1
    elif opportunity_type == "new":
        conf += min(0.25, competitor_gap * 0.25)
        if best is None and impr < 5 and clicks < 1:
            conf += 0.15
        if site_similarity < 0.3:
            conf += 0.1
    elif opportunity_type == "community":
        conf += 0.25

    return round(_clamp(conf, 0.0, 0.99), 2)


def should_include_candidate(
    *,
    opportunity_type: str,
    priority_score: float,
    competitor_gap: float,
    gsc_row: dict | None,
    query_text: str,
    confidence: float,
) -> tuple[bool, str]:
    q = (query_text or "").strip()
    if not q:
        return False, "empty_query"
    if len(q) < 3:
        return False, "query_too_short"

    snap = rank_snapshot(gsc_row)
    best = snap["best_position"]
    impr = snap["latest_impressions"]
    clicks = snap["latest_clicks"]

    if confidence < 0.5:
        return False, "low_confidence"

    if opportunity_type == "new":
        if priority_score < 40 and competitor_gap < 0.55:
            return False, "new_low_signal"
    elif opportunity_type == "refresh":
        if best is None and impr < 8 and clicks < 1 and priority_score < 40:
            return False, "refresh_low_signal"
    elif opportunity_type == "community":
        if priority_score < 35:
            return False, "community_low_signal"

    return True, "accepted"
