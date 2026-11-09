"""Org isolation in the database, the permission matrix, the audit log's append-only rule, and
metering with the spending cap."""

import uuid
from types import SimpleNamespace

import psycopg
import pytest
from sqlalchemy import select, update

from app.authz import allowed
from app.db import make_sessionmaker
from app.llm.gateway import RecordedGateway
from app.models import AuditLog, Event, Member, Org, Space, UsageRecord, User
from tests.conftest import libpq_url
from tests.fakes import FakeGitHub, pr_event, recorded, signed

OTHER_ORG = uuid.uuid4()


@pytest.fixture
async def two_orgs(seeded_v3, engine):
    """Acme Pay (seeded) plus Globex, with one person and one space."""
    async with make_sessionmaker(engine)() as s, s.begin():
        s.add(Org(id=OTHER_ORG, name="Globex"))
        await s.flush()
        hank = User(
            org_id=OTHER_ORG, email="hank@globex.example", name="Hank", api_token="dev-hank"
        )
        s.add(hank)
        await s.flush()
        globex = Space(org_id=OTHER_ORG, handle="globex-launch", name="Launch", created_by=hank.id)
        s.add(globex)
        await s.flush()
        s.add(Member(space_id=globex.id, user_id=hank.id, role="admin"))
    return seeded_v3


def api_conn(test_api_database_url: str) -> psycopg.Connection:
    return psycopg.connect(libpq_url(test_api_database_url))


def acting_for(conn: psycopg.Connection, org: uuid.UUID | None) -> None:
    conn.execute("SELECT set_config('tenet.org_id', %s, true)", (str(org) if org else "",))


async def test_raw_sql_as_the_api_role_sees_only_its_org(two_orgs, test_api_database_url):
    acme = two_orgs.space.id
    with api_conn(test_api_database_url) as conn:
        acting_for(conn, OTHER_ORG)
        spaces = [r[0] for r in conn.execute("SELECT handle FROM spaces")]
        events = conn.execute("SELECT count(*) FROM events WHERE space_id = %s", (acme,)).fetchone()
        proposals = conn.execute("SELECT count(*) FROM proposals").fetchone()
        people = [r[0] for r in conn.execute("SELECT email FROM users")]
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute(
                "INSERT INTO findings (id, space_id, author_id, text, evidence, mentions, status) "
                "VALUES (gen_random_uuid(), %s, %s, 'x', '[]', '[]', 'open')",
                (acme, two_orgs.users["maya"].id),
            )
        conn.rollback()

        acting_for(conn, None)
        nothing = conn.execute("SELECT count(*) FROM spaces").fetchone()
        conn.rollback()

        acting_for(conn, two_orgs.org.id)
        acme_events = conn.execute("SELECT count(*) FROM events").fetchone()

    assert spaces == ["globex-launch"]
    assert events == (0,) and proposals == (0,)
    assert people == ["hank@globex.example"]
    assert nothing == (0,)  # no org set: org tables look empty
    assert acme_events[0] > 0


async def test_lookups_reveal_only_an_org_id(two_orgs, test_api_database_url):
    with api_conn(test_api_database_url) as conn:
        assert conn.execute("SELECT tenet_token_org('dev-hank')").fetchone() == (OTHER_ORG,)
        assert conn.execute("SELECT tenet_token_org('nope')").fetchone() == (None,)
        assert conn.execute("SELECT tenet_repo_org('acme-pay/payments-service')").fetchone() == (
            two_orgs.org.id,
        )


async def test_api_cannot_reach_another_orgs_space(two_orgs, app_factory):
    async with app_factory() as (_, client):
        hank = {"Authorization": "Bearer dev-hank"}
        theirs = await client.get("/api/spaces/payments-redesign", headers=hank)
        state = await client.get("/api/spaces/payments-redesign/state", headers=hank)
        mine = await client.get("/api/spaces/globex-launch", headers=hank)
        taken = await client.post(
            "/api/spaces",
            json={"handle": "payments-redesign", "name": "Copy"},
            headers={**hank, "X-Tenet-CSRF": "1"},
        )
        people = await client.get("/api/users", headers=hank)

    assert theirs.status_code == 404 and state.status_code == 404
    assert mine.status_code == 200
    assert taken.status_code == 409
    assert [p["name"] for p in people.json()] == ["Hank"]


async def test_audit_log_is_append_only(seeded_v3, db_conn):
    db_conn.execute(
        "INSERT INTO audit_log (id, action, subject, outcome, reason, ip, user_agent, details) "
        "VALUES (gen_random_uuid(), 'auth.sign_in', 'x', 'success', '', '', '', '{}')"
    )
    for statement in (
        "UPDATE audit_log SET reason = 'edited'",
        "DELETE FROM audit_log",
        "TRUNCATE audit_log",
    ):
        with pytest.raises(psycopg.errors.RestrictViolation, match="append-only"):
            db_conn.execute(statement)


# --- the permission matrix ---------------------------------------------------------------------


class RoleSession:
    def __init__(self, role: str | None) -> None:
        self.role = role

    async def scalar(self, _query):
        return self.role


