import json

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.db import make_sessionmaker
from app.llm.gateway import RecordedGateway
from app.models import Event, PrivateMessage, Proposal
from app.sessions import as_agent, as_user, tagged_text
from tests.fakes import FIXTURES

SECRET = "Honestly I think Maya will hate the 24h window"
PRIVATE_THINKING = (
    f"{SECRET}, but let's see.\n\n"
    "@payments-redesign proposing: bounded automatic retries for transient payment failures — "
    "at most 3 attempts in 24 hours, one idempotency key per payment reused on every attempt, "
    "hard declines stay on manual recovery, and keep the checkout rollout flag.\n\n"
    "Also need to remember to call the processor rep."
)


def as_(name: str) -> dict[str, str]:
    return {"Authorization": f"Bearer dev-{name}"}


def capture_fixture() -> dict:
    return json.loads((FIXTURES / "llm" / "capture_d014.json").read_text())


async def new_session(client, who="yashwant") -> str:
    created = await client.post(
        "/api/spaces/payments-redesign/sessions", json={"title": "Retries"}, headers=as_(who)
    )
    assert created.status_code == 201, created.text
    return created.json()["id"]


def test_tagged_text_is_only_the_tagged_paragraph() -> None:
    assert tagged_text(PRIVATE_THINKING, "payments-redesign").startswith(
        "@payments-redesign proposing: bounded automatic retries"
    )
    assert SECRET not in tagged_text(PRIVATE_THINKING, "payments-redesign")
    assert tagged_text("email me@payments-redesign.com", "payments-redesign") is None
    assert tagged_text("nothing tagged", "payments-redesign") is None


async def test_private_work_leaves_nothing_in_the_space(seeded_v3, engine, app_factory) -> None:
    llm = RecordedGateway({"private_assistant": [{"text": "Try bounding by attempts and time."}]})
    async with make_sessionmaker(engine)() as s:
        before = len(list(await s.scalars(select(Event.id))))

    async with app_factory(llm=llm) as (_, client):
        sid = await new_session(client)
        sent = await client.post(
            f"/api/sessions/{sid}/messages",
            json={"text": f"{SECRET}. How should we bound retries?"},
            headers=as_("yashwant"),
        )

    assert sent.status_code == 201
    assert sent.json()["shared"] is None
    assert sent.json()["reply"]["text"] == "Try bounding by attempts and time."
    async with make_sessionmaker(engine)() as s:
        assert len(list(await s.scalars(select(Event.id)))) == before


async def test_tagging_shares_only_tagged_text_and_proposes_d014(seeded_v3, engine, app_factory):
    llm = RecordedGateway(
        {
            "router": [{"kind": "decision", "reason": "proposes a retry policy"}],
            "capture": [capture_fixture()],
            "conflict_check": [{"conflicts": []}],
        }
    )
    async with app_factory(llm=llm) as (_, client):
        sid = await new_session(client)
        sent = (
            await client.post(
                f"/api/sessions/{sid}/messages",
                json={"text": PRIVATE_THINKING},
                headers=as_("yashwant"),
            )
        ).json()
        proposal = (
            await client.get(f"/api/proposals/{sent['shared']['proposal_id']}", headers=as_("maya"))
        ).json()

    shared = sent["shared"]
    assert shared["route"] == "decision"
    assert shared["decision_key"] == "D-014" and shared["status"] == "pending"
    assert "dropped parent D-099: not an agreed decision" in shared["notes"]
    assert "review pending" in sent["reply"]["text"] and "Maya Chen" in sent["reply"]["text"]

    assert proposal["content"]["parents"] == ["D-013"]
    assert proposal["content"]["constraints"][1] == (
        "one idempotency key per payment, reused on every attempt"
    )
    assert proposal["stages"][0]["state"] == "waiting"

    # Nothing outside the tagged paragraph reached the space or any model call that acts on it.
    async with make_sessionmaker(engine)() as s:
        payloads = [json.dumps(p) for p in await s.scalars(select(Event.payload))]
        contents = [json.dumps(p) for p in await s.scalars(select(Proposal.content))]
    for blob in payloads + contents + [c["prompt"] for c in llm.calls]:
        assert SECRET not in blob
        assert "processor rep" not in blob
    assert any("bounded automatic retries" in p for p in payloads)


