from __future__ import annotations

import json
import re
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.models.opportunity import QueryOpportunity
from app.services.adapters.ahrefs_adapter import AhrefsAdapter
from app.services.adapters.semrush_adapter import SEMrushAdapter
from app.services.aeo_geo_agents import run_agent
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


def _best_gsc_query_match(query_text: str, gsc_records: list[dict]) -> tuple[dict | None, float]:
    best_row = None
    best_sim = 0.0
    for row in gsc_records:
        candidate = str(row.get("query_text") or "").strip().lower()
        if not candidate:
            continue
        sim = _text_similarity(query_text, candidate)
        if sim > best_sim:
            best_sim = sim
            best_row = row
    if best_sim < 0.55:
        return None, best_sim
    return best_row, best_sim


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


def _best_competitor_gap(query_text: str, rows: list[dict]) -> float:
    best_sim = 0.0
    best_gap = 0.0
    for row in rows:
        candidate = str(row.get("query_text") or "").strip().lower()
        if not candidate:
            continue
        sim = _text_similarity(query_text, candidate)
        gap = float(row.get("competitor_gap", 0.0) or 0.0)
        if sim > best_sim or (abs(sim - best_sim) < 1e-9 and gap > best_gap):
            best_sim = sim
            best_gap = gap
    if best_sim < 0.35:
        return 0.45
    return best_gap


def _extract_json(text: str) -> dict | None:
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


def _infer_intent_from_query(query_text: str) -> str:
    q = (query_text or "").lower()
    if any(x in q for x in ["buy", "pricing", "price", "vendor", "software", "tool", "platform", "service"]):
        return "commercial"
    if any(x in q for x in ["how", "what", "why", "guide", "checklist", "template", "best", "vs"]):
        return "informational"
    return "informational"




def _fallback_candidates_from_competitors(
    competitor_rows: list[dict],
    existing_queries: list[str],
    limit: int,
) -> list[dict]:
    existing = set(q for q in existing_queries if q)
    out: list[dict] = []
    seen: set[str] = set()

    sorted_rows = sorted(
        [r for r in competitor_rows if str(r.get("query_text") or "").strip()],
        key=lambda r: float(r.get("competitor_gap", 0.0) or 0.0),
        reverse=True,
    )

    for row in sorted_rows:
        q = _safe_query_text(str(row.get("query_text") or ""))
        if not q or q in seen:
            continue
        seen.add(q)

        overlap = max((_text_similarity(q, ex) for ex in existing), default=0.0)
        if overlap >= 0.72:
            continue

        out.append({
            "query_text": q,
            "intent": str(row.get("intent") or _infer_intent_from_query(q)),
            "why_now": f"Competitor gap {float(row.get('competitor_gap', 0.0) or 0.0):.2f} from {row.get('source')}",
            "aeo_geo_angle": "High gap topic likely to benefit from answer-first, citation-friendly content",
        })
        if len(out) >= max(limit * 3, 18):
            break

    return out

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