ORG = uuid.uuid4()
SPACE = SimpleNamespace(id=uuid.uuid4(), org_id=ORG, handle="s")
# action -> roles allowed (admin, owner, member, viewer, guest, none)
EXPECTED = {
    "space.read": "admin owner member viewer guest",
    "ask": "admin owner member viewer guest",
    "proposal.create": "admin owner member",
    "finding.share": "admin owner member",
    "finding.reply": "admin owner member",
    "item.add": "admin owner member",
    "member.manage": "admin",
}


@pytest.mark.parametrize("action", EXPECTED)
@pytest.mark.parametrize("role", ["admin", "owner", "member", "viewer", "guest", None])
async def test_space_matrix(action, role) -> None:
    user = SimpleNamespace(
        id=uuid.uuid4(), org_id=ORG, active=True, external=False, is_org_admin=False
    )
    assert await allowed(RoleSession(role), user, action, SPACE) == (
        role is not None and role in EXPECTED[action].split()
    )


@pytest.mark.parametrize(
    ("who", "action", "ok"),
    [
        ({}, "space.create", True),
        ({}, "org.directory", True),
        ({}, "org.admin", False),
        ({"is_org_admin": True}, "audit.read", True),
        ({"is_org_admin": True}, "usage.read", True),
        ({"external": True}, "space.create", False),
        ({"external": True}, "org.directory", False),
        ({"external": True, "is_org_admin": True}, "org.admin", False),
        ({"active": False}, "space.create", False),
    ],
)
async def test_org_matrix(who, action, ok) -> None:
    user = SimpleNamespace(
        **{
            "id": uuid.uuid4(),
            "org_id": ORG,
            "active": True,
            "external": False,
            "is_org_admin": False,
            **who,
        }
    )
    assert await allowed(RoleSession(None), user, action) is ok


async def test_no_access_across_orgs_whatever_the_role() -> None:
    stranger = SimpleNamespace(
        id=uuid.uuid4(), org_id=uuid.uuid4(), active=True, external=False, is_org_admin=True
    )
    assert not await allowed(RoleSession("admin"), stranger, "space.read", SPACE)


async def test_org_admin_manages_members_but_reads_nothing_without_a_role() -> None:
    admin = SimpleNamespace(
        id=uuid.uuid4(), org_id=ORG, active=True, external=False, is_org_admin=True
    )
    assert await allowed(RoleSession(None), admin, "member.manage", SPACE)
    assert not await allowed(RoleSession(None), admin, "space.read", SPACE)


# --- metering and the spending cap ---------------------------------------------------------------


async def test_model_calls_are_metered_per_org(seeded_v4, engine, app_factory):
    llm = RecordedGateway({"ask": [{"answer": "D-014 is agreed at v4.", "cited": ["D-014"]}]})
    async with app_factory(llm=llm) as (_, client):
        answer = await client.post(
            "/api/spaces/payments-redesign/ask",
            json={"question": "where are we?"},
            headers={"Authorization": "Bearer dev-maya"},
        )
        usage = (
            await client.get("/api/admin/usage", headers={"Authorization": "Bearer dev-yashwant"})
        ).json()

    assert answer.status_code == 200
    async with make_sessionmaker(engine)() as s:
        [row] = (await s.scalars(select(UsageRecord))).all()
    assert (row.org_id, row.task) == (seeded_v4.org.id, "ask")
    assert usage["cap_usd"] == 50.0 and usage["by_task"][0]["calls"] == 1


def test_cost_estimate() -> None:
    from decimal import Decimal

    from app.llm.metering import cost_of

    assert cost_of("claude-opus-5-5", 1_000_000, 100_000) == Decimal("6")
    assert cost_of("claude-haiku-5-5", 2_000_000, 0) == Decimal("0.2")


async def test_spending_cap_stops_calls_and_the_pr_check_fails_open(seeded_v4, engine, app_factory):
    async with make_sessionmaker(engine)() as s, s.begin():
        await s.execute(update(Org).values(monthly_cap_usd=0))
    github = FakeGitHub()
    llm = recorded(pr_analyzer=["pr_291_analyzer.json"])
    async with app_factory(github=github, llm=llm) as (_, client):
        raw, headers = signed(pr_event(291), "pull_request", "cap-1")
        await client.post("/webhooks/github", content=raw, headers=headers)
        ask = await client.post(
            "/api/spaces/payments-redesign/ask",
            json={"question": "where are we?"},
            headers={"Authorization": "Bearer dev-maya"},
        )

    [run] = github.check_runs
    assert run["conclusion"] == "neutral"
    assert llm.calls == []  # never reached the model
    assert ask.status_code == 502


async def test_events_written_through_the_api_stay_in_their_org(two_orgs, engine, app_factory):
    async with app_factory() as (_, client):
        await client.post(
            "/api/spaces/globex-launch/items",
            json={"url": "https://globex.atlassian.net/browse/GX-1", "title": "GX-1"},
            headers={"Authorization": "Bearer dev-hank"},
        )
    async with make_sessionmaker(engine)() as s:
        globex = await s.scalar(select(Space).where(Space.handle == "globex-launch"))
        [linked] = (await s.scalars(select(Event).where(Event.space_id == globex.id))).all()
        rows = (await s.scalars(select(AuditLog))).all()
    assert linked.type == "item.linked"
    assert all(r.org_id in (None, OTHER_ORG, two_orgs.org.id) for r in rows)
