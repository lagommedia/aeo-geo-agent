from datetime import datetime, timedelta, timezone
from pathlib import Path
from secrets import token_urlsafe
from urllib.parse import urlencode
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.secrets import decrypt_secret, encrypt_secret
from app.models.source_config import SourceConfig
from app.schemas.source import (
    OAuthCallbackIn,
    OAuthStartResponse,
    SourceConfigIn,
    SourceConfigOut,
    SourceCredentialIn,
    SourceTestResponse,
)

router = APIRouter(prefix="/sources", tags=["sources"])

SUPPORTED_SOURCES = {"gsc", "semrush", "ahrefs", "ai_citations", "openai", "anthropic", "gemini", "google_analytics", "company_profile"}




KB_ROOT = Path("data/openai_kb")
ALLOWED_KB_EXTENSIONS = {
    ".txt", ".md", ".markdown", ".pdf", ".docx", ".csv", ".json", ".html", ".htm"
}
MAX_KB_FILE_SIZE = 20 * 1024 * 1024


def _safe_filename(name: str) -> str:
    clean = "".join(ch for ch in (name or "file") if ch.isalnum() or ch in {"-", "_", "."})
    clean = clean.strip(".") or "file"
    return clean[:120]


def _openai_row(db: Session) -> SourceConfig:
    row = _get_or_create(db, "openai")
    return row


def _openai_files_public(config: dict) -> list[dict]:
    files = config.get("kb_files") if isinstance(config, dict) else None
    if not isinstance(files, list):
        return []
    out: list[dict] = []
    for item in files:
        if not isinstance(item, dict):
            continue
        out.append(
            {
                "id": str(item.get("id") or ""),
                "name": str(item.get("name") or ""),
                "size_bytes": int(item.get("size_bytes") or 0),
                "content_type": str(item.get("content_type") or ""),
                "uploaded_at": str(item.get("uploaded_at") or ""),
            }
        )
    return out


def _store_openai_kb_file(db: Session, file: UploadFile) -> SourceConfig:
    if not file.filename:
        raise HTTPException(status_code=400, detail="filename is required")

    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_KB_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext or 'unknown'}")

    payload = file.file.read()
    if not payload:
        raise HTTPException(status_code=400, detail="File is empty")
    if len(payload) > MAX_KB_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File exceeds 20MB limit")

    KB_ROOT.mkdir(parents=True, exist_ok=True)
    file_id = str(uuid4())
    safe_name = _safe_filename(file.filename)
    stored_name = f"{file_id}_{safe_name}"
    file_path = KB_ROOT / stored_name
    file_path.write_bytes(payload)

    row = _openai_row(db)
    config = dict(row.config or {})
    files = config.get("kb_files") if isinstance(config.get("kb_files"), list) else []
    files = [f for f in files if isinstance(f, dict)]
    files.append(
        {
            "id": file_id,
            "name": safe_name,
            "stored_name": stored_name,
            "path": str(file_path),
            "size_bytes": len(payload),
            "content_type": file.content_type or "application/octet-stream",
            "uploaded_at": _now().isoformat(),
        }
    )
    config["kb_files"] = files
    row.config = config
    if row.status == "disconnected":
        row.status = "connected"
    db.commit()
    db.refresh(row)
    return row


def _delete_openai_kb_file(db: Session, file_id: str) -> SourceConfig:
    row = _openai_row(db)
    config = dict(row.config or {})
    files = config.get("kb_files") if isinstance(config.get("kb_files"), list) else []

    remaining = []
    matched = None
    for item in files:
        if not isinstance(item, dict):
            continue
        if str(item.get("id") or "") == file_id:
            matched = item
            continue
        remaining.append(item)

    if not matched:
        raise HTTPException(status_code=404, detail="Knowledge base file not found")

    path_text = str(matched.get("path") or "")
    if path_text:
        try:
            Path(path_text).unlink(missing_ok=True)
        except Exception:
            pass

    config["kb_files"] = remaining
    row.config = config
    db.commit()
    db.refresh(row)
    return row


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _get_or_create(db: Session, source_name: str) -> SourceConfig:
    row = db.query(SourceConfig).filter(SourceConfig.source_name == source_name).one_or_none()
    if row:
        return row
    row = SourceConfig(source_name=source_name, config={}, status="disconnected")
    db.add(row)
    db.flush()
    return row


