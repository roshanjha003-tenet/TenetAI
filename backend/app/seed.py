"""Seed the demo: Acme Pay, four people, @payments-redesign at v3 (optionally through v4).

uv run python -m app.seed                # v3: D-012, D-013
uv run python -m app.seed --through 4    # v4: D-014 approved by Maya, then Arjun
uv run python -m app.seed --reset        # rebuild the schema first (events can't be deleted)
"""

import argparse
import asyncio
import hashlib
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from alembic import command
from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import REPO_ROOT, get_settings
from app.db import make_engine, make_sessionmaker
from app.events import append_event
from app.models import (
    Area,
    Item,
    Member,
    Org,
    OrgDomain,
    Proposal,
    ProposalReview,
    Repo,
    Space,
    User,
)
from app.steward import Approval, DecisionChange, commit, commit_decision

TZ = ZoneInfo("Asia/Kolkata")
SPACE_HANDLE = "payments-redesign"
# The GitHub repo whose PRs are checked against @payments-redesign. Override for a live demo,
# e.g. TENET_DEMO_REPO=yyadav1120/payments-service, so the GitHub App's webhooks match.
REPO = os.environ.get("TENET_DEMO_REPO", "acme-pay/payments-service")


def at(day: int, hour: int, minute: int) -> datetime:
    return datetime(2026, 10, day, hour, minute, tzinfo=TZ)


PEOPLE = [
    # key, name, email, title, github login
    ("yashwant", "Yashwant", "yashwant@acmepay.dev", "Founder", "yashwant-acme"),
    ("maya", "Maya Chen", "maya@acmepay.dev", "Product lead · product scope owner", "maya-acme"),
    (
        "arjun",
        "Arjun Rao",
        "arjun@acmepay.dev",
        "Payments engineering · technical safety owner",
        "arjun-acme",
    ),
    ("priya", "Priya Nair", "priya@acmepay.dev", "Engineer, payments", "priya-acme"),
]

ITEMS = [
    (
        "jira",
        "https://acmepay.atlassian.net/browse/PAY-142",
        "PAY-142 · Recover failed checkout payments",
        "Roughly 4% of checkout payments fail on the first attempt. Most are transient processor "
        "errors (timeouts, 'try again later'). Support recovers them by hand today, which takes "
        "about a day per payment.",
    ),
    (
        "notion",
        "https://www.notion.so/acmepay/Payment-retry-policy-v2",
        "Payment retry policy v2",
        "Transient failures may be retried a small number of times. Every attempt for a payment "
        "must carry the same idempotency key so the processor can never charge a customer twice. "
        "Hard declines (insufficient funds, stolen card) are never retried.",
    ),
    (
        "slack",
        "https://acmepay.slack.com/archives/C0PAYMENTS",
        "#payments",
        "Arjun: if we retry, the key has to be per payment, not per attempt. Maya: fine, as long "
        "as it ships behind the checkout flag and doesn't move Oct 23.",
    ),
]

D012 = dict(
    key="D-012",
    title="Failed payments stay on a manual recovery path",
    statement="Payments that fail at checkout go to the manual recovery queue, where support "
    "reviews and recovers them.",
    constraints=[
        "failed payments land in the manual recovery queue",
        "support can see every failed attempt for a payment",
    ],
    parents=[],
)
D013 = dict(
    key="D-013",
    title="Checkout ships behind a rollout flag; keep the Oct 23 target",
    statement="The redesigned checkout ships behind the checkout rollout flag, and the Oct 23 "
    "target date stays.",
    constraints=[
        "new checkout behaviour stays behind the checkout rollout flag",
        "the target date stays Oct 23",
    ],
    parents=[],
)
D014 = dict(
    key="D-014",
    title="Enable bounded automatic retries for transient payment failures",
    statement="Transient payment failures are retried automatically, within strict bounds; "
    "everything else stays on the manual recovery path.",
    constraints=[
        "at most 3 automatic attempts within 24 hours",
        "one idempotency key per payment, reused on every attempt",
        "hard declines are never retried; they stay on the manual recovery path",
        "retries stay behind the checkout rollout flag",
    ],
    parents=["D-013"],
)
D014_TAGGED_TEXT = (
    "@payments-redesign proposing: bounded automatic retries for transient payment failures"
)