def discover_new_opportunities(db: Session, website_url: str, limit: int = 15, seed_prompt: str | None = None) -> dict:
    existing_queries = [
        str(row.query_text or "").strip().lower()
        for row in db.query(QueryOpportunity).all()
        if str(row.query_text or "").strip()
    ]

    prompt = (
        "Return JSON only: {\"candidates\":[...]} where each candidate has keys "
        "query_text, intent, why_now, aeo_geo_angle. "
        "Generate high-value net-new AEO/GEO long-tail opportunities for zeni.ai. "
        "These are NEW opportunities only, not refresh opportunities. "
        "Do not use Google Search Console behavior or existing ranking terms for ideation. "
        "Use the provided seed_prompt as a hard directional constraint for inclusion, exclusion, and thematic focus. "
        "If the seed_prompt excludes a topic, do not return candidates in that topic. "
        "Keep candidates concise, unique, commercially relevant, and citation-friendly."
    )

    context = {
        "website_url": website_url,
        "seed_prompt": seed_prompt or "",
        "max_candidates": max(limit * 3, 18),
        "existing_query_samples": existing_queries[:120],
        "selection_goal": "new_only",
        "discovery_method": "openai_strategist_only",
    }

    try:
        response = run_agent(db, "strategist", prompt, context=context)
        payload = _extract_json(response.get("output") or "") or {}
        candidates = payload.get("candidates") if isinstance(payload, dict) else None
        if not isinstance(candidates, list):
            candidates = []
        candidate_source = "strategist_agent"
    except Exception:
        candidates = []
        candidate_source = "strategist_agent"

    created: list[QueryOpportunity] = []
    skipped = 0
    seen_queries: set[str] = set()

    for cand in candidates:
        if len(created) >= limit:
            break
        if not isinstance(cand, dict):
            skipped += 1
            continue

        query_text = _safe_query_text(str(cand.get("query_text") or ""))
        if not query_text or query_text in seen_queries or query_text in existing_queries:
            skipped += 1
            continue
        seen_queries.add(query_text)

        intent = str(cand.get("intent") or "").strip().lower()
        if intent not in {"informational", "commercial", "transactional"}:
            intent = _infer_intent_from_query(query_text)
        funnel = infer_funnel(query_text, intent)

        trend_score = 22.0
        trend_reason = "Strategist new-opportunity baseline"
        competitor_gap = 0.5
        ai_gap = 0.55
        classify_reason = "OpenAI strategist generated net-new opportunity from current strategic constraints"

        score_components, priority, explanation, score_ratings, score_source, score_rationale = score_with_strategist(
            db,
            query_text=query_text,
            source="strategist_new",
            intent=intent,
            funnel_stage=funnel,
            trend_score=trend_score,
            competitor_gap=competitor_gap,
            ai_citation_gap=ai_gap,
            refresh_needed=False,
            gsc_row=None,
            link_count=0,
            opportunity_type="new",
        )

        brief = generate_brief(query_text, intent, funnel, [], [])
        snippets = recommend_snippets(intent, query_text)

        payload_row = {
            "query_text": query_text,
            "source": "strategist_new",
            "intent": intent,
            "funnel_stage": funnel,
            "trend_score": trend_score,
            "trend_reason": trend_reason,
            "refresh_needed": False,
            "refresh_reason": "",
            "ai_snippet_reco": snippets,
            "brief": brief,
            "priority_score": priority,
            "priority_explanation": explanation,
            "recommended_actions": [
                "Create net-new page targeting this long-tail prompt",
                "Anchor title/H1 tightly to query intent",
                "Add answer-first summary + FAQ + schema",
                "Link from highest-authority related pages",
            ],
            "links": [],
            "status": "backlog",
            "metadata_json": {
                "opportunity_type": "new",
                "classification_reason": classify_reason,
                "classifier_version": "strategist_new_v2",
                "seed_prompt": seed_prompt,
                "strategist_candidate": {
                    "source": candidate_source,
                    "why_now": str(cand.get("why_now") or "").strip(),
                    "aeo_geo_angle": str(cand.get("aeo_geo_angle") or "").strip(),
                },
                "score_components": score_components,
                "score_ratings": score_ratings,
                "score_source": score_source,
                "score_rationale": score_rationale,
                "discovery_method": "openai_strategist_only",
            },
        }

        row = _upsert_by_query_source(db, payload_row)
        created.append(row)

    db.commit()
    for row in created:
        db.refresh(row)

    return {
        "created_count": len(created),
        "skipped_count": skipped,
        "opportunities": created,
    }


