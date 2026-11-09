"""Findings API: share with the space, reply, promote to a decision proposal."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.spaces import get_space
from app.auth import current_user
from app.authz import require
from app.db import get_session
from app.findings import finding_views, list_findings, mark_promoted, reply, share_finding
from app.models import Area, Finding, Space, User
from app.notify import dispatch

router = APIRouter()


class FindingIn(BaseModel):
    text: str
    evidence: list[dict[str, Any]] = Field(default_factory=list)


class ReplyIn(BaseModel):
    stance: str
    text: str = ""


@router.get("/spaces/{handle}/findings")
async def space_findings(
    handle: str,
    mention: str | None = None,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    space = await get_space(session, handle, user)
    return await finding_views(session, await list_findings(session, space, mention))


@router.post("/spaces/{handle}/findings", status_code=201)
async def new_finding(
    handle: str,
    body: FindingIn,
    request: Request,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    space = await get_space(session, handle, user)
    finding, notices = await share_finding(
        session, space=space, author=user, text=body.text, evidence=body.evidence
    )
    await session.commit()
    await dispatch(request.app.state, notices)
    return (await finding_views(session, [finding]))[0]


async def load(session: AsyncSession, finding_id: uuid.UUID, user: User) -> Finding:
    finding = await session.get(Finding, finding_id)
    if finding is None:
        raise HTTPException(404, "no such finding")
    await require(session, user, "space.read", await session.get(Space, finding.space_id))
    return finding


@router.get("/findings/{finding_id}")
async def read_finding(
    finding_id: uuid.UUID,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    return (await finding_views(session, [await load(session, finding_id, user)]))[0]


@router.post("/findings/{finding_id}/replies", status_code=201)
async def reply_to(
    finding_id: uuid.UUID,
    body: ReplyIn,
    request: Request,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    finding = await load(session, finding_id, user)
    _, notices = await reply(
        session, finding_id=finding.id, author=user, stance=body.stance, text=body.text
    )
    await session.commit()
    await dispatch(request.app.state, notices)
    return (await finding_views(session, [finding]))[0]


@router.post("/findings/{finding_id}/promote", status_code=201)
async def promote(
    finding_id: uuid.UUID,
    request: Request,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Turn a finding into a decision proposal: Capture drafts it, then the usual review."""
    from app.sessions import Shared, propose_decision

    finding = await load(session, finding_id, user)
    await require(session, user, "finding.promote", await session.get(Space, finding.space_id))
    owns_area = await session.scalar(
        select(Area.id).where(Area.space_id == finding.space_id, Area.owner_id == user.id).limit(1)
    )
    if user.id != finding.author_id and not owns_area:
        raise HTTPException(403, "only its author or an area owner can promote a finding")
    if finding.status == "promoted":
        raise HTTPException(409, "this finding was already promoted")
    if request.app.state.llm is None:
        raise HTTPException(503, "the model gateway isn't configured (ANTHROPIC_API_KEY)")
    await session.commit()

    shared = Shared(finding.text, finding.event_id, "decision")
    notices = await propose_decision(request.app.state, user, finding.space_id, shared)
    if shared.proposal_id is None:
        raise HTTPException(422, "; ".join(shared.notes) or "couldn't draft a proposal")
    finding = await session.get(Finding, finding_id, populate_existing=True)
    await mark_promoted(session, finding, shared.proposal_id, user)
    await session.commit()
    await dispatch(request.app.state, notices)
    view = (await finding_views(session, [finding]))[0]
    return {
        **view,
        "decision_key": shared.decision_key,
        "proposal_status": shared.status,
        "notes": shared.notes,
    }
