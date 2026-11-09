"""Sign-in, sign-out and your sessions. Every outcome lands in the audit log."""

import uuid
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.access import accept_invite, admit
from app.api.views import user_view
from app.auth import check_csrf, current_user
from app.db import get_session
from app.identity import (
    audit,
    clear_cookie,
    now,
    revoke_sessions,
    set_cookie,
    start_session,
)
from app.models import AuthSession, Invite, Org, Space, User
from app.oidc import PROVIDERS, SignInError
from app.tenancy import dev_token_org, invite_org, set_org

router = APIRouter()
FLOW_COOKIE = "tenet_oidc"


def oidc_of(request: Request):
    return request.app.state.oidc


@router.get("/auth/config")
async def auth_config(request: Request) -> dict[str, Any]:
    enabled = oidc_of(request).enabled()
    return {
        "providers": [
            {"id": name, "label": p.label} for name, p in PROVIDERS.items() if enabled[name]
        ],
        "dev": request.app.state.settings.dev,
    }


@router.get("/auth/{provider}/start", include_in_schema=False)
async def oidc_start(
    provider: str, request: Request, next: str = "/", invite: str | None = None
) -> RedirectResponse:
    settings = request.app.state.settings
    try:
        url, flow = oidc_of(request).start(provider, next, invite)
    except SignInError as exc:
        return failed_redirect(settings, str(exc))
    response = RedirectResponse(url, status_code=302)
    response.set_cookie(
        FLOW_COOKIE,
        flow,
        max_age=600,
        httponly=True,
        secure=not settings.dev,
        samesite="lax",
        path="/api/auth",
    )
    return response


def failed_redirect(settings, reason: str) -> RedirectResponse:
    return RedirectResponse(f"{settings.web_url}/login?{urlencode({'error': reason})}", 302)


@router.get("/auth/{provider}/callback", include_in_schema=False)
async def oidc_callback(
    provider: str,
    request: Request,
    code: str | None = None,
    state: str = "",
    error: str | None = None,
) -> RedirectResponse:
    state_ = request.app.state
    settings = state_.settings
    oidc = oidc_of(request)
    identity = None
    try:
        if error or not code:
            raise SignInError(f"{provider} sign-in was cancelled" if error else "no sign-in code")
        flow = oidc.read_flow(provider, request.cookies.get(FLOW_COOKIE), state)
        identity = await oidc.finish(provider, code, flow)
        async with state_.sessionmaker() as session, session.begin():
            user = await admit(session, identity, invite_token=flow.get("i"), request=request)
            token = await start_session(session, settings, user, provider, request)
    except SignInError as exc:
        async with state_.sessionmaker() as session, session.begin():
            await audit(
                session,
                "auth.sign_in",
                request=request,
                outcome="failure",
                reason=str(exc),
                subject=identity.email if identity else "",
                details={"provider": provider},
            )
        response = failed_redirect(settings, str(exc))
        response.delete_cookie(FLOW_COOKIE, path="/api/auth")
        return response
    response = RedirectResponse(f"{settings.web_url}{flow['a']}", 302)
    response.delete_cookie(FLOW_COOKIE, path="/api/auth")
    set_cookie(response, settings, token)
    return response


class DevSignIn(BaseModel):
    token: str


@router.post("/auth/dev")
async def dev_sign_in(
    body: DevSignIn, request: Request, session: AsyncSession = Depends(get_session)
) -> Any:
    """Development only: sign in as a seeded user by their dev token, into a normal session."""
    from fastapi.responses import JSONResponse

    settings = request.app.state.settings
    if not settings.dev:
        raise HTTPException(404)
    check_csrf(request)
    org = await dev_token_org(session, body.token.strip())
    user = None
    if org is not None:
        await set_org(session, org)
        user = await session.scalar(select(User).where(User.api_token == body.token.strip()))
    if user is None or not user.active:
        await audit(
            session,
            "auth.sign_in",
            request=request,
            outcome="failure",
            reason="unknown dev token",
            details={"provider": "dev"},
        )
        await session.commit()
        raise HTTPException(401, "unknown dev token")
    token = await start_session(session, settings, user, "dev", request)
    await session.commit()
    response = JSONResponse(user_view(user))
    set_cookie(response, settings, token)
    return response


