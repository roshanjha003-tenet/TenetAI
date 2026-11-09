import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.events import list_events
from app.models import Member, Proposal, ProposalReview
from app.seed import D014, seed
from app.steward import read_version


async def test_seed_through_v3(session: AsyncSession) -> None:
    result = await seed(session)

    assert result.space.handle == "payments-redesign"
    assert result.space.head_version == 3
    v1, v2, v3 = [await read_version(session, result.space.id, v) for v in (1, 2, 3)]
    assert v1.snapshot == {"decisions": {}}
    assert list(v2.snapshot["decisions"]) == ["D-012"]
    assert list(v3.snapshot["decisions"]) == ["D-012", "D-013"]
    assert [v.parent_version for v in (v1, v2, v3)] == [None, 1, 2]
    assert v3.snapshot["decisions"]["D-013"]["approved_by"][0]["name"] == "Maya Chen"

    types = [e.type for e in await list_events(session, result.space.id)]
    assert types.count("item.linked") == 3
    assert types.count("state.committed") == 3
    assert types.count("decision.created") == 2

    members = (
        await session.scalars(select(Member).where(Member.space_id == result.space.id))
    ).all()
    assert len(members) == 4
    assert result.areas["product-scope"].owner_id == result.users["maya"].id
    assert result.areas["technical-safety"].owner_id == result.users["arjun"].id


async def test_seed_through_v4_approves_d014_in_two_stages(session: AsyncSession) -> None:
    result = await seed(session, through=4)

    assert result.space.head_version == 4
    d014 = (await read_version(session, result.space.id)).snapshot["decisions"]["D-014"]
    assert d014["constraints"] == D014["constraints"]
    assert d014["parents"] == ["D-013"]
    assert [a["name"] for a in d014["approved_by"]] == ["Maya Chen", "Arjun Rao"]
    assert [a["stage"] for a in d014["approved_by"]] == ["product scope", "technical safety"]

    proposal = (await session.scalars(select(Proposal))).one()
    assert (proposal.status, proposal.base_version, proposal.committed_version) == (
        "approved",
        3,
        4,
    )
    reviews = (await session.scalars(select(ProposalReview).order_by(ProposalReview.stage))).all()
    assert [r.stage_name for r in reviews] == ["product scope", "technical safety"]


async def test_seed_refuses_to_run_twice(session: AsyncSession) -> None:
    await seed(session)
    with pytest.raises(RuntimeError, match="already exists"):
        await seed(session)
