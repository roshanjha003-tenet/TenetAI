"""Org administration: people, invites, verified domains, the audit log and model usage."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.access import TXT_PREFIX, add_domain, create_invite, verify_domain
from app.api.views import user_view
from app.auth import current_user
from app.authz import require
from app.db import get_session
from app.identity import audit, revoke_sessions
from app.models import AuditLog, Invite, Org, OrgDomain, Space, UsageRecord, User

router = APIRouter(prefix="/admin")


def person_view(u: User) -> dict[str, Any]:
    return {
        **user_view(u),
        "active": u.active,
        "is_org_admin": u.is_org_admin,
        "external": u.external,
    }


@router.get("/people")
async def people(
    user: User = Depends(current_user), session: AsyncSession = Depends(get_session)
) -> list[dict[str, Any]]:
    await require(session, user, "org.admin")
    return [person_view(u) for u in await session.scalars(select(User).order_by(User.name))]


class PersonIn(BaseModel):
    active: bool | None = None
    is_org_admin: bool | None = None


@router.patch("/people/{user_id}")
async def update_person(
    user_id: uuid.UUID,
    body: PersonIn,
    request: Request,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Turn someone off (their sessions end at once) or change who is an org admin."""
    await require(session, user, "org.admin")
    person = await session.get(User, user_id)
    if person is None:
        raise HTTPException(404, "no such person")
    if person.id == user.id and (body.active is False or body.is_org_admin is False):
        raise HTTPException(422, "you can't turn off or demote yourself")
    if body.is_org_admin is not None and body.is_org_admin != person.is_org_admin:
        if body.is_org_admin and person.external:
            raise HTTPException(422, "external guests can't be org admins")
        person.is_org_admin = body.is_org_admin
        await audit(
            session,
            "role.changed",
            request=request,
            actor=user,
            subject=person.email,
            details={"is_org_admin": body.is_org_admin},
        )
    if body.active is not None and body.active != person.active:
        person.active = body.active
        details: dict[str, Any] = {"active": body.active}
        if not body.active:
            details["sessions_revoked"] = await revoke_sessions(session, person.id)
        await audit(
            session,
            "user.deactivated" if not body.active else "user.reactivated",
            request=request,
            actor=user,
            subject=person.email,
            details=details,
        )
    await session.commit()
    return person_view(person)


# --- invites ---------------------------------------------------------------------------------


class InviteIn(BaseModel):
    email: str
    space: str | None = None  # "@payments-redesign"
    role: str = "member"


def invite_view(i: Invite, spaces: dict[uuid.UUID, str]) -> dict[str, Any]:
    status = (
        "accepted"
        if i.accepted_at
        else "expired"
        if i.expires_at <= datetime.now(UTC)
        else ("pending")
    )
    return {
        "id": str(i.id),
        "email": i.email,
        "space": f"@{spaces[i.space_id]}" if i.space_id in spaces else None,
        "role": i.role,
        "status": status,
        "expires_at": i.expires_at.isoformat(),
        "created_at": i.created_at.isoformat(),
    }


