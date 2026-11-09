"""Proposals and the fixed two-stage review: product scope, then technical safety.

A proposal changes nothing until both stage owners approve. Final approval puts it on the space
queue; the State steward then commits it. If HEAD moved since the proposal was written, the
steward re-checks: no conflict -> apply on the new HEAD; conflict -> back to the owner (blocked).
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.events import append_event
from app.models import (
    Area,
    Decision,
    Member,
    Proposal,
    ProposalReview,
    Pushback,
    Space,
    StateVersion,
    StewardJob,
    User,
)
from app.steward import (
    Approval,
    DecisionChange,
    StaleBaseVersion,
    commit,
    commit_decision,
)


@dataclass(frozen=True)
class Stage:
    number: int
    name: str
    area_key: str


STAGES = (
    Stage(1, "product scope", "product-scope"),
    Stage(2, "technical safety", "technical-safety"),
)
MVP_TYPES = ("decision", "revision", "status")
WRITER_ROLES = ("admin", "owner", "member")
MAX_CONSTRAINT_CHARS = 200


class ReviewError(Exception):
    status_code = 422


class Forbidden(ReviewError):
    status_code = 403


class NotFound(ReviewError):
    status_code = 404


class Conflict(ReviewError):
    status_code = 409


@dataclass
class Notice:
    """Something to tell people after the transaction commits (Slack, in milestone 7)."""

    kind: str  # proposal_created | review_requested | pushback_raised | state_updated | blocked
    #           | finding_shared | finding_reply
    proposal_id: uuid.UUID | None
    user_ids: list[uuid.UUID] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)
    finding_id: uuid.UUID | None = None


def now() -> datetime:
    return datetime.now(UTC)


async def require(session: AsyncSession, user: User, action: str, space: Space) -> None:
    """The permission matrix lives in app.authz (imported here: authz imports this module)."""
    from app.authz import require as matrix

    await matrix(session, user, action, space)


async def area(session: AsyncSession, space: Space, key: str) -> Area:
    found = await session.scalar(select(Area).where(Area.space_id == space.id, Area.key == key))
    if found is None:
        raise ReviewError(f"@{space.handle} has no area '{key}'")
    return found


async def stage_owner(session: AsyncSession, space: Space, stage: Stage) -> User:
    return await session.get(User, (await area(session, space, stage.area_key)).owner_id)


async def head_snapshot(session: AsyncSession, space: Space) -> dict[str, Any]:
    head = await session.get(StateVersion, (space.id, space.head_version))
    return head.snapshot if head else {"decisions": {}}


async def next_decision_key(session: AsyncSession, space: Space) -> str:
    keys = list(await session.scalars(select(Decision.key).where(Decision.space_id == space.id)))
    keys += [
        k
        for k in await session.scalars(
            select(Proposal.decision_key).where(
                Proposal.space_id == space.id, Proposal.decision_key.is_not(None)
            )
        )
    ]
    highest = max((int(k.split("-")[1]) for k in keys), default=0)
    return f"D-{highest + 1:03d}"


def clean_decision_content(content: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    statement = str(content.get("statement", "")).strip()
    if not statement:
        raise ReviewError("a decision needs a statement")
    constraints = [str(c).strip() for c in content.get("constraints", []) if str(c).strip()]
    too_long = [c for c in constraints if len(c) > MAX_CONSTRAINT_CHARS]
    if too_long:
        raise ReviewError(f"constraints are short must / must-not lines: '{too_long[0][:40]}…'")
    parents = [str(p).strip().upper() for p in content.get("parents", [])]
    decisions = snapshot.get("decisions", {})
    unknown = [p for p in parents if p not in decisions]
    if unknown:
        raise ReviewError(f"parent {unknown[0]} is not an agreed decision")
    abandoned = [p for p in parents if decisions[p].get("status") == "abandoned"]
    if abandoned:
        raise ReviewError(f"parent {abandoned[0]} was abandoned")
    return {
        **content,
        "statement": statement,
        "constraints": constraints,
        "parents": parents,
        "area": str(content.get("area", "")).strip(),
    }


async def create_proposal(
    session: AsyncSession,
    *,
    space: Space,
    proposer: User,
    type: str,
    title: str,
    content: dict[str, Any],
    base_version: int,
    evidence: list[dict[str, Any]] | None = None,
    decision_key: str | None = None,
    caused_by: uuid.UUID | None = None,
) -> tuple[Proposal, list[Notice]]:
    await require(session, proposer, "proposal.create", space)
    if type not in MVP_TYPES:
        raise ReviewError(f"'{type}' proposals aren't part of the MVP")
    title = title.strip()
    if not title:
        raise ReviewError("a proposal needs a title")
    if not 1 <= base_version <= space.head_version:
        raise ReviewError(f"base version must be between 1 and HEAD (v{space.head_version})")

    snapshot = await head_snapshot(session, space)
    if type in ("decision", "revision"):
        content = clean_decision_content(content, snapshot)
        await area(session, space, content["area"])
        if type == "decision":
            decision_key = await next_decision_key(session, space)
        else:
            decision_key = (decision_key or "").strip().upper()
            if decision_key not in snapshot.get("decisions", {}):
                raise ReviewError(f"{decision_key or 'a revision'} must name an agreed decision")
    else:
        text = str(content.get("text", "")).strip()
        if not text:
            raise ReviewError("a status update needs text")
        content, decision_key = {**content, "text": text}, None

    proposal = Proposal(
        space_id=space.id,
        type=type,
        title=title,
        content=content,
        evidence=evidence or [],
        base_version=base_version,
        decision_key=decision_key,
        proposer_id=proposer.id,
    )
    session.add(proposal)
    await session.flush()
    await append_event(
        session,
        space_id=space.id,
        type="proposal.created",
        actor_id=proposer.id,
        target_kind="proposal",
        target_id=str(proposal.id),
        caused_by=caused_by,
        payload={
            "type": type,
            "title": title,
            "decision": decision_key,
            "base_version": base_version,
        },
        idempotency_key=f"proposal:{proposal.id}:created",
    )
    first = await stage_owner(session, space, STAGES[0])
    members = list(await session.scalars(select(Member.user_id).where(Member.space_id == space.id)))
    return proposal, [
        Notice("proposal_created", proposal.id, members),
        Notice("review_requested", proposal.id, [first.id], {"stage": STAGES[0].name}),
    ]


async def get_pending(session: AsyncSession, proposal_id: uuid.UUID) -> tuple[Proposal, Space]:
    proposal = await session.get(Proposal, proposal_id, with_for_update=True)
    if proposal is None:
        raise NotFound("no such proposal")
    if proposal.status != "pending":
        raise Conflict(f"this proposal is {proposal.status}")
    return proposal, await session.get(Space, proposal.space_id)


async def open_pushbacks(session: AsyncSession, proposal: Proposal) -> list[Pushback]:
    return list(
        await session.scalars(
            select(Pushback).where(Pushback.proposal_id == proposal.id, Pushback.outcome.is_(None))
        )
    )


async def approve(
    session: AsyncSession, *, proposal_id: uuid.UUID, reviewer: User, note: str = ""
) -> list[Notice]:
    proposal, space = await get_pending(session, proposal_id)
    stage = STAGES[proposal.current_stage - 1]
    owner = await stage_owner(session, space, stage)
    if reviewer.id != owner.id:
        raise Forbidden(f"stage {stage.number} ({stage.name}) is {owner.name}'s to approve")
    note = note.strip()
    pushbacks = await open_pushbacks(session, proposal)
    if pushbacks and not note:
        raise ReviewError("approving over open pushbacks needs a one-line reason")
    for pushback in pushbacks:
        await settle_pushback(session, space, pushback, reviewer, "overruled", note)

    session.add(
        ProposalReview(
            proposal_id=proposal.id,
            stage=stage.number,
            stage_name=stage.name,
            reviewer_id=reviewer.id,
            outcome="approved",
            note=note,
        )
    )
    await append_event(
        session,
        space_id=space.id,
        type="proposal.approved",
        actor_id=reviewer.id,
        target_kind="proposal",
        target_id=str(proposal.id),
        payload={"stage": stage.number, "stage_name": stage.name, "note": note},
        idempotency_key=f"proposal:{proposal.id}:stage{stage.number}:approved",
    )
    if stage.number < len(STAGES):
        proposal.current_stage += 1
        following = STAGES[stage.number]
        nxt = await stage_owner(session, space, following)
        await session.flush()
        return [Notice("review_requested", proposal.id, [nxt.id], {"stage": following.name})]

    session.add(StewardJob(space_id=space.id, proposal_id=proposal.id))
    await session.flush()
    return []


async def reject(
    session: AsyncSession, *, proposal_id: uuid.UUID, reviewer: User, reason: str
) -> list[Notice]:
    proposal, space = await get_pending(session, proposal_id)
    stage = STAGES[proposal.current_stage - 1]
    owner = await stage_owner(session, space, stage)
    if reviewer.id != owner.id:
        raise Forbidden(f"stage {stage.number} ({stage.name}) is {owner.name}'s to decide")
    if not reason.strip():
        raise ReviewError("rejecting needs a reason")
    session.add(
        ProposalReview(
            proposal_id=proposal.id,
            stage=stage.number,
            stage_name=stage.name,
            reviewer_id=reviewer.id,
            outcome="rejected",
            note=reason.strip(),
        )
    )
    proposal.status = "rejected"
    proposal.resolved_at = now()
    await append_event(
        session,
        space_id=space.id,
        type="proposal.rejected",
        actor_id=reviewer.id,
        target_kind="proposal",
        target_id=str(proposal.id),
        payload={"stage": stage.number, "reason": reason.strip()},
        idempotency_key=f"proposal:{proposal.id}:rejected",
    )
    await session.flush()
    return [Notice("rejected", proposal.id, [proposal.proposer_id], {"reason": reason.strip()})]


async def raise_pushback(
    session: AsyncSession,
    *,
    proposal_id: uuid.UUID,
    user: User,
    reason: str,
    evidence: list[dict[str, Any]] | None = None,
) -> tuple[Pushback, list[Notice]]:
    proposal, space = await get_pending(session, proposal_id)
    await require(session, user, "pushback.raise", space)
    if not reason.strip():
        raise ReviewError("a pushback needs a reason")
    pushback = Pushback(
        proposal_id=proposal.id, raised_by=user.id, reason=reason.strip(), evidence=evidence or []
    )
    session.add(pushback)
    await session.flush()
    await append_event(
        session,
        space_id=space.id,
        type="pushback.raised",
        actor_id=user.id,
        target_kind="proposal",
        target_id=str(proposal.id),
        payload={"pushback": str(pushback.id), "reason": pushback.reason},
        idempotency_key=f"pushback:{pushback.id}:raised",
    )
    owner = await stage_owner(session, space, STAGES[proposal.current_stage - 1])
    return pushback, [
        Notice(
            "pushback_raised", proposal.id, [owner.id], {"reason": pushback.reason, "by": user.name}
        )
    ]


async def settle_pushback(
    session: AsyncSession, space: Space, pushback: Pushback, user: User, outcome: str, note: str
) -> None:
    pushback.outcome, pushback.note = outcome, note
    pushback.resolved_by, pushback.resolved_at = user.id, now()
    await append_event(
        session,
        space_id=space.id,
        type="pushback.resolved",
        actor_id=user.id,
        target_kind="proposal",
        target_id=str(pushback.proposal_id),
        payload={"pushback": str(pushback.id), "outcome": outcome, "note": note},
        idempotency_key=f"pushback:{pushback.id}:resolved",
    )


async def resolve_pushback(
    session: AsyncSession, *, pushback_id: uuid.UUID, user: User, outcome: str, note: str = ""
) -> None:
    pushback = await session.get(Pushback, pushback_id, with_for_update=True)
    if pushback is None:
        raise NotFound("no such pushback")
    if pushback.outcome is not None:
        raise Conflict(f"this pushback was already {pushback.outcome}")
    proposal, space = await get_pending(session, pushback.proposal_id)
    if outcome not in ("accepted", "overruled", "withdrawn"):
        raise ReviewError("outcome must be accepted, overruled or withdrawn")
    owner = await stage_owner(session, space, STAGES[proposal.current_stage - 1])
    allowed = {owner.id} | ({pushback.raised_by} if outcome == "withdrawn" else set())
    if user.id not in allowed:
        raise Forbidden(f"only {owner.name} can resolve this pushback")
    if outcome == "overruled" and not note.strip():
        raise ReviewError("overruling needs a one-line reason")
    await settle_pushback(session, space, pushback, user, outcome, note.strip())
    await session.flush()


# --- the space queue and the steward ----------------------------------------------------


def changed_decisions(before: dict[str, Any], after: dict[str, Any]) -> set[str]:
    a, b = before.get("decisions", {}), after.get("decisions", {})
    return {k for k in set(a) | set(b) if a.get(k) != b.get(k)}


async def apply_proposal(
    session: AsyncSession, space: Space, proposal: Proposal, base_version: int
) -> StateVersion:
    proposer = await session.get(User, proposal.proposer_id)
    reviews = list(
        await session.scalars(
            select(ProposalReview)
            .where(ProposalReview.proposal_id == proposal.id, ProposalReview.outcome == "approved")
            .order_by(ProposalReview.stage)
        )
    )
    approvals = [
        Approval(await session.get(User, r.reviewer_id), r.stage_name, r.at) for r in reviews
    ]
    last_reviewer = approvals[-1].user.id if approvals else None
    key = f"proposal:{proposal.id}:commit"
    if proposal.type in ("decision", "revision"):
        c = proposal.content
        version, _, _ = await commit_decision(
            session,
            space_id=space.id,
            base_version=base_version,
            decision=DecisionChange(
                key=proposal.decision_key,
                title=proposal.title,
                statement=c["statement"],
                constraints=c["constraints"],
                parents=c["parents"],
                area=await area(session, space, c["area"]),
                proposer=proposer,
                approvals=approvals,
                evidence=proposal.evidence,
            ),
            actor_id=last_reviewer,
            idempotency_key=key,
        )
        return version

    entry = {
        "text": proposal.content["text"],
        "by": proposer.name,
        "at": now().isoformat(),
        "title": proposal.title,
    }

    def change(snapshot: dict[str, Any]) -> dict[str, Any]:
        snapshot["status"] = entry
        return snapshot

    return await commit(
        session,
        space_id=space.id,
        base_version=base_version,
        change=change,
        summary=f"Status: {proposal.title}",
        actor_id=last_reviewer,
        idempotency_key=key,
    )


async def process_queue(session: AsyncSession, space_id: uuid.UUID) -> list[Notice]:
    """Drain one space's lane in order. Each job commits, or is blocked back to its owner."""
    notices: list[Notice] = []
    jobs = list(
        await session.scalars(
            select(StewardJob)
            .where(StewardJob.space_id == space_id, StewardJob.status == "queued")
            .order_by(StewardJob.seq)
            .with_for_update(skip_locked=True)
        )
    )
    for job in jobs:
        space = await session.get(Space, space_id, with_for_update=True, populate_existing=True)
        proposal = await session.get(Proposal, job.proposal_id, with_for_update=True)
        try:
            async with session.begin_nested():
                version = await apply_proposal(session, space, proposal, proposal.base_version)
        except StaleBaseVersion as stale:
            base = await session.get(StateVersion, (space.id, proposal.base_version))
            head = await session.get(StateVersion, (space.id, stale.head_version))
            moved = changed_decisions(base.snapshot, head.snapshot)
            touched = {proposal.decision_key, *proposal.content.get("parents", [])} - {None}
            clash = sorted(moved & touched)
            if clash:
                notices.append(await block(session, space, proposal, job, clash, stale))
                continue
            async with session.begin_nested():
                version = await apply_proposal(session, space, proposal, stale.head_version)
        proposal.status = "approved"
        proposal.committed_version = version.version
        proposal.resolved_at = now()
        job.status, job.done_at = "done", now()
        job.result = {"version": version.version}
        members = list(
            await session.scalars(select(Member.user_id).where(Member.space_id == space.id))
        )
        notices.append(Notice("state_updated", proposal.id, members, {"version": version.version}))
    await session.flush()
    return notices


async def block(
    session: AsyncSession,
    space: Space,
    proposal: Proposal,
    job: StewardJob,
    clash: list[str],
    stale: StaleBaseVersion,
) -> Notice:
    proposal.status = "blocked"
    proposal.resolved_at = now()
    job.status, job.done_at = "blocked", now()
    job.result = {"conflicts_with": clash, "head": stale.head_version}
    await append_event(
        session,
        space_id=space.id,
        type="proposal.blocked",
        target_kind="proposal",
        target_id=str(proposal.id),
        payload={
            "conflicts_with": clash,
            "base_version": proposal.base_version,
            "head_version": stale.head_version,
        },
        idempotency_key=f"proposal:{proposal.id}:blocked",
    )
    owners = [(await stage_owner(session, space, s)).id for s in STAGES]
    return Notice(
        "blocked", proposal.id, [proposal.proposer_id, *owners], {"conflicts_with": clash}
    )


async def queued_count(session: AsyncSession, space_id: uuid.UUID) -> int:
    return await session.scalar(
        select(func.count())
        .select_from(StewardJob)
        .where(StewardJob.space_id == space_id, StewardJob.status == "queued")
    )