def _ensure_supported(source_name: str) -> None:
    if source_name not in SUPPORTED_SOURCES:
        raise HTTPException(status_code=400, detail=f"Unsupported source: {source_name}")


def _gsc_has_oauth(config: dict) -> bool:
    oauth = config.get("oauth", {})
    return bool(oauth.get("access_token") or oauth.get("refresh_token"))


def _merge_config(source_name: str, existing: dict, incoming: dict) -> dict:
    merged = dict(existing or {})
    merged.update(incoming or {})

    # Keep sensitive fields that are never sent by UI.
    if source_name == "gsc":
        for key in ["oauth", "oauth_pending", "connected_at", "auth_type"]:
            if key in (existing or {}) and key not in (incoming or {}):
                merged[key] = existing[key]
    if source_name in {"semrush", "ahrefs", "ai_citations", "openai", "anthropic", "gemini", "google_analytics"}:
        if "api_key" in (existing or {}) and "api_key" not in (incoming or {}):
            merged["api_key"] = existing["api_key"]

    return merged


def _public_config(source_name: str, config: dict) -> dict:
    auth_type = config.get("auth_type")
    public = {"auth_type": auth_type}

    if source_name == "gsc":
        public.update(
            {
                "site_url": config.get("site_url"),
                "connected_at": config.get("connected_at"),
                "oauth_connected": _gsc_has_oauth(config),
                "pending_oauth": bool(config.get("oauth_pending")),
            }
        )
    elif source_name in {"semrush", "ahrefs"}:
        public.update({"api_key_configured": bool(config.get("api_key"))})
    elif source_name == "ai_citations":
        public.update(
            {
                "provider": config.get("provider", "mock"),
                "tracked_prompts_count": len(config.get("tracked_prompts", [])),
                "competitors_count": len(config.get("competitors", [])),
                "brand_terms_count": len(config.get("brand_terms", [])),
                "api_key_configured": bool(config.get("api_key")),
            }
        )
    elif source_name == "openai":
        raw_prompts = config.get("agent_prompts")
        agent_prompts = raw_prompts if isinstance(raw_prompts, dict) else {}
        public.update(
            {
                "api_key_configured": bool(config.get("api_key")),
                "model": config.get("model", "gpt-4.1-mini"),
                "agents": ["strategist", "content_creator", "refresh", "community"],
                "agent_prompts": {
                    "strategist": str(agent_prompts.get("strategist") or ""),
                    "content_creator": str(agent_prompts.get("content_creator") or ""),
                    "refresh": str(agent_prompts.get("refresh") or ""),
                    "community": str(agent_prompts.get("community") or ""),
                },
                "knowledge_base_files": _openai_files_public(config),
            }
        )
    elif source_name in {"anthropic", "gemini"}:
        public.update(
            {
                "api_key_configured": bool(config.get("api_key")),
                "model": config.get("model", ""),
                "instructions": config.get("instructions") if isinstance(config.get("instructions"), dict) else str(config.get("instructions") or ""),
            }
        )
    elif source_name == "google_analytics":
        public.update(
            {
                "api_key_configured": bool(config.get("api_key")),
                "property_id": str(config.get("property_id") or ""),
            }
        )
    elif source_name == "company_profile":
        public.update(
            {
                "company_name": str(config.get("company_name") or ""),
                "company_website": str(config.get("company_website") or ""),
                "company_context": str(config.get("company_context") or ""),
            }
        )

    return public


