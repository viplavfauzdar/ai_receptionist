"""
JWT session helpers for Reeva auth.

Session cookie: reeva_session (HTTP-only, set by the Next.js frontend server)
Token payload:  { sub: email, name: str, business_id: int|None, exp: timestamp }

The token flows like this:
  1. Backend OAuth callback issues a JWT and redirects to
     {FRONTEND}/auth/callback?token=JWT
  2. Next.js /auth/callback page sets it as an httpOnly cookie on the frontend domain
  3. Frontend middleware reads the cookie to protect /dashboard routes
  4. Frontend server components pass it as  Authorization: Bearer <token>  to the backend
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
from fastapi import HTTPException, Request, status

from .config import settings

ALGORITHM = "HS256"
COOKIE_NAME = "reeva_session"


def create_session_token(
    *,
    email: str,
    name: str | None,
    business_id: int | None,
) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=settings.auth_token_expire_hours)
    payload = {
        "sub": email,
        "name": name or "",
        "business_id": business_id,
        "exp": expire,
    }
    return jwt.encode(payload, settings.auth_secret_key, algorithm=ALGORITHM)


def decode_session_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.auth_secret_key, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")


def get_current_user(request: Request) -> dict:
    """
    Reads the session JWT from either:
      - Authorization: Bearer <token>  header  (Next.js server components)
      - reeva_session cookie             (direct browser requests)
    """
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return decode_session_token(auth_header[7:])

    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return decode_session_token(token)
