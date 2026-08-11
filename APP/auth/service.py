"""Auth: GitHub/Google OAuth exchange, password hashing, OTP, JWT issuance
and verification. `get_current_user` replaces the old shared-secret check
everywhere — mandatory login supersedes it, so there's no dual mode.

Env vars expected at runtime (plain names, not the _PROD/_DEV suffixed
variants used in local notes for convenience — each deployment's Container
App secrets supply whichever pair is right for that environment):
  GITHUB_CLIENT_ID, GITHUB_CLIENT_SECRET
  GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET
  JWT_SECRET_KEY  (generate with: python -c "import secrets; print(secrets.token_urlsafe(32))")
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import httpx
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from APP import db

JWT_ALGORITHM = "HS256"
JWT_EXPIRY_DAYS = 7

GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"
GITHUB_EMAILS_URL = "https://api.github.com/user/emails"

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"


class OAuthError(Exception):
    """Raised when a provider's token/userinfo exchange fails or returns no verified email."""


def _jwt_secret() -> str:
    secret = os.getenv("JWT_SECRET_KEY")
    if not secret:
        raise RuntimeError("JWT_SECRET_KEY is not set")
    return secret


# --------------------------------------------------------------------------- #
# GitHub / Google OAuth exchange
# --------------------------------------------------------------------------- #

def exchange_github_code(code: str) -> dict:
    """Exchanges an OAuth code for the GitHub user's id + verified primary email.

    The client secret never leaves this function — it's read from the
    environment and sent directly to GitHub, not passed through from the caller.
    """
    client_id = os.getenv("GITHUB_CLIENT_ID")
    client_secret = os.getenv("GITHUB_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise RuntimeError("GITHUB_CLIENT_ID/GITHUB_CLIENT_SECRET are not set")

    with httpx.Client(timeout=10.0) as client:
        token_resp = client.post(
            GITHUB_TOKEN_URL,
            headers={"Accept": "application/json"},
            data={"client_id": client_id, "client_secret": client_secret, "code": code},
        )
        token_resp.raise_for_status()
        access_token = token_resp.json().get("access_token")
        if not access_token:
            raise OAuthError("GitHub did not return an access token")

        auth_headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github+json"}
        user_resp = client.get(GITHUB_USER_URL, headers=auth_headers)
        user_resp.raise_for_status()
        user = user_resp.json()

        # GitHub's /user.email is null unless the user made it public — fall
        # back to /user/emails (requires the user:email scope) for the
        # verified primary address.
        email = user.get("email")
        if not email:
            emails_resp = client.get(GITHUB_EMAILS_URL, headers=auth_headers)
            emails_resp.raise_for_status()
            for entry in emails_resp.json():
                if entry.get("primary") and entry.get("verified"):
                    email = entry.get("email")
                    break

    if not email:
        raise OAuthError("GitHub account has no verified email available")

    return {"provider_user_id": str(user["id"]), "email": email}


def exchange_google_code(code: str, redirect_uri: str) -> dict:
    """Exchanges an OAuth code for the Google user's id + verified email."""
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise RuntimeError("GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET are not set")

    with httpx.Client(timeout=10.0) as client:
        token_resp = client.post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        token_resp.raise_for_status()
        access_token = token_resp.json().get("access_token")
        if not access_token:
            raise OAuthError("Google did not return an access token")

        userinfo_resp = client.get(GOOGLE_USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"})
        userinfo_resp.raise_for_status()
        userinfo = userinfo_resp.json()

    if not userinfo.get("email") or not userinfo.get("email_verified"):
        raise OAuthError("Google account has no verified email")

    return {"provider_user_id": userinfo["sub"], "email": userinfo["email"]}


# --------------------------------------------------------------------------- #
# Password hashing
# --------------------------------------------------------------------------- #

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


# --------------------------------------------------------------------------- #
# OTP — 6-digit codes, hashed at rest, never stored or logged in plaintext
# --------------------------------------------------------------------------- #

def generate_otp_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_otp_code(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def verify_otp_code(code: str, code_hash: str) -> bool:
    return hmac.compare_digest(hash_otp_code(code), code_hash)


def is_otp_expired(expires_at_iso: str) -> bool:
    expires_at = datetime.fromisoformat(expires_at_iso)
    return datetime.now(timezone.utc) > expires_at


# --------------------------------------------------------------------------- #
# JWT
# --------------------------------------------------------------------------- #

def create_access_token(user_id: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": user_id, "iat": now, "exp": now + timedelta(days=JWT_EXPIRY_DAYS)}
    return jwt.encode(payload, _jwt_secret(), algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> str:
    """Returns the user id encoded in the token, or raises jwt exceptions on failure."""
    payload = jwt.decode(token, _jwt_secret(), algorithms=[JWT_ALGORITHM])
    return payload["sub"]


# auto_error=False so a missing/!Bearer header falls through to the explicit
# 401 below rather than FastAPI's generic 403 — keeps the response identical
# to the hand-rolled Header() version this replaced, while still declaring a
# real securityScheme so /docs renders a single "Authorize" button instead of
# a raw header field on every endpoint.
_bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme)):
    """FastAPI dependency replacing the old require_api_key check everywhere.

    Every route that used to depend on require_api_key now depends on this
    instead — mandatory login supersedes the shared-secret deterrent.
    """
    if credentials is None or (credentials.scheme or "").lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing or malformed Authorization header")

    token = (credentials.credentials or "").strip()
    try:
        user_id = decode_access_token(token)
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    user = db.get_user_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    return user