@router.post("/auth/logout")
async def logout(
    request: Request,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> Any:
    from fastapi.responses import JSONResponse

    current: AuthSession | None = request.state.auth_session
    if current is not None:
        current.revoked_at = now()
        await audit(session, "auth.sign_out", request=request, actor=user, subject=user.email)
        await session.commit()
    response = JSONResponse({"signed_out": True})
    clear_cookie(response, request.app.state.settings)
    return response


@router.post("/auth/logout-all")
async def logout_all(
    request: Request,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> Any:
    from fastapi.responses import JSONResponse

    count = await revoke_sessions(session, user.id)
    await audit(
        session,
        "auth.sessions_revoked",
        request=request,
        actor=user,
        subject=user.email,
        details={"count": count, "scope": "all"},
    )
    await session.commit()
    response = JSONResponse({"revoked": count})
    clear_cookie(response, request.app.state.settings)
    return response


def session_view(row: AuthSession, current: AuthSession | None) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "provider": row.provider,
        "ip": row.ip,
        "user_agent": row.user_agent,
        "created_at": row.created_at.isoformat(),
        "last_seen_at": row.last_seen_at.isoformat(),
        "expires_at": row.expires_at.isoformat(),
        "current": current is not None and row.id == current.id,
    }


@router.get("/auth/sessions")
async def my_sessions(
    request: Request,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    rows = await session.scalars(
        select(AuthSession)
        .where(
            AuthSession.user_id == user.id,
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > now(),
        )
        .order_by(AuthSession.last_seen_at.desc())
    )
    return [session_view(r, request.state.auth_session) for r in rows]


@router.delete("/auth/sessions/{session_id}")
async def revoke_one(
    session_id: uuid.UUID,
    request: Request,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, bool]:
    row = await session.get(AuthSession, session_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(404, "no such session")
    row.revoked_at = now()
    await audit(
        session,
        "auth.sessions_revoked",
        request=request,
        actor=user,
        subject=user.email,
        details={"session": str(row.id)},
    )
    await session.commit()
    return {"revoked": True}


# --- invites (the person invited) ------------------------------------------------------------


@router.get("/invites/{token}")
async def read_invite(token: str, request: Request) -> dict[str, Any]:
    """What an invite link is for, so the page can say who invited you where. No sign-in."""
    from app.identity import hash_token

    async with request.app.state.sessionmaker() as session, session.begin():
        org_id = await invite_org(session, token)
        if org_id is None:
            raise HTTPException(404, "that invite link isn't valid")
        await set_org(session, org_id)
        invite = await session.scalar(select(Invite).where(Invite.token_hash == hash_token(token)))
        org = await session.get(Org, org_id)
        space = await session.get(Space, invite.space_id) if invite.space_id else None
        inviter = await session.get(User, invite.invited_by)
        return {
            "org": org.name,
            "space": f"@{space.handle}" if space else None,
            "role": invite.role,
            "email": invite.email,
            "invited_by": inviter.name,
            "expired": invite.expires_at <= now(),
            "accepted": invite.accepted_at is not None,
        }


@router.post("/invites/{token}/accept")
async def accept(
    token: str,
    request: Request,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Already signed in (say, to another space): accept as yourself, if the invite is yours."""
    if await invite_org(session, token) != user.org_id:
        raise HTTPException(403, "this invite is for another org")
    try:
        await accept_invite(session, token, user.email, user.name, request)
    except SignInError as exc:
        raise HTTPException(403, str(exc)) from exc
    await session.commit()
    return {"accepted": True}
