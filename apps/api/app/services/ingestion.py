from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
import re
from urllib.parse import urlparse

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.secrets import decrypt_secret, encrypt_secret
from app.models.opportunity import QueryOpportunity
from app.models.run_history import RunHistory
from app.models.source_config import SourceConfig
from app.services.adapters.ahrefs_adapter import AhrefsAdapter
from app.services.adapters.citations_adapter import CitationMonitorAdapter
from app.services.adapters.competitor_velocity import CompetitorVelocityAdapter
from app.services.adapters.gsc_adapter import GSCAdapter
from app.services.adapters.gsc_live_adapter import GSCLiveAdapter
from app.services.adapters.semrush_adapter import SEMrushAdapter
from app.services.briefs import generate_brief, infer_funnel, recommend_snippets
from app.services.detectors import detect_refresh_need, detect_rising_query
from app.services.strategist_engine import (
    classify_opportunity_type as classify_opportunity_type_engine,
    decision_confidence,
    score_with_strategist,
    should_include_candidate,
)


def _upsert_opportunity(db: Session, payload: dict) -> QueryOpportunity:
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


def _refresh_gsc_token_if_needed(source_row: SourceConfig) -> str | None:
    config = source_row.config or {}
    oauth = config.get("oauth", {})
    access_token = oauth.get("access_token")
    refresh_token = oauth.get("refresh_token")
    expires_at = oauth.get("expires_at")

    if access_token:
        access_token = decrypt_secret(access_token)

    if not refresh_token:
        return access_token

    if not settings.google_oauth_client_id or not settings.google_oauth_client_secret:
        return access_token

    should_refresh = True
    if expires_at:
        try:
            should_refresh = datetime.now(timezone.utc) >= datetime.fromisoformat(expires_at) - timedelta(minutes=2)
        except ValueError:
            should_refresh = True

    if not should_refresh:
        return access_token

    refresh_token = decrypt_secret(refresh_token)
    response = httpx.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": settings.google_oauth_client_id,
            "client_secret": settings.google_oauth_client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=20.0,
    )
    if response.status_code >= 300:
        return access_token

    payload = response.json()
    new_access_token = payload.get("access_token")
    if not new_access_token:
        return access_token

    oauth["access_token"] = encrypt_secret(new_access_token)
    oauth["expires_at"] = (datetime.now(timezone.utc) + timedelta(seconds=int(payload.get("expires_in", 3600)))).isoformat()
    config["oauth"] = oauth
    source_row.config = config
    return new_access_token


def _load_gsc_records(db: Session) -> list[dict]:
    source_row = db.query(SourceConfig).filter(SourceConfig.source_name == "gsc").one_or_none()
    if not source_row:
        return GSCAdapter().normalize(GSCAdapter().fetch())

    config = source_row.config or {}
    site_url = config.get("site_url") or settings.gsc_site_url
    if source_row.status != "connected" or not site_url:
        return GSCAdapter().normalize(GSCAdapter().fetch())

    access_token = _refresh_gsc_token_if_needed(source_row)
    if not access_token:
        return GSCAdapter().normalize(GSCAdapter().fetch())

    try:
        live_rows = GSCLiveAdapter(access_token=access_token, site_url=site_url).fetch()
        if not live_rows:
            return GSCAdapter().normalize(GSCAdapter().fetch())
        db.commit()
        return GSCAdapter().normalize(live_rows)
    except Exception:
        return GSCAdapter().normalize(GSCAdapter().fetch())


def _tokens(text: str) -> set[str]:
    raw = re.findall(r"[a-z0-9]+", (text or "").lower())
    out: set[str] = set()
    for tok in raw:
        out.add(tok)
        if tok.endswith("ies") and len(tok) > 4:
            out.add(tok[:-3] + "y")
        elif tok.endswith("s") and len(tok) > 3:
            out.add(tok[:-1])
    return out


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


def _max_page_similarity(query_text: str, site_links: set[str]) -> float:
    q = _tokens(query_text)
    return max((_jaccard(q, _link_tokens(link)) for link in site_links), default=0.0)


def _safe_query_text(value: str, limit: int = 500) -> str:
    return (value or "").strip().lower()[:limit]


def _best_gsc_query_match(query_text: str, gsc_records: list[dict], min_similarity: float = 0.35) -> tuple[dict | None, str | None, float]:
    q = (query_text or "").strip().lower()
    q_tokens = _tokens(q)
    best_row = None
    best_query = None
    best_similarity = 0.0

    for row in gsc_records:
        candidate_query = str(row.get("query_text", "") or "").strip().lower()
        if not candidate_query:
            continue

        similarity = _jaccard(q_tokens, _tokens(candidate_query))
        if (q and candidate_query and (q in candidate_query or candidate_query in q)) and similarity < 0.72:
            similarity = 0.72

        if similarity > best_similarity:
            best_similarity = similarity
            best_row = row
            best_query = candidate_query

    if best_similarity < min_similarity:
        return None, None, best_similarity
    return best_row, best_query, best_similarity


