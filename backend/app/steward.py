"""State steward: the only writer of agreed state.

One ordered lane per space: `commit` locks the space row, so commits for a space run one at a time,
and it writes a new StateVersion only if the caller's base_version still equals HEAD
(compare-and-swap). Callers own the transaction; nothing here commits it.
"""

import copy
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.events import append_event
from app.models import Area, Decision, DecisionRevision, Space, StateVersion, User

Snapshot = dict[str, Any]


class StaleBaseVersion(Exception):
    def __init__(self, base_version: int, head_version: int) -> None:
        super().__init__(f"base version {base_version} is stale; HEAD is {head_version}")
        self.base_version = base_version
        self.head_version = head_version


class UnknownSpace(Exception):
    pass


def empty_snapshot() -> Snapshot:
    return {"decisions": {}}


async def read_version(
    session: AsyncSession, space_id: uuid.UUID, version: int | None = None
) -> StateVersion | None:
    """Read a StateVersion; None means HEAD. Rewind is reading an older version."""
    if version is None:
        space = await session.get(Space, space_id)
        if space is None:
            raise UnknownSpace(space_id)
        version = space.head_version
    return await session.get(StateVersion, (space_id, version))


async def commit(
    session: AsyncSession,
    *,
    space_id: uuid.UUID,
    base_version: int,
    change: Callable[[Snapshot], Snapshot],
    summary: str,
    actor_id: uuid.UUID | None,
    idempotency_key: str,
    caused_by: uuid.UUID | None = None,
    at: datetime | None = None,
    event_payload: dict[str, Any] | None = None,
) -> StateVersion:
    space = await session.get(Space, space_id, with_for_update=True, populate_existing=True)
    if space is None:
        raise UnknownSpace(space_id)
    head = space.head_version
    if base_version != head:
        raise StaleBaseVersion(base_version, head)

    parent = await session.get(StateVersion, (space_id, head)) if head else None
    snapshot = change(copy.deepcopy(parent.snapshot if parent else empty_snapshot()))
    new_version = head + 1

    event = await append_event(
        session,
        space_id=space_id,
        type="state.committed",
        actor_id=actor_id,
        target_kind="state_version",
        target_id=str(new_version),
        target_revision=new_version,
        payload={"summary": summary, "parent_version": head or None, **(event_payload or {})},
        caused_by=caused_by,
        idempotency_key=idempotency_key,
        at=at,
    )
    version = StateVersion(
        space_id=space_id,
        version=new_version,
        parent_version=head or None,
        snapshot=snapshot,
        summary=summary,
        committed_by=actor_id,
        event_id=event.id,
    )
    if at is not None:
        version.created_at = at
    session.add(version)
    space.head_version = new_version
    await session.flush()
    return version


@dataclass
class Approval:
    user: User
    stage: str
    at: datetime


@dataclass
class DecisionChange:
    key: str
    title: str
    statement: str
    area: Area
    proposer: User
    approvals: list[Approval]
    constraints: list[str] = field(default_factory=list)
    parents: list[str] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)


async def commit_decision(
    session: AsyncSession,
    *,
    space_id: uuid.UUID,
    base_version: int,
    decision: DecisionChange,
    actor_id: uuid.UUID | None,
    idempotency_key: str,
    caused_by: uuid.UUID | None = None,
    at: datetime | None = None,
) -> tuple[StateVersion, Decision, DecisionRevision]:
    """Commit a new decision, or the next revision of an existing one, as the next StateVersion."""
    existing = (
        await session.execute(
            select(Decision).where(Decision.space_id == space_id, Decision.key == decision.key)
        )
    ).scalar_one_or_none()
    revision = existing.current_revision + 1 if existing else 1
    approvals = [
        {"user_id": str(a.user.id), "name": a.user.name, "stage": a.stage, "at": a.at.isoformat()}
        for a in decision.approvals
    ]
    entry = {
        "key": decision.key,
        "title": decision.title,
        "statement": decision.statement,
        "constraints": list(decision.constraints),
        "parents": list(decision.parents),
        "area": decision.area.key,
        "status": "active",
        "revision": revision,
        "proposer": decision.proposer.name,
        "approved_by": approvals,
    }

    def change(snapshot: Snapshot) -> Snapshot:
        snapshot.setdefault("decisions", {})[decision.key] = entry
        return snapshot

    version = await commit(
        session,
        space_id=space_id,
        base_version=base_version,
        change=change,
        summary=f"{decision.key}: {decision.title}",
        actor_id=actor_id,
        idempotency_key=idempotency_key,
        caused_by=caused_by,
        at=at,
        event_payload={"decision": decision.key, "revision": revision},
    )

    if existing is None:
        existing = Decision(
            space_id=space_id,
            key=decision.key,
            area_id=decision.area.id,
            title=decision.title,
            current_revision=revision,
            status="active",
        )
        if at is not None:
            existing.created_at = at
        session.add(existing)
        await session.flush()
    else:
        existing.current_revision = revision
        existing.title = decision.title
        existing.status = "active"

    rev = DecisionRevision(
        decision_id=existing.id,
        revision=revision,
        statement=decision.statement,
        constraints=list(decision.constraints),
        parents=list(decision.parents),
        evidence=list(decision.evidence),
        proposer_id=decision.proposer.id,
        approvals=approvals,
        state_version=version.version,
    )
    if at is not None:
        rev.created_at = at
    session.add(rev)

    await append_event(
        session,
        space_id=space_id,
        type="decision.created" if revision == 1 else "decision.revised",
        actor_id=actor_id,
        target_kind="decision",
        target_id=decision.key,
        target_revision=revision,
        payload={"title": decision.title, "state_version": version.version},
        caused_by=version.event_id,
        idempotency_key=f"{idempotency_key}:decision",
        at=at,
    )
    await session.flush()
    return version, existing, rev
