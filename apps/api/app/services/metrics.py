import csv
from collections import defaultdict
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.opportunity import QueryOpportunity


def _is_non_branded(query: str) -> bool:
    terms = [x.strip().lower() for x in settings.brand_terms.split(",") if x.strip()]
    q = query.lower()
    return not any(term in q for term in terms)


def compute_ai_citation_share(db: Session) -> list[dict]:
    rows = db.query(QueryOpportunity).filter(QueryOpportunity.source == "ai_citations").all()
    grouped = defaultdict(lambda: {"brand": 0, "total": 0})
    for row in rows:
        date = row.metadata_json.get("date", "unknown")
        grouped[date]["total"] += 1
        if settings.our_domain in " ".join(row.links):
            grouped[date]["brand"] += 1

    result = []
    for date, vals in sorted(grouped.items()):
        share = (vals["brand"] / vals["total"]) if vals["total"] else 0
        result.append({"label": date, "value": round(share, 3)})
    return result


def compute_non_branded_pipeline(db: Session, conversions_csv: str = "sample_data/conversions.csv") -> list[dict]:
    rows = db.query(QueryOpportunity).all()
    grouped = defaultdict(float)
    for row in rows:
        if _is_non_branded(row.query_text):
            grouped[row.source] += row.trend_score

    if Path(conversions_csv).exists():
        with open(conversions_csv, newline="", encoding="utf-8") as f:
            for rec in csv.DictReader(f):
                grouped[rec["page"]] += float(rec.get("conversions", 0) or 0)

    return [{"label": k, "value": round(v, 2)} for k, v in sorted(grouped.items())]


def compute_competitor_velocity(db: Session) -> list[dict]:
    rows = db.query(QueryOpportunity).filter(QueryOpportunity.source == "competitor_velocity").all()
    grouped = defaultdict(float)
    for row in rows:
        grouped[row.metadata_json.get("week", "unknown")] += row.metadata_json.get("posts", 0)
    return [{"label": k, "value": v} for k, v in sorted(grouped.items())]
