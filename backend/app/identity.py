"""Sessions and the audit log.

A session is a random 32-byte token in an HttpOnly cookie; the database keeps only its SHA-256.
Sessions expire after `session_idle_hours` without use and `session_max_days` in total, and can be
revoked one by one or all at once.
"""

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import Request, Response
from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models import AuditLog, AuthSession, User

COOKIE = "tenet_session"
TOUCH_EVERY = timedelta(minutes=5)


def now() -> datetime:
    return datetime.now(UTC)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def client_ip(request: Request | None) -> str:
    if request is None:
        return ""
    forwarded = request.headers.get("x-forwarded-for", "")
    return (forwarded.split(",")[0].strip() or (request.client.host if request.client else ""))[:64]


def user_agent(request: Request | None) -> str:
    return (request.headers.get("user-agent", "") if request else "")[:300]


async def audit(
    session: AsyncSession,
    action: str,
    *,
    request: Request | None = None,
    actor: User | None = None,
    org_id: uuid.UUID | None = None,
    subject: str = "",
    outcome: str = "success",
    reason: str = "",
    details: dict[str, Any] | None = None,
) -> None:
    # A plain INSERT (no RETURNING): a failed sign-in has no org, so its row can't be read back.
    await session.execute(
        insert(AuditLog).values(
            id=uuid.uuid4(),
            org_id=org_id or (actor.org_id if actor else None),
            actor_id=actor.id if actor else None,
            action=action,
            subject=subject[:320],
            outcome=outcome,
            reason=reason[:2000],
            ip=client_ip(request),
            user_agent=user_agent(request),
            details=details or {},
        )
    )


async def start_session(
    session: AsyncSession, settings: Settings, user: User, provider: str, request: Request | None
) -> str:
    token = secrets.token_urlsafe(32)
    session.add(
        AuthSession(
            token_hash=hash_token(token),
            user_id=user.id,
            provider=provider,
            ip=client_ip(request),
            user_agent=user_agent(request),
            expires_at=now() + timedelta(days=settings.session_max_days),
        )
    )
    await audit(
        session,
        "auth.sign_in",
        request=request,
        actor=user,
        subject=user.email,
        details={"provider": provider},
    )
    return token


async def session_user(
    session: AsyncSession, settings: Settings, token: str
) -> tuple[User, AuthSession] | None:
    row = await session.scalar(
        select(AuthSession).where(AuthSession.token_hash == hash_token(token))
    )
    if row is None or row.revoked_at is not None:
        return None
    t = now()
    if t >= row.expires_at or t >= row.last_seen_at + timedelta(hours=settings.session_idle_hours):
        return None
    user = await session.get(User, row.user_id)
    if user is None or not user.active:
        return None
    if t - row.last_seen_at > TOUCH_EVERY:
        row.last_seen_at = t
    return user, row


async def revoke_sessions(
    session: AsyncSession, user_id: uuid.UUID, *, except_id: uuid.UUID | None = None
) -> int:
    query = update(AuthSession).where(
        AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None)
    )
    if except_id is not None:
        query = query.where(AuthSession.id != except_id)
    result = await session.execute(query.values(revoked_at=now()))
    return result.rowcount or 0


def set_cookie(response: Response, settings: Settings, token: str) -> None:
    response.set_cookie(
        COOKIE,
        token,
        max_age=settings.session_max_days * 86400,
        httponly=True,
        secure=not settings.dev,
        samesite="lax",
        path="/",
    )


def clear_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(COOKIE, path="/", httponly=True, secure=not settings.dev, samesite="lax")
