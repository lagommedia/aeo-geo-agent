from datetime import datetime, timezone
import json
import re

import httpx

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.secrets import decrypt_secret
from app.models.opportunity import QueryOpportunity
from app.models.source_config import SourceConfig
from app.schemas.opportunity import OpportunityOut, OpportunityStatusUpdate
from app.services.aeo_geo_agents import resolve_agent_instructions, resolve_anthropic_credentials, resolve_anthropic_instructions, resolve_openai_credentials
from app.services.briefs import generate_strategist_brief
from app.services.content_creator import generate_article_from_brief
from app.services.manual_opportunity import evaluate_manual_opportunity
from app.services.new_opportunity_discovery import discover_new_opportunities, discover_refresh_opportunities

router = APIRouter(prefix="/opportunities", tags=["opportunities"])


class ContentGeneratePayload(BaseModel):
    force_regenerate: bool = False


class GeneratedContentOut(BaseModel):
    opportunity_id: int
    keyword: str
    content_markdown: str
    provider: str
    model: str | None = None
    generated_at: str | None = None




class ManualOpportunityIn(BaseModel):
    query_text: str
    website_url: str = "https://zeni.ai"


class StrategistRunOut(BaseModel):
    status: str
    result: dict


class BoardPullOut(BaseModel):
    status: str
    board: str
    pulled_count: int
    opportunities: list[OpportunityOut]


class NewDiscoverIn(BaseModel):
    website_url: str = "https://zeni.ai"
    limit: int = 15
    seed_prompt: str | None = None


class NewDiscoverOut(BaseModel):
    status: str
    created_count: int
    skipped_count: int
    opportunities: list[OpportunityOut]



def _board_key_for_opportunity(opp: QueryOpportunity) -> str:
    source = (opp.source or "").strip().lower()
    if source == "community":
        return "community"
    if source == "refresh_scan":
        return "refresh"

    meta = opp.metadata_json if isinstance(opp.metadata_json, dict) else {}
    typed = str(meta.get("opportunity_type") or "").strip().lower()
    if typed == "community":
        return "community"
    if typed == "refresh":
        return "refresh"
    return "new"


def _normalize_board(board: str) -> str:
    b = (board or "").strip().lower()
    if b not in {"new", "refresh", "community"}:
        raise HTTPException(status_code=400, detail="board must be one of new, refresh, community")
    return b


GEMINI_SCORE_WEIGHTS = {
    "ai_query_volume": 20.0,
    "answer_likelihood": 15.0,
    "commercial_intent": 20.0,
    "ai_citation_gap": 15.0,
    "authority_leverage": 15.0,
    "content_coverage_gap": 15.0,
}


def _extract_first_json(text: str) -> dict | None:
    if not text:
        return None
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except Exception:
        return None


def _gemini_ratings_to_points(ratings: dict[str, float]) -> tuple[dict[str, float], float, str]:
    components: dict[str, float] = {}
    for key, weight in GEMINI_SCORE_WEIGHTS.items():
        rating = float(ratings.get(key, 0.0) or 0.0)
        rating = max(0.0, min(10.0, rating))
        components[key] = round((rating / 10.0) * weight, 2)
    total = round(sum(components.values()), 2)
    explanation = ", ".join([f"{k}={components[k]}/{int(GEMINI_SCORE_WEIGHTS[k])}" for k in GEMINI_SCORE_WEIGHTS])
    return components, total, explanation


def _resolve_gemini_rating_config(db: Session) -> tuple[str | None, str, str]:
    row = db.query(SourceConfig).filter(SourceConfig.source_name == "gemini").one_or_none()
    config = (row.config or {}) if row else {}
    config = config if isinstance(config, dict) else {}
    api_key = decrypt_secret(config.get("api_key")) if config.get("api_key") else None
    model = str(config.get("model") or "gemini-1.5-pro")
    instructions = config.get("instructions") if isinstance(config.get("instructions"), dict) else {}
    rating_instructions = str(instructions.get("rating") or "").strip()
    return api_key, model, rating_instructions