@router.post("/invites", status_code=201)
async def invite(
    body: InviteIn,
    request: Request,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Email delivery is stubbed: the response carries the link for you to send."""
    space = None
    if body.space:
        space = await session.scalar(select(Space).where(Space.handle == body.space.lstrip("@")))
        if space is None:
            raise HTTPException(404, f"no space {body.space}")
        await require(session, user, "member.manage", space)
    else:
        await require(session, user, "member.invite")
    row, token = await create_invite(
        session, user, body.email, space=space, role=body.role, request=request
    )
    await session.commit()
    spaces = {space.id: space.handle} if space else {}
    link = f"{request.app.state.settings.web_url}/invite/{token}"
    return {**invite_view(row, spaces), "link": link}


@router.get("/invites")
async def invites(
    user: User = Depends(current_user), session: AsyncSession = Depends(get_session)
) -> list[dict[str, Any]]:
    await require(session, user, "member.invite")
    rows = list(await session.scalars(select(Invite).order_by(Invite.created_at.desc())))
    spaces = dict((await session.execute(select(Space.id, Space.handle))).all())
    return [invite_view(i, spaces) for i in rows]


# --- domains ---------------------------------------------------------------------------------


class DomainIn(BaseModel):
    domain: str


def domain_view(d: OrgDomain) -> dict[str, Any]:
    return {
        "domain": d.domain,
        "verified": d.verified_at is not None,
        "verified_at": d.verified_at.isoformat() if d.verified_at else None,
        "txt_record": f"{TXT_PREFIX}{d.verification_token}",
    }


@router.get("/domains")
async def domains(
    user: User = Depends(current_user), session: AsyncSession = Depends(get_session)
) -> list[dict[str, Any]]:
    await require(session, user, "domain.manage")
    return [domain_view(d) for d in await session.scalars(select(OrgDomain).order_by("domain"))]


@router.post("/domains", status_code=201)
async def new_domain(
    body: DomainIn,
    request: Request,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    await require(session, user, "domain.manage")
    row = await add_domain(session, user, body.domain, request)
    await session.commit()
    return domain_view(row)


@router.post("/domains/{domain}/verify")
async def check_domain(
    domain: str,
    request: Request,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    await require(session, user, "domain.manage")
    try:
        row = await verify_domain(session, user, domain, request.app.state.dns_txt, request)
    finally:
        await session.commit()  # keep the audit record of a failed check too
    return domain_view(row)


# --- accounting ------------------------------------------------------------------------------


@router.get("/audit")
async def audit_log(
    limit: int = Query(100, le=500),
    action: str | None = None,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    await require(session, user, "audit.read")
    query = select(AuditLog).order_by(AuditLog.seq.desc()).limit(limit)
    if action:
        query = query.where(AuditLog.action == action)
    rows = list(await session.scalars(query))
    names = dict((await session.execute(select(User.id, User.name))).all())
    return [
        {
            "at": r.at.isoformat(),
            "action": r.action,
            "actor": names.get(r.actor_id),
            "subject": r.subject,
            "outcome": r.outcome,
            "reason": r.reason,
            "ip": r.ip,
            "details": r.details,
        }
        for r in rows
    ]


def month_start() -> datetime:
    return datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)


@router.get("/usage")
async def usage(
    user: User = Depends(current_user), session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    await require(session, user, "usage.read")
    org = await session.get(Org, user.org_id)
    rows = (
        await session.execute(
            select(
                UsageRecord.task,
                UsageRecord.model,
                func.count(),
                func.sum(UsageRecord.input_tokens),
                func.sum(UsageRecord.output_tokens),
                func.sum(UsageRecord.cost_usd),
            )
            .where(UsageRecord.at >= month_start())
            .group_by(UsageRecord.task, UsageRecord.model)
            .order_by(func.sum(UsageRecord.cost_usd).desc())
        )
    ).all()
    spent = sum((r[5] or Decimal(0) for r in rows), Decimal(0))
    return {
        "month_start": month_start().isoformat(),
        "spent_usd": float(spent),
        "cap_usd": float(org.monthly_cap_usd) if org.monthly_cap_usd is not None else None,
        "by_task": [
            {
                "task": task,
                "model": model,
                "calls": calls,
                "input_tokens": int(tin or 0),
                "output_tokens": int(tout or 0),
                "cost_usd": float(cost or 0),
            }
            for task, model, calls, tin, tout, cost in rows
        ],
    }


class CapIn(BaseModel):
    cap_usd: float | None


@router.put("/usage/cap")
async def set_cap(
    body: CapIn,
    request: Request,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    await require(session, user, "org.admin")
    if body.cap_usd is not None and body.cap_usd < 0:
        raise HTTPException(422, "the cap can't be negative")
    org = await session.get(Org, user.org_id)
    org.monthly_cap_usd = body.cap_usd
    await audit(
        session, "usage.cap_changed", request=request, actor=user, details={"cap_usd": body.cap_usd}
    )
    await session.commit()
    return {"cap_usd": body.cap_usd}