@dataclass
class SeedResult:
    org: Org
    space: Space
    users: dict[str, User]
    areas: dict[str, Area]


def stable_id(name: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"tenet-seed:{name}")


async def seed(session: AsyncSession, through: int = 3) -> SeedResult:
    if through not in (3, 4):
        raise ValueError("through must be 3 or 4")
    existing = (
        await session.execute(select(Space).where(Space.handle == SPACE_HANDLE))
    ).scalar_one_or_none()
    if existing is not None:
        raise RuntimeError(f"@{SPACE_HANDLE} already exists; run with --reset")

    org = Org(id=stable_id("org"), name="Acme Pay")
    session.add(org)
    users: dict[str, User] = {}
    for key, name, email, title, gh in PEOPLE:
        users[key] = User(
            id=stable_id(f"user:{key}"),
            org_id=org.id,
            email=email,
            name=name,
            title=title,
            api_token=f"dev-{key}",
            github_login=gh,
            is_org_admin=key == "yashwant",
        )
    session.add_all(users.values())
    # Acme Pay's verified domain: anyone @acmepay.dev who signs in with Google joins the org.
    session.add(
        OrgDomain(
            domain="acmepay.dev",
            org_id=org.id,
            verification_token="seeded",
            verified_at=datetime(2026, 10, 17, tzinfo=UTC),
        )
    )
    await session.flush()

    yashwant, maya, arjun = users["yashwant"], users["maya"], users["arjun"]
    space = Space(
        id=stable_id("space"),
        org_id=org.id,
        handle=SPACE_HANDLE,
        name="Payments redesign",
        goal="Ship the redesigned checkout, with payment recovery, by Oct 23.",
        created_by=yashwant.id,
        created_at=at(16, 10, 0),
    )
    session.add(space)
    await session.flush()

    areas = {
        "product-scope": Area(
            space_id=space.id, key="product-scope", name="Product scope", owner_id=maya.id
        ),
        "technical-safety": Area(
            space_id=space.id, key="technical-safety", name="Technical safety", owner_id=arjun.id
        ),
    }
    session.add_all(areas.values())
    session.add(Repo(space_id=space.id, full_name=REPO))
    roles = {"yashwant": "admin", "maya": "owner", "arjun": "owner", "priya": "member"}
    session.add_all(
        Member(space_id=space.id, user_id=users[k].id, role=r, added_at=at(16, 10, 0))
        for k, r in roles.items()
    )
    await session.flush()

    created = await append_event(
        session,
        space_id=space.id,
        type="space.created",
        actor_id=yashwant.id,
        target_kind="space",
        target_id=SPACE_HANDLE,
        idempotency_key="seed:space",
        payload={"name": space.name, "goal": space.goal},
        at=at(16, 10, 0),
    )
    v1 = await commit(
        session,
        space_id=space.id,
        base_version=0,
        change=lambda s: s,
        summary="Space created",
        actor_id=yashwant.id,
        idempotency_key="seed:v1",
        caused_by=created.id,
        at=at(16, 10, 0),
    )
    for i, (kind, url, title, excerpt) in enumerate(ITEMS):
        item = Item(
            space_id=space.id,
            kind=kind,
            url=url,
            title=title,
            excerpt=excerpt,
            content_hash=hashlib.sha256(excerpt.encode()).hexdigest(),
            added_by=yashwant.id,
            added_at=at(16, 10, 5 + i),
        )
        session.add(item)
        await session.flush()
        await append_event(
            session,
            space_id=space.id,
            type="item.linked",
            actor_id=yashwant.id,
            target_kind="item",
            target_id=str(item.id),
            idempotency_key=f"seed:item:{kind}",
            payload={"kind": kind, "title": title, "url": url},
            at=at(16, 10, 5 + i),
        )

    v2, _, _ = await commit_decision(
        session,
        space_id=space.id,
        base_version=v1.version,
        decision=DecisionChange(
            **D012,
            area=areas["technical-safety"],
            proposer=arjun,
            approvals=[Approval(arjun, "technical safety", at(17, 15, 30))],
            evidence=[{"kind": "jira", "title": "PAY-142"}],
        ),
        actor_id=arjun.id,
        idempotency_key="seed:v2",
        at=at(17, 15, 30),
    )
    v3, _, _ = await commit_decision(
        session,
        space_id=space.id,
        base_version=v2.version,
        decision=DecisionChange(
            **D013,
            area=areas["product-scope"],
            proposer=maya,
            approvals=[Approval(maya, "product scope", at(18, 16, 10))],
            evidence=[{"kind": "slack", "title": "#payments"}],
        ),
        actor_id=maya.id,
        idempotency_key="seed:v3",
        at=at(18, 16, 10),
    )

    if through == 4:
        await seed_d014_approved(session, space, users, areas, base_version=v3.version)
    await session.flush()
    return SeedResult(org=org, space=space, users=users, areas=areas)