def _score_new_opportunity_with_gemini(db: Session, opp: QueryOpportunity) -> None:
    metadata = dict(opp.metadata_json or {}) if isinstance(opp.metadata_json, dict) else {}

    # Refresh the strategist brief before Gemini evaluates which candidates should surface.
    brief = generate_strategist_brief(db, opp)
    opp.brief = brief
    metadata["strategist_brief_version"] = "v1"
    metadata["brief_upgraded_at"] = datetime.now(timezone.utc).isoformat()

    api_key, model, rating_instructions = _resolve_gemini_rating_config(db)
    if not api_key:
        opp.metadata_json = metadata
        return

    prompt = (rating_instructions or "You are scoring new AEO/GEO opportunities for prioritization. Return JSON only.").strip()
    payload = {
        "query_text": opp.query_text,
        "source": opp.source,
        "intent": opp.intent,
        "funnel_stage": opp.funnel_stage,
        "existing_priority_score": opp.priority_score,
        "links": opp.links or [],
        "brief": brief,
        "criteria_weights": GEMINI_SCORE_WEIGHTS,
        "required_output": {
            "ratings": list(GEMINI_SCORE_WEIGHTS.keys()),
            "rationale": "short string"
        }
    }

    request_text = (
        f"{prompt}\n\n"
        "Return JSON only with keys: ratings, rationale. "
        "ratings must contain numeric 0-10 values for ai_query_volume, answer_likelihood, commercial_intent, ai_citation_gap, authority_leverage, content_coverage_gap.\n\n"
        f"Context JSON:\n{json.dumps(payload, ensure_ascii=True, indent=2)}"
    )

    try:
        response = httpx.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}",
            headers={"Content-Type": "application/json"},
            json={
                "contents": [{"parts": [{"text": request_text}]}],
                "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"},
            },
            timeout=90.0,
        )
        response.raise_for_status()
        data = response.json()
        text_parts: list[str] = []
        for candidate in data.get("candidates", []):
            content = candidate.get("content") or {}
            for part in content.get("parts", []):
                if isinstance(part, dict) and part.get("text"):
                    text_parts.append(str(part.get("text")))
        payload_json = _extract_first_json("\n".join(text_parts))
        ratings_raw = payload_json.get("ratings") if isinstance(payload_json, dict) else None
        if not isinstance(ratings_raw, dict):
            raise RuntimeError("Gemini did not return ratings JSON")

        ratings = {}
        for key in GEMINI_SCORE_WEIGHTS:
            ratings[key] = round(max(0.0, min(10.0, float(ratings_raw.get(key, 0.0) or 0.0))), 2)
        components, total, explanation = _gemini_ratings_to_points(ratings)

        opp.priority_score = total
        opp.priority_explanation = explanation
        metadata["score_components"] = components
        metadata["score_ratings"] = ratings
        metadata["score_source"] = "gemini_rating"
        metadata["score_rationale"] = str(payload_json.get("rationale") or "").strip()
        metadata["gemini_rated_at"] = datetime.now(timezone.utc).isoformat()
    except Exception as exc:
        metadata["score_source"] = metadata.get("score_source") or "existing_priority"
        metadata["gemini_rating_error"] = str(exc)[:500]

    opp.metadata_json = metadata


def _get_generated_content(opp: QueryOpportunity) -> GeneratedContentOut | None:
    metadata = opp.metadata_json or {}
    generated = metadata.get("generated_content") if isinstance(metadata, dict) else None
    if not isinstance(generated, dict):
        return None
    if not generated.get("content_markdown"):
        return None

    return GeneratedContentOut(
        opportunity_id=opp.id,
        keyword=generated.get("keyword") or opp.query_text,
        content_markdown=generated.get("content_markdown") or "",
        provider=generated.get("provider") or "unknown",
        model=generated.get("model"),
        generated_at=generated.get("generated_at"),
    )


