"""
backend/auth.py — Google OAuth + session-cookie auth for the RTL backend.

Flow:
    GET  /auth/login     — redirects the browser to Google.
    GET  /auth/callback  — Google redirects back with a code; we exchange it,
                           upsert the user row in Supabase, and store
                           { id, email } in the signed session cookie.
    POST /auth/logout    — clears the session.
    GET  /auth/me        — returns the current user (401 if unauthenticated).

Any route that depends on `get_current_user` will 401 when the session
cookie is missing or stale, so the front-end can redirect to /auth/login.

Environment variables required:
    GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET  — OAuth client credentials.
    SECRET_KEY                              — used to sign session cookies.
    SUPABASE_DB_URL                         — for upserting the user row.
    OAUTH_REDIRECT_URI (optional, default http://localhost:8000/auth/callback)
    FRONTEND_URL (optional, default http://localhost:3000) — where the
        user is sent after a successful login.
"""
import os
from typing import Optional

import psycopg
from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse


# ── OAuth client ──────────────────────────────────────────────────────────────

oauth = OAuth()
oauth.register(
    name="google",
    client_id=os.environ.get("GOOGLE_CLIENT_ID"),
    client_secret=os.environ.get("GOOGLE_CLIENT_SECRET"),
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)


def _redirect_uri() -> str:
    return os.environ.get("OAUTH_REDIRECT_URI", "http://localhost:8000/auth/callback")


def _frontend_url() -> str:
    return os.environ.get("FRONTEND_URL", "http://localhost:3000")


# ── User upsert ───────────────────────────────────────────────────────────────

def _upsert_user(user_id: str, email: str) -> None:
    """Insert or update the user row in Supabase. Uses `sub` as the stable PK."""
    conn_str = os.environ["SUPABASE_DB_URL"]
    with psycopg.connect(conn_str, autocommit=True, prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO users (id, email, created_at)
                VALUES (%s, %s, NOW())
                ON CONFLICT (id) DO UPDATE SET email = EXCLUDED.email;
                """,
                (user_id, email),
            )


# ── FastAPI dependency ────────────────────────────────────────────────────────

def get_current_user(request: Request) -> dict:
    """Dependency that returns { id, email } for the logged-in user, or 401s."""
    user = request.session.get("user")
    if not user or "id" not in user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


def get_optional_user(request: Request) -> Optional[dict]:
    """Like get_current_user but returns None instead of raising."""
    user = request.session.get("user")
    if not user or "id" not in user:
        return None
    return user


# ── Router ────────────────────────────────────────────────────────────────────

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/login")
async def login(request: Request):
    """Kick off the Google OAuth flow."""
    return await oauth.google.authorize_redirect(request, _redirect_uri())


@router.get("/callback")
async def callback(request: Request):
    """Exchange the OAuth code for user info, upsert, set session, redirect."""
    try:
        token = await oauth.google.authorize_access_token(request)
    except OAuthError as exc:
        raise HTTPException(status_code=400, detail=f"OAuth error: {exc.error}")

    info = token.get("userinfo") or await oauth.google.parse_id_token(request, token)
    user_id = info.get("sub")
    email = info.get("email")
    if not user_id or not email:
        raise HTTPException(status_code=400, detail="Google did not return sub/email.")

    _upsert_user(user_id, email)

    request.session["user"] = {"id": user_id, "email": email}
    return RedirectResponse(url=_frontend_url())


@router.post("/logout")
async def logout(request: Request):
    request.session.pop("user", None)
    return {"ok": True}


@router.get("/me")
async def me(user: dict = Depends(get_current_user)):
    return user