def _to_source_out(row: SourceConfig) -> SourceConfigOut:
    return SourceConfigOut(
        id=row.id,
        source_name=row.source_name,
        config=_public_config(row.source_name, row.config or {}),
        status=row.status,
        notes=row.notes,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _get_gsc_tokens(config: dict) -> tuple[str | None, str | None, str | None]:
    oauth = config.get("oauth", {})
    access_token = decrypt_secret(oauth.get("access_token")) if oauth.get("access_token") else None
    refresh_token = decrypt_secret(oauth.get("refresh_token")) if oauth.get("refresh_token") else None
    expires_at = oauth.get("expires_at")
    return access_token, refresh_token, expires_at


def _refresh_gsc_token(config: dict) -> dict:
    _, refresh_token, _ = _get_gsc_tokens(config)
    if not refresh_token:
        return config

    if not settings.google_oauth_client_id or not settings.google_oauth_client_secret:
        return config

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
        return config

    payload = response.json()
    expires_in = int(payload.get("expires_in", 3600))
    config.setdefault("oauth", {})["access_token"] = encrypt_secret(payload["access_token"])
    config["oauth"]["expires_at"] = (_now() + timedelta(seconds=expires_in)).isoformat()
    return config


@router.get("", response_model=list[SourceConfigOut])
def list_sources(db: Session = Depends(get_db), _user=Depends(get_current_user)):
    rows = db.query(SourceConfig).all()
    return [_to_source_out(row) for row in rows]


@router.post("", response_model=SourceConfigOut)
def upsert_source(payload: SourceConfigIn, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    _ensure_supported(payload.source_name)
    row = _get_or_create(db, payload.source_name)

    merged_config = _merge_config(payload.source_name, row.config or {}, payload.config)
    row.config = merged_config

    if payload.source_name == "gsc":
        if _gsc_has_oauth(merged_config):
            row.status = "connected"
        elif merged_config.get("oauth_pending"):
            row.status = "pending"
        else:
            row.status = "disconnected"
    else:
        row.status = payload.status

    row.notes = payload.notes
    db.commit()
    db.refresh(row)
    return _to_source_out(row)


@router.post("/credentials", response_model=SourceConfigOut)
def save_credentials(payload: SourceCredentialIn, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    _ensure_supported(payload.source_name)
    row = _get_or_create(db, payload.source_name)

    config = dict(row.config or {})
    if payload.source_name in {"semrush", "ahrefs"}:
        api_key = str(payload.credentials.get("api_key") or "").strip()
        if api_key:
            config["api_key"] = encrypt_secret(api_key)
        elif not config.get("api_key"):
            raise HTTPException(status_code=400, detail="api_key is required")
        config["auth_type"] = "api_key"
        row.status = "connected"
    elif payload.source_name == "ai_citations":
        config["provider"] = payload.credentials.get("provider", "mock")
        config["tracked_prompts"] = payload.credentials.get("tracked_prompts", [])
        config["competitors"] = payload.credentials.get("competitors", [])
        config["brand_terms"] = payload.credentials.get("brand_terms", [])
        api_key = payload.credentials.get("api_key")
        if api_key:
            config["api_key"] = encrypt_secret(api_key)
        config["auth_type"] = "api_key_or_mock"
        row.status = "connected"
    elif payload.source_name == "openai":
        api_key = payload.credentials.get("api_key")
        if api_key:
            api_key = str(api_key).strip()
            if not api_key.startswith("sk-") or len(api_key) < 24:
                raise HTTPException(status_code=400, detail="Invalid OpenAI API key format")
            config["api_key"] = encrypt_secret(api_key)
        elif not config.get("api_key") and not settings.openai_api_key:
            raise HTTPException(status_code=400, detail="api_key is required")
        config["model"] = payload.credentials.get("model", config.get("model", settings.openai_model))
        supported_agents = {"strategist", "content_creator", "refresh", "community"}

        full_prompts = payload.credentials.get("agent_prompts")
        if isinstance(full_prompts, dict):
            normalized: dict[str, str] = {}
            for key, val in full_prompts.items():
                agent_key = str(key or "").strip().lower()
                if agent_key not in supported_agents:
                    continue
                cleaned = str(val or "").strip()
                if cleaned:
                    normalized[agent_key] = cleaned
            config["agent_prompts"] = normalized
        else:
            agent_name = payload.credentials.get("agent_name")
            agent_prompt = payload.credentials.get("agent_prompt")
            if agent_name is not None or agent_prompt is not None:
                agent_key = str(agent_name or "").strip().lower()
                if agent_key not in supported_agents:
                    raise HTTPException(status_code=400, detail="agent_name must be one of strategist, content_creator, refresh, community")

                prompts = config.get("agent_prompts") if isinstance(config.get("agent_prompts"), dict) else {}
                cleaned = str(agent_prompt or "").strip()
                if cleaned:
                    prompts[agent_key] = cleaned
                else:
                    prompts.pop(agent_key, None)
                config["agent_prompts"] = prompts
        config["auth_type"] = "api_key"
        row.status = "connected"
    elif payload.source_name in {"anthropic", "gemini"}:
        api_key = str(payload.credentials.get("api_key") or "").strip()
        model = str(payload.credentials.get("model") or "").strip()
        raw_instructions = payload.credentials.get("instructions")
        if isinstance(raw_instructions, dict):
            instructions = {str(k): str(v or "").strip() for k, v in raw_instructions.items()}
        else:
            instructions = str(raw_instructions or "").strip()
        if api_key:
            config["api_key"] = encrypt_secret(api_key)
        elif not config.get("api_key"):
            raise HTTPException(status_code=400, detail="api_key is required")
        config["model"] = model
        config["instructions"] = instructions
        config["auth_type"] = "api_key"
        row.status = "connected"
    elif payload.source_name == "google_analytics":
        api_key = str(payload.credentials.get("api_key") or "").strip()
        property_id = str(payload.credentials.get("property_id") or "").strip()
        if api_key:
            config["api_key"] = encrypt_secret(api_key)
        elif not config.get("api_key"):
            raise HTTPException(status_code=400, detail="api_key is required")
        config["property_id"] = property_id
        config["auth_type"] = "api_key"
        row.status = "connected" if property_id else "disconnected"
    elif payload.source_name == "company_profile":
        config["company_name"] = str(payload.credentials.get("company_name") or "").strip()
        config["company_website"] = str(payload.credentials.get("company_website") or "").strip()
        config["company_context"] = str(payload.credentials.get("company_context") or "").strip()
        config["auth_type"] = "profile"
        row.status = "connected" if config.get("company_name") and config.get("company_website") else "disconnected"
    else:
        raise HTTPException(status_code=400, detail="Use OAuth flow for gsc")

    row.config = config
    row.notes = payload.notes
    db.commit()
    db.refresh(row)
    return _to_source_out(row)




@router.get("/openai/kb/files")
def list_openai_kb_files(db: Session = Depends(get_db), _user=Depends(get_current_user)):
    row = _openai_row(db)
    config = dict(row.config or {})
    return {"files": _openai_files_public(config)}


@router.post("/openai/kb/upload", response_model=SourceConfigOut)
def upload_openai_kb_file(file: UploadFile = File(...), db: Session = Depends(get_db), _user=Depends(get_current_user)):
    row = _store_openai_kb_file(db, file)
    return _to_source_out(row)


@router.delete("/openai/kb/files/{file_id}", response_model=SourceConfigOut)
def delete_openai_kb_file(file_id: str, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    row = _delete_openai_kb_file(db, file_id)
    return _to_source_out(row)


@router.post("/gsc/oauth/start", response_model=OAuthStartResponse)
def start_gsc_oauth(db: Session = Depends(get_db), _user=Depends(get_current_user)):
    if not settings.google_oauth_client_id or not settings.google_oauth_client_secret:
        raise HTTPException(status_code=400, detail="Set GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET in .env")

    state = token_urlsafe(24)
    pending = {"state": state, "expires_at": (_now() + timedelta(minutes=15)).isoformat()}

    row = _get_or_create(db, "gsc")
    config = dict(row.config or {})
    config["oauth_pending"] = pending
    config["auth_type"] = "oauth2"
    row.config = config
    row.status = "pending"
    row.notes = "Waiting for Google OAuth callback"
    db.commit()

    query = urlencode(
        {
            "client_id": settings.google_oauth_client_id,
            "redirect_uri": settings.google_oauth_redirect_uri,
            "response_type": "code",
            "scope": settings.google_oauth_scopes,
            "access_type": "offline",
            "include_granted_scopes": "true",
            "prompt": "consent",
            "state": state,
        }
    )
    auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{query}"
    return OAuthStartResponse(source_name="gsc", auth_url=auth_url, state=state)


@router.post("/gsc/oauth/callback", response_model=SourceConfigOut)
def complete_gsc_oauth(payload: OAuthCallbackIn, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    row = _get_or_create(db, "gsc")
    config = dict(row.config or {})

    pending = config.get("oauth_pending") or {}
    pending_state = pending.get("state")
    pending_expires = pending.get("expires_at")

    if not pending_state or not pending_expires:
        raise HTTPException(status_code=400, detail="Missing pending OAuth state; start OAuth again")

    try:
        expires_dt = datetime.fromisoformat(pending_expires)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid pending OAuth state metadata")

    if _now() > expires_dt:
        config.pop("oauth_pending", None)
        row.config = config
        row.status = "disconnected"
        db.commit()
        raise HTTPException(status_code=400, detail="OAuth state expired")

    if payload.state != pending_state:
        raise HTTPException(status_code=400, detail="Invalid OAuth state")

    if not settings.google_oauth_client_id or not settings.google_oauth_client_secret:
        raise HTTPException(status_code=400, detail="Google OAuth env vars missing")

    token_response = httpx.post(
        "https://oauth2.googleapis.com/token",
        data={
            "code": payload.code,
            "client_id": settings.google_oauth_client_id,
            "client_secret": settings.google_oauth_client_secret,
            "redirect_uri": settings.google_oauth_redirect_uri,
            "grant_type": "authorization_code",
        },
        timeout=20.0,
    )

    if token_response.status_code >= 300:
        raise HTTPException(status_code=400, detail=f"Token exchange failed: {token_response.text}")

    token_data = token_response.json()
    expires_in = int(token_data.get("expires_in", 3600))

    config["oauth"] = {
        "access_token": encrypt_secret(token_data["access_token"]),
        "refresh_token": encrypt_secret(token_data.get("refresh_token")) if token_data.get("refresh_token") else None,
        "token_type": token_data.get("token_type", "Bearer"),
        "expires_at": (_now() + timedelta(seconds=expires_in)).isoformat(),
        "scope": token_data.get("scope", settings.google_oauth_scopes),
    }
    config["connected_at"] = _now().isoformat()
    config["auth_type"] = "oauth2"
    config.pop("oauth_pending", None)

    row.config = config
    row.status = "connected"
    row.notes = "Connected via Google OAuth"
    db.commit()
    db.refresh(row)
    return _to_source_out(row)


@router.post("/{source_name}/test", response_model=SourceTestResponse)
def test_source(source_name: str, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    _ensure_supported(source_name)
    row = _get_or_create(db, source_name)
    config = dict(row.config or {})

    if source_name == "gsc":
        config = _refresh_gsc_token(config)
        access_token, _, expires_at = _get_gsc_tokens(config)
        if not access_token:
            row.status = "disconnected"
            db.commit()
            return SourceTestResponse(source_name="gsc", status="error", message="No OAuth token; connect Google account first")

        response = httpx.get(
            "https://www.googleapis.com/webmasters/v3/sites",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=20.0,
        )
        if response.status_code >= 300:
            row.status = "error"
            db.commit()
            body = response.text[:1200]
            message = "Google Search Console API call failed"
            if response.status_code == 403 and "accessNotConfigured" in body:
                message = "Search Console API is disabled in Google Cloud. Enable searchconsole.googleapis.com and retry."
            return SourceTestResponse(
                source_name="gsc",
                status="error",
                message=message,
                details={"status_code": response.status_code, "body": body},
            )

        sites = [s.get("siteUrl") for s in response.json().get("siteEntry", []) if s.get("siteUrl")]
        row.config = config
        row.status = "connected"
        db.commit()
        return SourceTestResponse(
            source_name="gsc",
            status="connected",
            message="Google Search Console connected",
            details={"sites": sites[:20], "expires_at": expires_at},
        )

    if source_name in {"semrush", "ahrefs"}:
        if not config.get("api_key"):
            row.status = "disconnected"
            db.commit()
            return SourceTestResponse(source_name=source_name, status="error", message="API key missing")
        row.status = "connected"
        db.commit()
        return SourceTestResponse(
            source_name=source_name,
            status="connected",
            message=f"{source_name.upper()} credentials saved (live ping TODO for provider-specific endpoint)",
        )

    if source_name == "ai_citations":
        row.status = "connected"
        db.commit()
        return SourceTestResponse(
            source_name="ai_citations",
            status="connected",
            message="AI citations source configured",
            details={
                "provider": config.get("provider", "mock"),
                "tracked_prompts": len(config.get("tracked_prompts", [])),
                "competitors": len(config.get("competitors", [])),
            },
        )

    if source_name == "openai":
        enc_key = config.get("api_key")
        if not enc_key:
            row.status = "disconnected"
            db.commit()
            return SourceTestResponse(source_name="openai", status="error", message="API key missing")

        api_key = decrypt_secret(enc_key)
        response = httpx.get(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=20.0,
        )
        if response.status_code >= 300:
            row.status = "error"
            db.commit()
            return SourceTestResponse(
                source_name="openai",
                status="error",
                message="OpenAI API key test failed",
                details={"status_code": response.status_code, "body": response.text[:1200]},
            )

        row.status = "connected"
        db.commit()
        return SourceTestResponse(
            source_name="openai",
            status="connected",
            message="OpenAI Brain connected",
            details={"model": config.get("model", settings.openai_model)},
        )

    if source_name in {"anthropic", "gemini"}:
        if not config.get("api_key"):
            row.status = "disconnected"
            db.commit()
            return SourceTestResponse(source_name=source_name, status="error", message="API key missing")
        row.status = "connected"
        db.commit()
        return SourceTestResponse(
            source_name=source_name,
            status="connected",
            message=f"{source_name.capitalize()} configuration saved",
            details={"model": config.get("model", "")},
        )

    if source_name == "google_analytics":
        if not config.get("api_key"):
            row.status = "disconnected"
            db.commit()
            return SourceTestResponse(source_name="google_analytics", status="error", message="API key missing")
        if not str(config.get("property_id") or "").strip():
            row.status = "disconnected"
            db.commit()
            return SourceTestResponse(source_name="google_analytics", status="error", message="property_id is required")
        row.status = "connected"
        db.commit()
        return SourceTestResponse(
            source_name="google_analytics",
            status="connected",
            message="Google Analytics configuration saved",
            details={"property_id": str(config.get("property_id") or "")},
        )

    if source_name == "company_profile":
        ok = bool(config.get("company_name") and config.get("company_website"))
        row.status = "connected" if ok else "disconnected"
        db.commit()
        return SourceTestResponse(
            source_name="company_profile",
            status="connected" if ok else "error",
            message="Company profile saved" if ok else "company_name and company_website are required",
            details={
                "company_name": config.get("company_name", ""),
                "company_website": config.get("company_website", ""),
            },
        )

    raise HTTPException(status_code=400, detail="Unsupported source")
