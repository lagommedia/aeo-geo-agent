from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.opportunity import QueryOpportunity
from app.models.run_history import RunHistory
from app.services.adapters.ahrefs_adapter import AhrefsAdapter
from app.services.adapters.citations_adapter import CitationMonitorAdapter
from app.services.adapters.competitor_velocity import CompetitorVelocityAdapter
from app.services.adapters.gsc_adapter import GSCAdapter
from app.services.adapters.semrush_adapter import SEMrushAdapter
from app.services.briefs import generate_brief, infer_funnel, recommend_snippets
from app.services.detectors import detect_refresh_need, detect_rising_query
from app.services.scoring import score_priority


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


def run_ingestion(db: Session) -> dict:
    run = RunHistory(run_type="nightly_ingestion", status="running", details={})
    db.add(run)
    db.commit()

    inserted = 0
    try:
        gsc_records = GSCAdapter().normalize(GSCAdapter().fetch())
        citations = CitationMonitorAdapter().normalize(CitationMonitorAdapter().fetch())
        semrush = SEMrushAdapter().normalize(SEMrushAdapter().fetch())
        ahrefs = AhrefsAdapter().normalize(AhrefsAdapter().fetch())
        competitor_weeks = CompetitorVelocityAdapter().normalize(CompetitorVelocityAdapter().fetch())

        competitor_map = {}
        for row in semrush + ahrefs:
            competitor_map[row["query_text"]] = max(competitor_map.get(row["query_text"], 0), row.get("competitor_gap", 0))

        citation_map = {}
        for row in citations:
            gap = 1.0 if row.get("brand_mentioned") and not row.get("brand_cited") else 0.0
            citation_map[row["query_text"]] = max(citation_map.get(row["query_text"], 0), gap)

        for row in gsc_records:
            trend, trend_reason = detect_rising_query(row["timeseries"])
            refresh_needed, refresh_reason = detect_refresh_need(row["timeseries"])
            intent = "commercial" if any(x in row["query_text"] for x in ["software", "platform", "outsourced", "automation"]) else "informational"
            funnel = infer_funnel(row["query_text"], intent)
            ai_gap = citation_map.get(row["query_text"], 0.0)
            competitor_gap = competitor_map.get(row["query_text"], 0.0)
            priority, explanation = score_priority(trend, intent, funnel, refresh_needed, ai_gap, competitor_gap)
            snippets = recommend_snippets(intent, row["query_text"])
            brief = generate_brief(row["query_text"], intent, funnel, [], row["links"])
            actions = [
                "Refresh title/H1 for query-match",
                "Add AI answer block + FAQ",
                "Strengthen internal links to demo and ROI pages",
            ]
            if refresh_needed:
                actions.append("Update decaying page with fresh examples and stats")
            if ai_gap > 0:
                actions.append("Create citation-friendly definitions and outreach targets")

            payload = {
                "query_text": row["query_text"],
                "source": row["source"],
                "intent": intent,
                "funnel_stage": funnel,
                "trend_score": trend,
                "trend_reason": trend_reason,
                "refresh_needed": refresh_needed,
                "refresh_reason": refresh_reason,
                "ai_snippet_reco": snippets,
                "brief": brief,
                "priority_score": priority,
                "priority_explanation": explanation,
                "recommended_actions": actions,
                "links": row["links"],
                "status": "new",
                "metadata_json": {"timeseries": row["timeseries"]},
            }
            _upsert_opportunity(db, payload)
            inserted += 1

        for row in citations:
            if row.get("brand_mentioned") and not row.get("brand_cited"):
                priority, explanation = score_priority(18, "commercial", "MOFU", False, 1.0, 0.3)
                payload = {
                    "query_text": row["query_text"],
                    "source": "ai_citations",
                    "intent": "commercial",
                    "funnel_stage": "MOFU",
                    "trend_score": 18,
                    "trend_reason": "Brand mentioned but not cited",
                    "refresh_needed": False,
                    "refresh_reason": "",
                    "ai_snippet_reco": {"schema": ["Organization", "FAQPage"], "snippet_blocks": ["Definition block", "Citation references"]},
                    "brief": generate_brief(row["query_text"], "commercial", "MOFU", [], row.get("cited_urls", [])),
                    "priority_score": priority,
                    "priority_explanation": explanation,
                    "recommended_actions": [
                        "Add source-backed claims with citations",
                        "Publish comparison page against cited competitors",
                    ],
                    "links": row.get("cited_urls", []),
                    "status": "new",
                    "metadata_json": {"date": row.get("date"), "competitor_cited": row.get("competitor_cited", [])},
                }
                _upsert_opportunity(db, payload)
                inserted += 1

        for week in competitor_weeks:
            payload = {
                "query_text": f"competitor velocity {week['week']}",
                "source": "competitor_velocity",
                "intent": "informational",
                "funnel_stage": "TOFU",
                "trend_score": min(40, week["posts"] * 2),
                "trend_reason": "Weekly competitor publishing volume",
                "refresh_needed": False,
                "refresh_reason": "",
                "ai_snippet_reco": {"schema": ["Article"], "snippet_blocks": ["Trend summary"]},
                "brief": "Track competitor velocity deltas and publish response content weekly.",
                "priority_score": min(60, week["posts"] * 3),
                "priority_explanation": f"competitor posts={week['posts']}",
                "recommended_actions": ["Publish one response post for high-velocity weeks"],
                "links": [],
                "status": "new",
                "metadata_json": {"week": week["week"], "posts": week["posts"]},
            }
            _upsert_opportunity(db, payload)
            inserted += 1

        run.status = "success"
        run.details = {"opportunities_processed": inserted}
    except Exception as exc:  # pragma: no cover
        run.status = "failed"
        run.error = str(exc)
        raise
    finally:
        run.finished_at = datetime.now(timezone.utc)
        db.commit()

    return run.details
