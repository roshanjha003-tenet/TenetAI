"""JSON shapes the API returns. Plain functions so the web app's types stay easy to follow."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Area,
    Event,
    Item,
    Member,
    PRCheck,
    Proposal,
    ProposalReview,
    Pushback,
    Space,
    StateVersion,
    User,
)
from app.review import STAGES


def user_view(user: User | None) -> dict[str, Any] | None:
    if user is None:
        return None
    return {
        "id": str(user.id),
        "name": user.name,
        "email": user.email,
        "title": user.title,
        "github_login": user.github_login,
    }


async def users_by_id(session: AsyncSession, ids: set[Any]) -> dict[Any, User]:
    ids = {i for i in ids if i is not None}
    if not ids:
        return {}
    return {u.id: u for u in await session.scalars(select(User).where(User.id.in_(ids)))}


def space_view(space: Space) -> dict[str, Any]:
    return {
        "id": str(space.id),
        "handle": space.handle,
        "name": space.name,
        "goal": space.goal,
        "head_version": space.head_version,
        "created_at": space.created_at.isoformat(),
    }


def item_view(item: Item) -> dict[str, Any]:
    return {
        "id": str(item.id),
        "kind": item.kind,
        "url": item.url,
        "title": item.title,
        "excerpt": item.excerpt,
        "added_at": item.added_at.isoformat(),
    }


def version_view(v: StateVersion, users: dict[Any, User]) -> dict[str, Any]:
    return {
        "version": v.version,
        "parent_version": v.parent_version,
        "summary": v.summary,
        "committed_by": user_view(users.get(v.committed_by)),
        "created_at": v.created_at.isoformat(),
        "snapshot": v.snapshot,
    }


def event_view(e: Event, users: dict[Any, User]) -> dict[str, Any]:
    return {
        "id": str(e.id),
        "seq": e.seq,
        "type": e.type,
        "at": e.at.isoformat(),
        "actor": user_view(users.get(e.actor_id)),
        "target": {"kind": e.target_kind, "id": e.target_id, "revision": e.target_revision},
        "payload": e.payload,
        "caused_by": str(e.caused_by) if e.caused_by else None,
    }


def check_view(c: PRCheck) -> dict[str, Any]:
    return {
        "id": str(c.id),
        "repo": c.repo,
        "pr_number": c.pr_number,
        "head_sha": c.head_sha,
        "result": c.result,
        "conclusion": c.conclusion,
        "title": c.title,
        "summary": c.summary,
        "findings": c.findings,
        "pr_title": c.pr_title,
        "pr_author": c.pr_author,
        "pr_url": c.pr_url,
        "created_at": c.created_at.isoformat(),
    }


async def space_detail(session: AsyncSession, space: Space) -> dict[str, Any]:
    members = list(await session.scalars(select(Member).where(Member.space_id == space.id)))
    areas = list(await session.scalars(select(Area).where(Area.space_id == space.id)))
    items = list(
        await session.scalars(select(Item).where(Item.space_id == space.id).order_by(Item.added_at))
    )
    users = await users_by_id(session, {m.user_id for m in members} | {a.owner_id for a in areas})
    owned = {a.owner_id: [] for a in areas}
    for a in areas:
        owned[a.owner_id].append(a.key)
    return {
        **space_view(space),
        "members": [
            {**user_view(users[m.user_id]), "role": m.role, "areas": owned.get(m.user_id, [])}
            for m in members
        ],
        "areas": [
            {"key": a.key, "name": a.name, "owner": user_view(users[a.owner_id])} for a in areas
        ],
        "items": [item_view(i) for i in items],
        "stages": [{"number": s.number, "name": s.name, "area": s.area_key} for s in STAGES],
    }


async def proposal_detail(session: AsyncSession, proposal: Proposal) -> dict[str, Any]:
    reviews = list(
        await session.scalars(
            select(ProposalReview)
            .where(ProposalReview.proposal_id == proposal.id)
            .order_by(ProposalReview.stage)
        )
    )
    pushbacks = list(
        await session.scalars(
            select(Pushback)
            .where(Pushback.proposal_id == proposal.id)
            .order_by(Pushback.created_at)
        )
    )
    areas = {
        a.key: a
        for a in await session.scalars(select(Area).where(Area.space_id == proposal.space_id))
    }
    users = await users_by_id(
        session,
        {proposal.proposer_id}
        | {r.reviewer_id for r in reviews}
        | {p.raised_by for p in pushbacks}
        | {p.resolved_by for p in pushbacks}
        | {a.owner_id for a in areas.values()},
    )
    by_stage = {r.stage: r for r in reviews}
    stages = []
    for s in STAGES:
        review = by_stage.get(s.number)
        owner = users.get(areas[s.area_key].owner_id) if s.area_key in areas else None
        if review is not None:
            state = review.outcome
        elif proposal.status == "pending" and proposal.current_stage == s.number:
            state = "waiting"
        else:
            state = "not_started"
        stages.append(
            {
                "number": s.number,
                "name": s.name,
                "owner": user_view(owner),
                "state": state,
                "note": review.note if review else None,
                "at": review.at.isoformat() if review else None,
            }
        )
    return {
        "id": str(proposal.id),
        "type": proposal.type,
        "title": proposal.title,
        "content": proposal.content,
        "evidence": proposal.evidence,
        "decision_key": proposal.decision_key,
        "status": proposal.status,
        "base_version": proposal.base_version,
        "current_stage": proposal.current_stage,
        "committed_version": proposal.committed_version,
        "proposer": user_view(users.get(proposal.proposer_id)),
        "created_at": proposal.created_at.isoformat(),
        "resolved_at": proposal.resolved_at.isoformat() if proposal.resolved_at else None,
        "stages": stages,
        "pushbacks": [
            {
                "id": str(p.id),
                "reason": p.reason,
                "evidence": p.evidence,
                "raised_by": user_view(users.get(p.raised_by)),
                "outcome": p.outcome,
                "note": p.note,
                "resolved_by": user_view(users.get(p.resolved_by)),
                "created_at": p.created_at.isoformat(),
            }
            for p in pushbacks
        ],
    }
