"""Who is calling. Identity comes from a session cookie (or, in dev only, a seeded bearer token),
never from the request body.

Cookie-authenticated requests that change state must also send `X-Tenet-CSRF: 1` from the web
app's own origin; a cross-site form can't set that header, so it can't act as the user.

Once the caller is known, the request acts for their org: row-level security shows it nothing else.
"""

from urllib.parse import urlparse

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.identity import COOKIE, session_user
from app.models import AuthSession, User
from app.tenancy import dev_token_org, session_org, set_org

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def origin_of(url: str) -> str:
    parts = urlparse(url)
    return f"{parts.scheme}://{parts.netloc}"


def check_csrf(request: Request) -> None:
    if request.method in SAFE_METHODS:
        return
    if request.headers.get("x-tenet-csrf") != "1":
        raise HTTPException(403, "missing CSRF header")
    origin = request.headers.get("origin")
    if origin and origin != origin_of(request.app.state.settings.web_url):
        raise HTTPException(403, "cross-site request refused")


async def current_auth(request: Request, session: AsyncSession) -> tuple[User, AuthSession | None]:
    settings = request.app.state.settings
    cookie = request.cookies.get(COOKIE)
    if cookie:
        org = await session_org(session, cookie)
        if org is not None:
            await set_org(session, org)
        found = await session_user(session, settings, cookie) if org else None
        if found is None:
            raise HTTPException(401, "session expired; sign in again")
        check_csrf(request)
        return found
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() == "bearer" and token:
        if not settings.dev:
            raise HTTPException(401, "token sign-in is only available in development")
        token = token.strip()
        org = await dev_token_org(session, token)
        if org is not None:
            await set_org(session, org)
            user = await session.scalar(select(User).where(User.api_token == token))
            if user is not None and user.active:
                return user, None
        raise HTTPException(401, "invalid token", headers={"WWW-Authenticate": "Bearer"})
    raise HTTPException(401, "sign in required")


async def current_user(request: Request, session: AsyncSession = Depends(get_session)) -> User:
    user, auth_session = await current_auth(request, session)
    request.state.user = user
    request.state.auth_session = auth_session
    return user