async def test_conflict_with_the_spine_holds_the_proposal(seeded_v3, app_factory) -> None:
    llm = RecordedGateway(
        {
            "capture": [
                {**capture_fixture(), "constraints": ["retries ship without the rollout flag"]}
            ],
            "conflict_check": [
                {
                    "conflicts": [
                        {
                            "decision": "D-013",
                            "explanation": "drops the flag",
                            "constraint": (
                                "new checkout behaviour stays behind the checkout rollout flag"
                            ),
                        },
                        {
                            "decision": "D-013",
                            "constraint": "an invented constraint",
                            "explanation": "x",
                        },
                    ]
                }
            ],
        }
    )
    async with app_factory(llm=llm) as (_, client):
        sid = await new_session(client)
        sent = (
            await client.post(
                f"/api/sessions/{sid}/messages",
                json={"text": "@payments-redesign retries without the flag", "action": "decision"},
                headers=as_("yashwant"),
            )
        ).json()
        proposal = (
            await client.get(f"/api/proposals/{sent['shared']['proposal_id']}", headers=as_("maya"))
        ).json()

    assert proposal["status"] == "blocked"
    assert [c["decision"] for c in proposal["content"]["conflicts"]] == ["D-013"]
    assert "conflicts with an agreed decision" in sent["reply"]["text"]


async def test_status_route_creates_a_status_proposal(seeded_v3, app_factory) -> None:
    llm = RecordedGateway({"router": [{"kind": "status", "reason": "progress"}]})
    async with app_factory(llm=llm) as (_, client):
        sid = await new_session(client, "priya")
        sent = (
            await client.post(
                f"/api/sessions/{sid}/messages",
                json={"text": "@payments-redesign update: QA started on checkout"},
                headers=as_("priya"),
            )
        ).json()

    assert sent["shared"]["route"] == "status"
    assert sent["shared"]["status"] == "pending"


async def test_sessions_are_visible_only_to_their_owner(seeded_v3, app_factory) -> None:
    llm = RecordedGateway({"private_assistant": [{"text": "ok"}]})
    async with app_factory(llm=llm) as (_, client):
        sid = await new_session(client, "yashwant")
        await client.post(
            f"/api/sessions/{sid}/messages", json={"text": SECRET}, headers=as_("yashwant")
        )
        mine = await client.get(f"/api/sessions/{sid}", headers=as_("yashwant"))
        theirs = await client.get(f"/api/sessions/{sid}", headers=as_("maya"))
        listing = await client.get("/api/sessions", headers=as_("maya"))
        post_as_other = await client.post(
            f"/api/sessions/{sid}/messages", json={"text": "hi"}, headers=as_("maya")
        )

    assert [m["text"] for m in mine.json()["messages"]] == [SECRET, "ok"]
    assert theirs.status_code == 404
    assert listing.json() == []
    assert post_as_other.status_code == 404


async def test_database_enforces_privacy(seeded_v3, engine) -> None:
    sessions = make_sessionmaker(engine)
    yashwant, maya = seeded_v3.users["yashwant"], seeded_v3.users["maya"]
    async with as_user(sessions, yashwant.id) as s:
        from app.models import PrivateSession

        ps = PrivateSession(owner_id=yashwant.id, space_id=seeded_v3.space.id, title="t")
        s.add(ps)
        await s.flush()
        s.add(PrivateMessage(session_id=ps.id, owner_id=yashwant.id, role="user", text=SECRET))

    # Another user, through row-level security, sees no rows.
    async with as_user(sessions, maya.id) as s:
        assert list(await s.scalars(select(PrivateMessage))) == []
        # ...and can't write a row claiming to be someone else's.
        with pytest.raises(DBAPIError, match="row-level security"):
            async with s.begin_nested():
                s.add(
                    PrivateMessage(
                        session_id=ps.id, owner_id=yashwant.id, role="user", text="forged"
                    )
                )
                await s.flush()

    # The agents' role can't read private tables at all.
    with pytest.raises(DBAPIError, match="permission denied"):
        async with as_agent(sessions) as s:
            await s.execute(text("SELECT text FROM private_messages"))

    # Without a user set, the app role sees nothing either.
    async with sessions() as s, s.begin():
        await s.execute(text("SET LOCAL ROLE tenet_app"))
        assert list(await s.scalars(select(PrivateMessage))) == []