async def seed_d014_approved(
    session: AsyncSession,
    space: Space,
    users: dict[str, User],
    areas: dict[str, Area],
    base_version: int,
) -> None:
    yashwant, maya, arjun = users["yashwant"], users["maya"], users["arjun"]
    proposal = Proposal(
        space_id=space.id,
        type="decision",
        title=D014["title"],
        decision_key="D-014",
        content={
            "statement": D014["statement"],
            "constraints": D014["constraints"],
            "parents": D014["parents"],
            "area": "technical-safety",
            "tagged_text": D014_TAGGED_TEXT,
        },
        evidence=[{"kind": "notion", "title": "Payment retry policy v2"}],
        base_version=base_version,
        proposer_id=yashwant.id,
        created_at=at(20, 11, 5),
    )
    session.add(proposal)
    await session.flush()
    created = await append_event(
        session,
        space_id=space.id,
        type="proposal.created",
        actor_id=yashwant.id,
        target_kind="proposal",
        target_id=str(proposal.id),
        idempotency_key="seed:d014:proposed",
        payload={"decision": "D-014", "title": D014["title"]},
        at=at(20, 11, 5),
    )
    reviews = [
        (1, "product scope", maya, at(20, 14, 20), "In scope for Oct 23 as long as it's flagged."),
        (
            2,
            "technical safety",
            arjun,
            at(21, 9, 40),
            "Key per payment, not per attempt. Approved.",
        ),
    ]
    last = created
    for stage, name, reviewer, when, note in reviews:
        session.add(
            ProposalReview(
                proposal_id=proposal.id,
                stage=stage,
                stage_name=name,
                reviewer_id=reviewer.id,
                outcome="approved",
                note=note,
                at=when,
            )
        )
        last = await append_event(
            session,
            space_id=space.id,
            type="proposal.approved",
            actor_id=reviewer.id,
            target_kind="proposal",
            target_id=str(proposal.id),
            idempotency_key=f"seed:d014:stage{stage}",
            caused_by=last.id,
            payload={"stage": stage, "stage_name": name, "note": note},
            at=when,
        )
    v4, _, _ = await commit_decision(
        session,
        space_id=space.id,
        base_version=base_version,
        decision=DecisionChange(
            **D014,
            area=areas["technical-safety"],
            proposer=yashwant,
            approvals=[
                Approval(maya, "product scope", at(20, 14, 20)),
                Approval(arjun, "technical safety", at(21, 9, 40)),
            ],
            evidence=[{"kind": "notion", "title": "Payment retry policy v2"}],
        ),
        actor_id=arjun.id,
        idempotency_key="seed:v4",
        caused_by=last.id,
        at=at(21, 9, 40),
    )
    proposal.status = "approved"
    proposal.current_stage = 2
    proposal.committed_version = v4.version
    proposal.resolved_at = at(21, 9, 40)


def reset_schema(database_url: str) -> None:
    config = Config(str(REPO_ROOT / "backend" / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    command.downgrade(config, "base")
    command.upgrade(config, "head")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--through", type=int, choices=(3, 4), default=3)
    parser.add_argument("--reset", action="store_true")
    # The owner role: the seed writes across orgs and resets the schema.
    parser.add_argument("--database-url", default=get_settings().migration_database_url)
    args = parser.parse_args()

    if args.reset:
        await asyncio.to_thread(reset_schema, args.database_url)
    engine = make_engine(args.database_url)
    async with make_sessionmaker(engine)() as session, session.begin():
        result = await seed(session, through=args.through)
    await engine.dispose()
    print(f"Seeded @{result.space.handle} at v{args.through}")


if __name__ == "__main__":
    asyncio.run(main())
