from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from authlib.integrations.starlette_client import OAuth
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, EmailStr, Field
from sqlmodel import Session, select
from starlette.middleware.sessions import SessionMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from content_demand_agent.analytics import run_agent_snapshot
from content_demand_agent.config import settings
from content_demand_agent.db import (
    PlatformConnection,
    User,
    get_session,
    get_user_by_email,
    get_user_by_google_sub,
    init_db,
)
from content_demand_agent.security import encrypt_credential, hash_password, verify_password

SUPPORTED_PLATFORMS = [
    "google_search_console",
    "gemini_citations",
    "chatgpt_citations",
    "semrush",
    "ahrefs",
    "competitor_content_velocity",
]


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class ConnectPlatformRequest(BaseModel):
    platform: str
    login_method: str = Field(pattern="^(credentials|google_oauth)$")
    username: str | None = None
    password: str | None = None


oauth = OAuth()
oauth.register(
    name="google",
    client_id=settings.google_client_id or None,
    client_secret=settings.google_client_secret or None,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)

app = FastAPI(title="Content Demand Capture Agent")
app.add_middleware(SessionMiddleware, secret_key=settings.app_secret_key)
base_dir = Path(__file__).parent
app.mount("/static", StaticFiles(directory=base_dir / "static"), name="static")
templates = Jinja2Templates(directory=str(base_dir / "templates"))


@app.on_event("startup")
def on_startup() -> None:
    init_db()


def _current_user(request: Request, session: Session) -> User:
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not logged in")
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")
    return user


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/")
def ui_home(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "google_configured": bool(settings.google_client_id and settings.google_client_secret),
        },
    )


@app.get("/dashboard")
def dashboard(request: Request, session: Session = Depends(get_session)):
    _current_user(request, session)
    return templates.TemplateResponse("dashboard.html", {"request": request})


@app.post("/auth/register")
def register(payload: RegisterRequest, session: Session = Depends(get_session)) -> dict[str, Any]:
    existing = get_user_by_email(session, payload.email)
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(email=payload.email, password_hash=hash_password(payload.password))
    session.add(user)
    session.commit()
    session.refresh(user)
    return {"id": user.id, "email": user.email}


@app.post("/auth/login")
def login(
    payload: LoginRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> dict[str, str]:
    user = get_user_by_email(session, payload.email)
    if not user or not user.password_hash or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    request.session["user_id"] = user.id
    return {"status": "logged_in"}


@app.get("/auth/google/login")
async def google_login(request: Request):
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(status_code=500, detail="Google OAuth is not configured")
    return await oauth.google.authorize_redirect(request, settings.google_redirect_uri)


@app.get("/auth/google/callback")
async def google_callback(request: Request, session: Session = Depends(get_session)):
    token = await oauth.google.authorize_access_token(request)
    user_info = token.get("userinfo")
    if not user_info:
        user_info = await oauth.google.parse_id_token(request, token)
    sub = user_info["sub"]
    email = user_info["email"]

    user = get_user_by_google_sub(session, sub)
    if not user:
        user = get_user_by_email(session, email)
        if user:
            user.google_sub = sub
        else:
            user = User(email=email, google_sub=sub)
            session.add(user)
    session.commit()
    session.refresh(user)
    request.session["user_id"] = user.id
    request.session["google_email"] = email
    return RedirectResponse(url="/", status_code=302)


@app.post("/auth/logout")
def logout(request: Request) -> dict[str, str]:
    request.session.clear()
    return {"status": "logged_out"}


@app.get("/me")
def me(request: Request, session: Session = Depends(get_session)) -> dict[str, Any]:
    user = _current_user(request, session)
    connections = session.exec(
        select(PlatformConnection).where(PlatformConnection.user_id == user.id)
    ).all()
    return {
        "id": user.id,
        "email": user.email,
        "google_linked": bool(user.google_sub),
        "platform_connections": [
            {
                "platform": c.platform,
                "login_method": c.login_method,
                "username": c.username,
                "google_verified": c.google_verified,
                "google_email": c.google_email,
                "status": c.status,
                "updated_at": c.updated_at.isoformat(),
            }
            for c in connections
        ],
    }


@app.post("/platforms/connect")
def connect_platform(
    payload: ConnectPlatformRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    user = _current_user(request, session)
    platform = payload.platform.strip().lower()
    if platform not in SUPPORTED_PLATFORMS:
        raise HTTPException(status_code=400, detail=f"Unsupported platform: {platform}")

    if payload.login_method == "credentials" and (not payload.username or not payload.password):
        raise HTTPException(status_code=400, detail="username and password are required")
    if payload.login_method == "google_oauth" and not user.google_sub:
        raise HTTPException(
            status_code=400,
            detail="Google account must be linked first via /auth/google/login",
        )

    connection = session.exec(
        select(PlatformConnection).where(
            PlatformConnection.user_id == user.id, PlatformConnection.platform == platform
        )
    ).first()
    if not connection:
        connection = PlatformConnection(
            user_id=user.id,
            platform=platform,
            login_method=payload.login_method,
        )
        session.add(connection)

    connection.login_method = payload.login_method
    connection.username = payload.username
    connection.credential_ref = (
        encrypt_credential(payload.password) if payload.password else connection.credential_ref
    )
    connection.google_verified = payload.login_method == "google_oauth"
    connection.google_email = request.session.get("google_email") if connection.google_verified else None
    connection.status = "connected"
    connection.updated_at = datetime.now(timezone.utc)

    session.commit()
    return {
        "platform": connection.platform,
        "login_method": connection.login_method,
        "google_verified": connection.google_verified,
        "status": connection.status,
    }


@app.post("/platforms/{platform}/verify-google")
def verify_platform_google(
    platform: str,
    request: Request,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    user = _current_user(request, session)
    if not user.google_sub:
        raise HTTPException(status_code=400, detail="Google account not linked on user profile")

    connection = session.exec(
        select(PlatformConnection).where(
            PlatformConnection.user_id == user.id, PlatformConnection.platform == platform
        )
    ).first()
    if not connection:
        raise HTTPException(status_code=404, detail="Platform connection not found")

    connection.google_verified = True
    connection.google_email = request.session.get("google_email")
    connection.updated_at = datetime.now(timezone.utc)
    session.commit()
    return {
        "platform": platform,
        "google_verified": True,
        "google_email": connection.google_email,
    }


@app.get("/platforms")
def list_platforms() -> JSONResponse:
    return JSONResponse({"supported_platforms": SUPPORTED_PLATFORMS})


@app.post("/agent/run")
def run_agent(request: Request, session: Session = Depends(get_session)) -> dict[str, Any]:
    _current_user(request, session)
    return run_agent_snapshot()