@router.get("", response_model=list[OpportunityOut])
def list_opportunities(
    source: str | None = Query(default=None),
    funnel_stage: str | None = Query(default=None),
    intent: str | None = Query(default=None),
    status: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    q = db.query(QueryOpportunity)
    if source:
        q = q.filter(QueryOpportunity.source == source)
    if funnel_stage:
        q = q.filter(QueryOpportunity.funnel_stage == funnel_stage)
    if intent:
        q = q.filter(QueryOpportunity.intent == intent)
    if status:
        q = q.filter(QueryOpportunity.status == status)
    return q.order_by(desc(QueryOpportunity.priority_score)).all()






@router.post("/boards/{board}/pull", response_model=BoardPullOut)
def pull_board_opportunities(
    board: str,
    limit: int = Query(default=3, ge=1, le=25),
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    board_key = _normalize_board(board)

    # Only pull from backlog/new candidates that are not already active on the board.
    rows = (
        db.query(QueryOpportunity)
        .filter(QueryOpportunity.status.in_(["backlog", "new"]))
        .order_by(desc(QueryOpportunity.priority_score))
        .all()
    )

    candidates: list[QueryOpportunity] = []
    candidate_limit = max(limit * 4, 12)
    for row in rows:
        if _board_key_for_opportunity(row) != board_key:
            continue
        candidates.append(row)
        if len(candidates) >= candidate_limit:
            break

    if board_key == "new":
        for row in candidates:
            _score_new_opportunity_with_gemini(db, row)
        db.commit()
        selected = sorted(candidates, key=lambda row: float(row.priority_score or 0.0), reverse=True)[:limit]
    else:
        selected = candidates[:limit]

    for row in selected:
        row.status = "incoming"

    db.commit()
    for row in selected:
        db.refresh(row)

    return BoardPullOut(
        status="ok",
        board=board_key,
        pulled_count=len(selected),
        opportunities=selected,
    )


@router.post("/strategist/run", response_model=StrategistRunOut)
def run_strategist_now(db: Session = Depends(get_db), _user=Depends(get_current_user)):
    raise HTTPException(
        status_code=410,
        detail="Strategist batch ingestion is disabled. Use manual evaluate + board pull flow.",
    )


@router.post("/new/discover", response_model=NewDiscoverOut)
def discover_new(payload: NewDiscoverIn, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    result = discover_new_opportunities(
        db,
        website_url=payload.website_url,
        limit=max(1, min(payload.limit, 30)),
        seed_prompt=payload.seed_prompt,
    )
    return NewDiscoverOut(status="ok", created_count=result["created_count"], skipped_count=result["skipped_count"], opportunities=result["opportunities"])




@router.post("/refresh/discover", response_model=NewDiscoverOut)
def discover_refresh(payload: NewDiscoverIn, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    result = discover_refresh_opportunities(
        db,
        website_url=payload.website_url,
        limit=payload.limit,
        seed_prompt=payload.seed_prompt,
    )
    return {"status": "ok", **result}

@router.post("/manual/evaluate", response_model=OpportunityOut)
def create_manual_opportunity(payload: ManualOpportunityIn, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    try:
        return evaluate_manual_opportunity(db, payload.query_text, payload.website_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{opportunity_id}", response_model=OpportunityOut)
def get_opportunity(opportunity_id: int, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    opp = db.query(QueryOpportunity).filter(QueryOpportunity.id == opportunity_id).one_or_none()
    if not opp:
        raise HTTPException(status_code=404, detail="Not found")
    return opp


@router.patch("/{opportunity_id}", response_model=OpportunityOut)
def update_status(opportunity_id: int, payload: OpportunityStatusUpdate, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    opp = db.query(QueryOpportunity).filter(QueryOpportunity.id == opportunity_id).one_or_none()
    if not opp:
        raise HTTPException(status_code=404, detail="Not found")

    next_status = (payload.status or "").strip().lower()
    opp.status = next_status

    if next_status == "accepted":
        metadata = dict(opp.metadata_json or {}) if isinstance(opp.metadata_json, dict) else {}
        if not metadata.get("strategist_brief_version"):
            opp.brief = generate_strategist_brief(db, opp)
            metadata["strategist_brief_version"] = "v1"
            metadata["brief_upgraded_at"] = datetime.now(timezone.utc).isoformat()
            opp.metadata_json = metadata

    db.commit()
    db.refresh(opp)
    return opp


@router.get("/{opportunity_id}/brief")
def export_brief(opportunity_id: int, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    opp = db.query(QueryOpportunity).filter(QueryOpportunity.id == opportunity_id).one_or_none()
    if not opp:
        raise HTTPException(status_code=404, detail="Not found")
    return {"id": opportunity_id, "brief": opp.brief}



def _set_content_status(opp: QueryOpportunity, status: str, error: str | None = None) -> None:
    metadata = dict(opp.metadata_json) if isinstance(opp.metadata_json, dict) else {}
    metadata["content_status"] = status
    if error:
        metadata["content_error"] = error
    else:
        metadata.pop("content_error", None)
    opp.metadata_json = metadata


def _generate_content_background(opportunity_id: int, force_regenerate: bool, bind) -> None:
    bg_db = Session(bind=bind)
    try:
        opp = bg_db.query(QueryOpportunity).filter(QueryOpportunity.id == opportunity_id).one_or_none()
        if not opp:
            return

        _set_content_status(opp, "generating")
        bg_db.commit()
        bg_db.refresh(opp)

        metadata = opp.metadata_json if isinstance(opp.metadata_json, dict) else {}
        opportunity_type = str(metadata.get("opportunity_type") or "").strip().lower()

        if opportunity_type == "new":
            api_key, model = resolve_anthropic_credentials(bg_db)
            content_creator_instructions = resolve_anthropic_instructions(bg_db, "new")
            result = generate_article_from_brief(
                opp.query_text,
                opp.brief,
                opp,
                provider="anthropic",
                api_key=api_key,
                model=model,
                agent_instructions=content_creator_instructions,
            )
        else:
            api_key, model = resolve_openai_credentials(bg_db)
            content_creator_instructions = resolve_agent_instructions(bg_db, "content_creator")
            result = generate_article_from_brief(
                opp.query_text,
                opp.brief,
                opp,
                provider="openai",
                api_key=api_key,
                model=model,
                agent_instructions=content_creator_instructions,
            )

        generated = {
            "opportunity_id": opp.id,
            "keyword": opp.query_text,
            "content_markdown": result.get("content_markdown") or "",
            "provider": result.get("provider") or "unknown",
            "model": result.get("model"),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

        metadata = dict(opp.metadata_json) if isinstance(opp.metadata_json, dict) else {}
        metadata["generated_content"] = generated
        metadata["content_status"] = "completed"
        metadata.pop("content_error", None)
        opp.metadata_json = metadata

        bg_db.commit()
    except Exception as exc:
        opp = bg_db.query(QueryOpportunity).filter(QueryOpportunity.id == opportunity_id).one_or_none()
        if opp:
            _set_content_status(opp, "failed", str(exc))
            bg_db.commit()
    finally:
        bg_db.close()


@router.get("/{opportunity_id}/content", response_model=GeneratedContentOut)
def get_generated_content(opportunity_id: int, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    opp = db.query(QueryOpportunity).filter(QueryOpportunity.id == opportunity_id).one_or_none()
    if not opp:
        raise HTTPException(status_code=404, detail="Not found")

    generated = _get_generated_content(opp)
    if not generated:
        raise HTTPException(status_code=404, detail="No generated content yet")
    return generated


@router.post("/{opportunity_id}/content/generate")
def generate_content(
    opportunity_id: int,
    payload: ContentGeneratePayload,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    opp = db.query(QueryOpportunity).filter(QueryOpportunity.id == opportunity_id).one_or_none()
    if not opp:
        raise HTTPException(status_code=404, detail="Not found")

    existing = _get_generated_content(opp)
    metadata = opp.metadata_json if isinstance(opp.metadata_json, dict) else {}
    current_status = str(metadata.get("content_status") or "").strip().lower()

    if existing and not payload.force_regenerate:
        return {"status": "completed", "opportunity_id": opp.id, "content_status": "completed"}

    if current_status in {"queued", "generating"} and not payload.force_regenerate:
        return {"status": "accepted", "opportunity_id": opp.id, "content_status": current_status}

    _set_content_status(opp, "queued")
    db.commit()

    background_tasks.add_task(_generate_content_background, opp.id, bool(payload.force_regenerate), db.get_bind())

    return {"status": "accepted", "opportunity_id": opp.id, "content_status": "queued"}