def discover_refresh_opportunities(db: Session, website_url: str, limit: int = 15, seed_prompt: str | None = None) -> dict:
    gsc_records = _load_gsc_records(db)
    usable_gsc = [
        row for row in gsc_records
        if str(row.get("query_text") or "").strip()
    ]

    if not usable_gsc:
        return {
            "created_count": 0,
            "skipped_count": 0,
            "opportunities": [],
        }

    existing_refresh_queries = {
        str(row.query_text or "").strip().lower()
        for row in db.query(QueryOpportunity).all()
        if str(row.query_text or "").strip()
    }

    top_queries = []
    for row in usable_gsc[:150]:
        top_queries.append({
            "query_text": str(row.get("query_text") or "").strip(),
            "clicks": float(row.get("clicks", 0.0) or 0.0),
            "impressions": float(row.get("impressions", 0.0) or 0.0),
            "position": float(row.get("position", 0.0) or 0.0),
            "url": str(row.get("page") or row.get("url") or "").strip(),
        })

    prompt = (
        "Return JSON only: {\"candidates\":[...]} where each candidate has keys "
        "query_text, intent, why_now, aeo_geo_angle, existing_url, keep, remove, add. "
        "These are REFRESH opportunities only. Use current ranking/impression terms from the company site, "
        "find pages/terms that should be refreshed, and prioritize terms with commercial or answer-engine upside. "
        "Do not invent net-new opportunities unrelated to existing site visibility. "
        "Use the seed_prompt as a hard constraint for inclusion, exclusion, and thematic focus."
    )

    context = {
        "website_url": website_url,
        "seed_prompt": seed_prompt or "",
        "max_candidates": max(limit * 3, 18),
        "selection_goal": "refresh_only",
        "ranking_terms": top_queries,
        "discovery_method": "openai_refresh_strategist",
    }

    try:
        response = run_agent(db, "refresh", prompt, context=context)
        payload = _extract_json(response.get("output") or "") or {}
        candidates = payload.get("candidates") if isinstance(payload, dict) else None
        if not isinstance(candidates, list):
            candidates = []
        candidate_source = "refresh_agent"
    except Exception:
        candidates = []
        candidate_source = "refresh_agent"

    created: list[QueryOpportunity] = []
    skipped = 0
    seen_queries: set[str] = set()

    for cand in candidates:
        if len(created) >= limit:
            break
        if not isinstance(cand, dict):
            skipped += 1
            continue

        query_text = _safe_query_text(str(cand.get("query_text") or ""))
        if not query_text or query_text in seen_queries or query_text in existing_refresh_queries:
            skipped += 1
            continue
        seen_queries.add(query_text)

        intent = str(cand.get("intent") or "").strip().lower()
        if intent not in {"informational", "commercial", "transactional"}:
            intent = _infer_intent_from_query(query_text)

        funnel = infer_funnel(query_text, intent)
        gsc_row, _ = _best_gsc_query_match(query_text, usable_gsc)
        if not gsc_row:
            skipped += 1
            continue

        link_count = 1 if str(cand.get("existing_url") or gsc_row.get("page") or gsc_row.get("url") or "").strip() else 0
        trend_score = 28.0
        competitor_gap = 0.45
        ai_gap = 0.5
        classify_reason = "OpenAI refresh strategist identified an existing ranking term/page that should be improved instead of creating net-new content"

        score_components, priority, explanation, score_ratings, score_source, score_rationale = score_with_strategist(
            db,
            query_text=query_text,
            source="refresh_scan",
            intent=intent,
            funnel_stage=funnel,
            trend_score=trend_score,
            competitor_gap=competitor_gap,
            ai_citation_gap=ai_gap,
            refresh_needed=True,
            gsc_row=gsc_row,
            link_count=link_count,
            opportunity_type="refresh",
        )

        brief = generate_brief(query_text, intent, funnel, [], [])
        snippets = recommend_snippets(intent, query_text)

        payload_row = {
            "query_text": query_text,
            "source": "refresh_scan",
            "intent": intent,
            "funnel_stage": funnel,
            "trend_score": trend_score,
            "trend_reason": "Existing ranking/impression term selected for refresh opportunity",
            "refresh_needed": True,
            "refresh_reason": str(cand.get("why_now") or "Existing page/term underperforming relative to refresh potential").strip(),
            "ai_snippet_reco": snippets,
            "brief": brief,
            "priority_score": priority,
            "priority_explanation": explanation,
            "recommended_actions": [
                "Refresh the existing page instead of creating a net-new asset",
                "Tighten title/H1 and answer-first summary to the target query",
                "Improve depth, structure, FAQ, and schema coverage",
                "Preserve intent alignment and avoid cannibalization",
            ],
            "links": [str(cand.get("existing_url") or gsc_row.get("page") or gsc_row.get("url") or "").strip()] if str(cand.get("existing_url") or gsc_row.get("page") or gsc_row.get("url") or "").strip() else [],
            "status": "backlog",
            "metadata_json": {
                "opportunity_type": "refresh",
                "classification_reason": classify_reason,
                "classifier_version": "refresh_strategist_v1",
                "seed_prompt": seed_prompt,
                "refresh_candidate": {
                    "source": candidate_source,
                    "why_now": str(cand.get("why_now") or "").strip(),
                    "aeo_geo_angle": str(cand.get("aeo_geo_angle") or "").strip(),
                    "keep": str(cand.get("keep") or "").strip(),
                    "remove": str(cand.get("remove") or "").strip(),
                    "add": str(cand.get("add") or "").strip(),
                    "existing_url": str(cand.get("existing_url") or gsc_row.get("page") or gsc_row.get("url") or "").strip(),
                },
                "score_components": score_components,
                "score_ratings": score_ratings,
                "score_source": score_source,
                "score_rationale": score_rationale,
                "discovery_method": "openai_refresh_strategist",
            },
        }

        row = _upsert_by_query_source(db, payload_row)
        created.append(row)

    db.commit()
    for row in created:
        db.refresh(row)

    return {
        "created_count": len(created),
        "skipped_count": skipped,
        "opportunities": created,
    }