def classify_opportunity_type(query_text: str, competitor_gap: float, gsc_row: dict | None, site_links: set[str]) -> tuple[str, str]:
    # Backward-compatible wrapper used by current tests.
    opp_type, _refresh_needed, reason = classify_opportunity_type_engine(
        query_text=query_text,
        source="gsc",
        competitor_gap=competitor_gap,
        gsc_row=gsc_row,
        site_links=site_links,
    )
    return opp_type, reason


def run_ingestion(db: Session) -> dict:
    run = RunHistory(run_type="nightly_ingestion", status="running", details={})
    db.add(run)
    db.commit()

    inserted = 0
    created_by_type: Counter[str] = Counter()
    skipped_by_reason: Counter[str] = Counter()
    seen_keys: set[tuple[str, str]] = set()
    max_by_type = {"new": 300, "refresh": 900, "community": 200}

    try:
        gsc_records = _load_gsc_records(db)
        citations = CitationMonitorAdapter().normalize(CitationMonitorAdapter().fetch())
        semrush = SEMrushAdapter().normalize(SEMrushAdapter().fetch())
        ahrefs = AhrefsAdapter().normalize(AhrefsAdapter().fetch())
        competitor_weeks = CompetitorVelocityAdapter().normalize(CompetitorVelocityAdapter().fetch())

        gsc_map = {row["query_text"]: row for row in gsc_records}
        site_links = set()
        for row in gsc_records:
            for link in row.get("links", []):
                if link:
                    site_links.add(link)

        competitor_map: dict[str, float] = {}
        for row in semrush + ahrefs:
            q = row["query_text"]
            competitor_map[q] = max(competitor_map.get(q, 0.0), float(row.get("competitor_gap", 0.0)))

        citation_map: dict[str, float] = {}
        for row in citations:
            gap = 1.0 if row.get("brand_mentioned") and not row.get("brand_cited") else 0.0
            citation_map[row["query_text"]] = max(citation_map.get(row["query_text"], 0.0), gap)

        def _persist(payload: dict, opp_type: str, confidence: float, competitor_gap: float, gsc_row: dict | None) -> None:
            nonlocal inserted
            key = (str(payload.get("query_text") or ""), str(payload.get("source") or ""))
            if key in seen_keys:
                skipped_by_reason["duplicate_in_run"] += 1
                return
            seen_keys.add(key)

            if created_by_type.get(opp_type, 0) >= max_by_type.get(opp_type, 300):
                skipped_by_reason[f"cap_{opp_type}"] += 1
                return

            keep, reason = should_include_candidate(
                opportunity_type=opp_type,
                priority_score=float(payload.get("priority_score") or 0.0),
                competitor_gap=competitor_gap,
                gsc_row=gsc_row,
                query_text=str(payload.get("query_text") or ""),
                confidence=confidence,
            )
            if not keep:
                skipped_by_reason[reason] += 1
                return

            _upsert_opportunity(db, payload)
            inserted += 1
            created_by_type[opp_type] += 1

        # GSC-backed opportunities
        for row in gsc_records:
            query_text = str(row.get("query_text") or "").strip().lower()
            if not query_text:
                skipped_by_reason["empty_query"] += 1
                continue

            trend, trend_reason = detect_rising_query(row["timeseries"])
            refresh_needed, refresh_reason = detect_refresh_need(row["timeseries"])
            intent = "commercial" if any(x in query_text for x in ["software", "platform", "outsourced", "automation"]) else "informational"
            funnel = infer_funnel(query_text, intent)
            ai_gap = citation_map.get(query_text, 0.0)
            competitor_gap = competitor_map.get(query_text, 0.0)

            gsc_row = row
            gsc_match_query = query_text
            gsc_match_similarity = 1.0

            opp_type, refresh_flag, opp_reason = classify_opportunity_type_engine(
                query_text=query_text,
                source="gsc",
                competitor_gap=competitor_gap,
                gsc_row=gsc_row,
                site_links=site_links,
            )

            score_components, priority, explanation, score_ratings, score_source, score_rationale = score_with_strategist(
                db,
                query_text=query_text,
                source="gsc",
                intent=intent,
                funnel_stage=funnel,
                trend_score=trend,
                competitor_gap=competitor_gap,
                ai_citation_gap=ai_gap,
                refresh_needed=refresh_flag or refresh_needed,
                gsc_row=gsc_row,
                link_count=len(row.get("links", [])),
                opportunity_type=opp_type,
            )

            snippets = recommend_snippets(intent, query_text)
            brief = generate_brief(query_text, intent, funnel, [], row.get("links", []))
            site_similarity = _max_page_similarity(query_text, site_links)
            confidence = decision_confidence(
                opportunity_type=opp_type,
                competitor_gap=competitor_gap,
                gsc_row=gsc_row,
                site_similarity=site_similarity,
            )

            payload = {
                "query_text": _safe_query_text(query_text),
                "source": "gsc",
                "intent": intent,
                "funnel_stage": funnel,
                "trend_score": trend,
                "trend_reason": trend_reason,
                "refresh_needed": refresh_flag or refresh_needed,
                "refresh_reason": refresh_reason,
                "ai_snippet_reco": snippets,
                "brief": brief,
                "priority_score": priority,
                "priority_explanation": explanation,
                "recommended_actions": [
                    "Refresh title/H1 for query-match",
                    "Add AI answer block + FAQ",
                    "Strengthen internal links to demo and ROI pages",
                ] + (["Update existing page with fresh examples, stats, and improved heading structure"] if (refresh_needed or opp_type == "refresh") else []) + (["Create citation-friendly definitions and outreach targets"] if ai_gap > 0 else []),
                "links": row.get("links", []),
                "status": "backlog",
                "metadata_json": {
                    "timeseries": row.get("timeseries", []),
                    "opportunity_type": opp_type,
                    "classification_reason": opp_reason,
                    "classifier_version": "v2",
                    "classifier_inputs": {
                        "gsc_match_query": gsc_match_query,
                        "gsc_match_similarity": round(gsc_match_similarity, 3),
                        "competitor_gap": competitor_gap,
                    },
                    "score_components": score_components,
                    "score_ratings": score_ratings,
                    "score_source": score_source,
                    "score_rationale": score_rationale,
                    "strategist_confidence": confidence,
                },
            }
            _persist(payload, opp_type, confidence, competitor_gap, gsc_row)

        # Community / citation opportunities
        for row in citations:
            if not (row.get("brand_mentioned") and not row.get("brand_cited")):
                continue

            query = str(row.get("query_text") or "").strip().lower()
            if not query:
                skipped_by_reason["empty_query"] += 1
                continue

            competitor_gap = 0.3
            gsc_row = gsc_map.get(query)
            gsc_match_query = query if gsc_row else None
            gsc_match_similarity = 1.0 if gsc_row else 0.0
            if not gsc_row:
                gsc_row, gsc_match_query, gsc_match_similarity = _best_gsc_query_match(query, gsc_records)

            opp_type, refresh_flag, opp_reason = classify_opportunity_type_engine(
                query_text=query,
                source="community",
                competitor_gap=competitor_gap,
                gsc_row=gsc_row,
                site_links=site_links,
            )
            if gsc_match_query:
                opp_reason = f"{opp_reason} | matched_gsc_query={gsc_match_query} (sim={gsc_match_similarity:.2f})"

            score_components, priority, explanation, score_ratings, score_source, score_rationale = score_with_strategist(
                db,
                query_text=query,
                source="community",
                intent="commercial",
                funnel_stage="MOFU",
                trend_score=18,
                competitor_gap=competitor_gap,
                ai_citation_gap=1.0,
                refresh_needed=refresh_flag,
                gsc_row=gsc_row,
                link_count=len(row.get("cited_urls", [])),
                opportunity_type=opp_type,
            )
            site_similarity = _max_page_similarity(query, site_links)
            confidence = decision_confidence(
                opportunity_type=opp_type,
                competitor_gap=competitor_gap,
                gsc_row=gsc_row,
                site_similarity=site_similarity,
            )

            payload = {
                "query_text": _safe_query_text(query),
                "source": "community",
                "intent": "commercial",
                "funnel_stage": "MOFU",
                "trend_score": 18,
                "trend_reason": "Brand mentioned but not cited",
                "refresh_needed": refresh_flag,
                "refresh_reason": opp_reason if refresh_flag else "",
                "ai_snippet_reco": {"schema": ["Organization", "FAQPage"], "snippet_blocks": ["Definition block", "Citation references"]},
                "brief": generate_brief(query, "commercial", "MOFU", [], row.get("cited_urls", [])),
                "priority_score": priority,
                "priority_explanation": explanation,
                "recommended_actions": [
                    "Add source-backed claims with citations",
                    "Publish comparison page against cited competitors",
                ],
                "links": row.get("cited_urls", []),
                "status": "backlog",
                "metadata_json": {
                    "date": row.get("date"),
                    "competitor_cited": row.get("competitor_cited", []),
                    "opportunity_type": opp_type,
                    "classification_reason": opp_reason,
                    "classifier_version": "v2",
                    "classifier_inputs": {
                        "gsc_match_query": gsc_match_query,
                        "gsc_match_similarity": round(gsc_match_similarity, 3),
                        "competitor_gap": competitor_gap,
                    },
                    "score_components": score_components,
                    "score_ratings": score_ratings,
                    "score_source": score_source,
                    "score_rationale": score_rationale,
                    "strategist_confidence": confidence,
                },
            }
            _persist(payload, opp_type, confidence, competitor_gap, gsc_row)

        # Competitor velocity opportunities
        for week in competitor_weeks:
            query = _safe_query_text(f"competitor velocity {week['week']}")
            competitor_gap = min(1.0, float(week.get("posts", 0)) / 10)
            gsc_row = gsc_map.get(query)

            opp_type, refresh_flag, opp_reason = classify_opportunity_type_engine(
                query_text=query,
                source="competitor_velocity",
                competitor_gap=competitor_gap,
                gsc_row=gsc_row,
                site_links=site_links,
            )
            score_components, priority, explanation, score_ratings, score_source, score_rationale = score_with_strategist(
                db,
                query_text=query,
                source="competitor_velocity",
                intent="informational",
                funnel_stage="TOFU",
                trend_score=min(40.0, float(week.get("posts", 0)) * 2),
                competitor_gap=competitor_gap,
                ai_citation_gap=0.25,
                refresh_needed=refresh_flag,
                gsc_row=gsc_row,
                link_count=0,
                opportunity_type=opp_type,
            )
            site_similarity = _max_page_similarity(query, site_links)
            confidence = decision_confidence(
                opportunity_type=opp_type,
                competitor_gap=competitor_gap,
                gsc_row=gsc_row,
                site_similarity=site_similarity,
            )

            payload = {
                "query_text": query,
                "source": "competitor_velocity",
                "intent": "informational",
                "funnel_stage": "TOFU",
                "trend_score": min(40.0, float(week.get("posts", 0)) * 2),
                "trend_reason": "Weekly competitor publishing volume",
                "refresh_needed": refresh_flag,
                "refresh_reason": opp_reason if refresh_flag else "",
                "ai_snippet_reco": {"schema": ["Article"], "snippet_blocks": ["Trend summary"]},
                "brief": "Track competitor velocity deltas and publish response content weekly.",
                "priority_score": priority,
                "priority_explanation": explanation,
                "recommended_actions": ["Publish one response post for high-velocity weeks"],
                "links": [],
                "status": "backlog",
                "metadata_json": {
                    "week": week.get("week"),
                    "posts": week.get("posts"),
                    "opportunity_type": opp_type,
                    "classification_reason": opp_reason,
                    "classifier_version": "v2",
                    "score_components": score_components,
                    "score_ratings": score_ratings,
                    "score_source": score_source,
                    "score_rationale": score_rationale,
                    "strategist_confidence": confidence,
                },
            }
            _persist(payload, opp_type, confidence, competitor_gap, gsc_row)

        run.status = "success"
        # Post-run normalization: existing owned pages should never remain classified as net-new.
        all_rows = db.query(QueryOpportunity).filter(QueryOpportunity.source == "gsc").all()
        corrected = 0
        for opp in all_rows:
            base_meta = opp.metadata_json if isinstance(opp.metadata_json, dict) else {}
            meta = dict(base_meta)
            opp_type = str(meta.get("opportunity_type") or "").strip().lower()
            has_owned_link = isinstance(opp.links, list) and len(opp.links) > 0
            if opp_type == "new" and has_owned_link:
                prev_reason = str(meta.get("classification_reason") or "")
                meta["opportunity_type"] = "refresh"
                meta["classification_reason"] = (
                    "Existing rank/impression signal detected (post-run normalization: owned page link present)"
                    + (f" | prev={prev_reason}" if prev_reason else "")
                )
                opp.refresh_needed = True
                opp.refresh_reason = "Existing owned page link present for query/topic"
                opp.metadata_json = meta
                corrected += 1

        if corrected:
            run.details = {
                "opportunities_processed": inserted,
                "created_by_type": dict(created_by_type),
                "skipped_by_reason": dict(skipped_by_reason),
                "post_run_corrected_to_refresh": corrected,
            }
        else:
            run.details = {
                "opportunities_processed": inserted,
                "created_by_type": dict(created_by_type),
                "skipped_by_reason": dict(skipped_by_reason),
            }

    except Exception as exc:  # pragma: no cover
        run.status = "failed"
        run.error = str(exc)
        raise
    finally:
        run.finished_at = datetime.now(timezone.utc)
        db.commit()

    return run.details
