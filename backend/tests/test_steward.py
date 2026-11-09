import asyncio
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db import make_sessionmaker
from app.models import Decision, DecisionRevision, Space, StateVersion
from app.steward import (
    Approval,
    DecisionChange,
    StaleBaseVersion,
    commit,
    commit_decision,
    read_version,
)
from tests.factories import make_space


def add_note(text: str):
    def change(snapshot: dict) -> dict:
        snapshot.setdefault("notes", []).append(text)
        return snapshot

    return change


async def test_commit_creates_next_version_with_parent(session: AsyncSession) -> None:
    space, user, _ = await make_space(session)

    v1 = await commit(
        session,
        space_id=space.id,
        base_version=0,
        change=add_note("one"),
        summary="one",
        actor_id=user.id,
        idempotency_key="k1",
    )
    v2 = await commit(
        session,
        space_id=space.id,
        base_version=1,
        change=add_note("two"),
        summary="two",
        actor_id=user.id,
        idempotency_key="k2",
    )

    assert (v1.version, v1.parent_version) == (1, None)
    assert (v2.version, v2.parent_version) == (2, 1)
    assert v2.snapshot["notes"] == ["one", "two"]
    assert (await read_version(session, space.id, 1)).snapshot["notes"] == ["one"]
    assert (await read_version(session, space.id)).version == 2
    assert space.head_version == 2


async def test_commit_rejects_stale_base_and_writes_nothing(session: AsyncSession) -> None:
    space, user, _ = await make_space(session)
    await commit(
        session,
        space_id=space.id,
        base_version=0,
        change=add_note("one"),
        summary="one",
        actor_id=user.id,
        idempotency_key="k1",
    )

    with pytest.raises(StaleBaseVersion) as exc:
        await commit(
            session,
            space_id=space.id,
            base_version=0,
            change=add_note("late"),
            summary="late",
            actor_id=user.id,
            idempotency_key="k2",
        )

    assert (exc.value.base_version, exc.value.head_version) == (0, 1)
    versions = await session.scalar(
        select(func.count()).select_from(StateVersion).where(StateVersion.space_id == space.id)
    )
    assert versions == 1


async def test_concurrent_commits_on_same_base_one_wins(engine: AsyncEngine) -> None:
    sessions = make_sessionmaker(engine)
    async with sessions() as s, s.begin():
        space, user, _ = await make_space(s)

    async def attempt(label: str) -> int:
        async with sessions() as s, s.begin():
            version = await commit(
                s,
                space_id=space.id,
                base_version=0,
                change=add_note(label),
                summary=label,
                actor_id=user.id,
                idempotency_key=label,
            )
            await asyncio.sleep(0.2)  # hold the space lock so the other attempt has to wait
            return version.version

    results = await asyncio.gather(attempt("a"), attempt("b"), return_exceptions=True)

    winners = [r for r in results if isinstance(r, int)]
    losers = [r for r in results if isinstance(r, StaleBaseVersion)]
    assert winners == [1]
    assert len(losers) == 1 and losers[0].head_version == 1
    async with sessions() as s:
        assert (await s.get(Space, space.id)).head_version == 1


async def test_commit_decision_revises_existing_decision(session: AsyncSession) -> None:
    space, user, area = await make_space(session)
    now = datetime.now(UTC)

    def change(statement: str) -> DecisionChange:
        return DecisionChange(
            key="D-001",
            title="Retry policy",
            statement=statement,
            area=area,
            proposer=user,
            approvals=[Approval(user, "core", now)],
            constraints=[statement],
        )

    await commit_decision(
        session,
        space_id=space.id,
        base_version=0,
        decision=change("first"),
        actor_id=user.id,
        idempotency_key="d1",
    )
    version, decision, revision = await commit_decision(
        session,
        space_id=space.id,
        base_version=1,
        decision=change("second"),
        actor_id=user.id,
        idempotency_key="d2",
    )

    assert version.version == 2
    assert decision.current_revision == 2 and revision.revision == 2
    assert version.snapshot["decisions"]["D-001"]["statement"] == "second"
    assert version.snapshot["decisions"]["D-001"]["revision"] == 2
    revisions = await session.scalars(
        select(DecisionRevision.statement)
        .join(Decision)
        .where(Decision.space_id == space.id)
        .order_by(DecisionRevision.revision)
    )
    assert list(revisions) == ["first", "second"]
