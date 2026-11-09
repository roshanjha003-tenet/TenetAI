import uuid

from sqlalchemy import select

from app.db import make_sessionmaker
from app.models import Event, Pushback, StewardJob
from app.seed import D014

D014_BODY = {
    "type": "decision",
    "title": D014["title"],
    "content": {
        "statement": D014["statement"],
        "constraints": D014["constraints"],
        "parents": ["D-013"],
        "area": "technical-safety",
        "tagged_text": "@payments-redesign proposing: bounded automatic retries…",
    },
    "evidence": [{"kind": "notion", "title": "Payment retry policy v2"}],
}


def as_(name: str) -> dict[str, str]:
    return {"Authorization": f"Bearer dev-{name}"}


class FakeNotifier:
    def __init__(self) -> None:
        self.sent: list[tuple[str, list[uuid.UUID], dict]] = []

    async def notify(self, state, notice) -> None:
        self.sent.append((notice.kind, notice.user_ids, notice.data))


async def propose(client, body=D014_BODY, who="yashwant"):
    return await client.post("/api/spaces/payments-redesign/proposals", json=body, headers=as_(who))


async def test_d014_two_stage_review_commits_v4(seeded_v3, engine, app_factory) -> None:
    notifier = FakeNotifier()
    users = seeded_v3.users
    async with app_factory(notifier=notifier) as (_, client):
        created = await propose(client)
        assert created.status_code == 201, created.text
        proposal = created.json()
        assert proposal["decision_key"] == "D-014"
        assert proposal["base_version"] == 3
        assert [s["state"] for s in proposal["stages"]] == ["waiting", "not_started"]
        assert proposal["stages"][0]["owner"]["name"] == "Maya Chen"
        pid = proposal["id"]

        # Stage 2's owner can't skip stage 1.
        early = await client.post(f"/api/proposals/{pid}/approve", json={}, headers=as_("arjun"))
        assert early.status_code == 403
        assert "Maya Chen" in early.json()["detail"]

        stage1 = await client.post(
            f"/api/proposals/{pid}/approve",
            json={"note": "In scope if flagged."},
            headers=as_("maya"),
        )
        assert [s["state"] for s in stage1.json()["stages"]] == ["approved", "waiting"]
        state = await client.get("/api/spaces/payments-redesign/state", headers=as_("priya"))
        assert state.json()["version"] == 3  # nothing agreed until both stages approve

        stage2 = await client.post(
            f"/api/proposals/{pid}/approve", json={"note": "Key per payment."}, headers=as_("arjun")
        )
        done = stage2.json()
        assert (done["status"], done["committed_version"]) == ("approved", 4)

        state = (
            await client.get("/api/spaces/payments-redesign/state", headers=as_("priya"))
        ).json()
        d014 = state["snapshot"]["decisions"]["D-014"]
        assert state["version"] == 4 and state["parent_version"] == 3
        assert d014["constraints"] == D014["constraints"]
        assert d014["parents"] == ["D-013"]
        assert [a["name"] for a in d014["approved_by"]] == ["Maya Chen", "Arjun Rao"]

        decision = (
            await client.get("/api/spaces/payments-redesign/decisions/D-014", headers=as_("priya"))
        ).json()
        assert decision["current_revision"] == 1
        assert decision["area"]["owner"]["name"] == "Arjun Rao"

    async with make_sessionmaker(engine)() as s:
        types = list(await s.scalars(select(Event.type).order_by(Event.seq)))
    assert types[-5:] == [
        "proposal.created",
        "proposal.approved",
        "proposal.approved",
        "state.committed",
        "decision.created",
    ]
    assert [kind for kind, _, _ in notifier.sent] == [
        "proposal_created",
        "review_requested",
        "review_requested",
        "state_updated",
    ]
    assert notifier.sent[1][1] == [users["maya"].id]
    assert notifier.sent[2][1] == [users["arjun"].id]


async def test_identity_comes_from_the_token(seeded_v3, app_factory) -> None:
    async with app_factory() as (_, client):
        missing = await client.post("/api/spaces/payments-redesign/proposals", json=D014_BODY)
        wrong = await client.post(
            "/api/spaces/payments-redesign/proposals",
            json=D014_BODY,
            headers={"Authorization": "Bearer nope"},
        )
        # A proposer field in the body is ignored; the token decides who proposed.
        spoof = await propose(client, {**D014_BODY, "proposer_id": str(uuid.uuid4())}, "priya")

    assert (missing.status_code, wrong.status_code) == (401, 401)
    assert spoof.json()["proposer"]["name"] == "Priya Nair"


async def test_proposal_validation(seeded_v3, app_factory) -> None:
    content = D014_BODY["content"]
    async with app_factory() as (_, client):
        bad_parent = await propose(
            client, {**D014_BODY, "content": {**content, "parents": ["D-999"]}}
        )
        long_line = await propose(
            client, {**D014_BODY, "content": {**content, "constraints": ["x" * 201]}}
        )
        no_area = await propose(client, {**D014_BODY, "content": {**content, "area": "legal"}})
        pivot = await propose(client, {**D014_BODY, "type": "pivot"})

    assert bad_parent.status_code == 422 and "D-999" in bad_parent.json()["detail"]
    assert long_line.status_code == 422
    assert no_area.status_code == 422
    assert pivot.status_code == 422


async def test_pushback_must_be_answered_to_approve(seeded_v3, engine, app_factory) -> None:
    async with app_factory() as (_, client):
        pid = (await propose(client)).json()["id"]
        raised = await client.post(
            f"/api/proposals/{pid}/pushbacks",
            json={"reason": "3 attempts may be too many for debit cards"},
            headers=as_("priya"),
        )
        assert raised.status_code == 201

        silent = await client.post(f"/api/proposals/{pid}/approve", json={}, headers=as_("maya"))
        assert silent.status_code == 422

        approved = await client.post(
            f"/api/proposals/{pid}/approve",
            json={"note": "Processor caps debit retries anyway."},
            headers=as_("maya"),
        )
        assert approved.status_code == 200

    async with make_sessionmaker(engine)() as s:
        pushback = (await s.scalars(select(Pushback))).one()
    assert (pushback.outcome, pushback.note) == (
        "overruled",
        "Processor caps debit retries anyway.",
    )


async def test_rejected_proposal_is_closed(seeded_v3, app_factory) -> None:
    async with app_factory() as (_, client):
        pid = (await propose(client)).json()["id"]
        rejected = await client.post(
            f"/api/proposals/{pid}/reject", json={"reason": "Not for Oct 23."}, headers=as_("maya")
        )
        again = await client.post(f"/api/proposals/{pid}/approve", json={}, headers=as_("maya"))
        state = await client.get("/api/spaces/payments-redesign/state", headers=as_("maya"))

    assert rejected.json()["status"] == "rejected"
    assert again.status_code == 409
    assert state.json()["version"] == 3


async def approve_both(client, pid: str):
    await client.post(f"/api/proposals/{pid}/approve", json={}, headers=as_("maya"))
    return (
        await client.post(f"/api/proposals/{pid}/approve", json={}, headers=as_("arjun"))
    ).json()


async def test_head_moved_without_conflict_applies_on_new_head(seeded_v3, app_factory) -> None:
    status = {
        "type": "status",
        "title": "Checkout QA started",
        "content": {"text": "QA on the new checkout started today."},
    }
    async with app_factory() as (_, client):
        first = (await propose(client, status)).json()["id"]
        second = (await propose(client)).json()["id"]  # D-014, also written against v3
        assert (await approve_both(client, first))["committed_version"] == 4
        result = await approve_both(client, second)

    assert (result["status"], result["committed_version"]) == ("approved", 5)


async def test_head_moved_with_conflict_goes_back_to_owner(seeded_v3, engine, app_factory):
    def revise_d013(text: str) -> dict:
        return {
            "type": "revision",
            "decision_key": "D-013",
            "title": "Checkout target",
            "content": {
                "statement": text,
                "constraints": [text],
                "parents": [],
                "area": "product-scope",
            },
        }

    notifier = FakeNotifier()
    async with app_factory(notifier=notifier) as (_, client):
        first = (await propose(client, revise_d013("target moves to Oct 30"))).json()["id"]
        second = (await propose(client, revise_d013("target stays Oct 23"))).json()["id"]
        assert (await approve_both(client, first))["committed_version"] == 4
        blocked = await approve_both(client, second)
        state = await client.get("/api/spaces/payments-redesign/state", headers=as_("maya"))

    assert blocked["status"] == "blocked"
    assert state.json()["version"] == 4
    assert notifier.sent[-1][0] == "blocked"
    assert notifier.sent[-1][2] == {"conflicts_with": ["D-013"]}
    async with make_sessionmaker(engine)() as s:
        jobs = list(await s.scalars(select(StewardJob.status).order_by(StewardJob.seq)))
    assert jobs == ["done", "blocked"]


async def test_space_creation_commits_v1_and_links_items(seeded_v3, app_factory) -> None:
    async with app_factory() as (_, client):
        created = await client.post(
            "/api/spaces",
            json={
                "handle": "@checkout-copy",
                "name": "Checkout copy",
                "goal": "Clearer errors",
                "areas": [
                    {
                        "key": "product-scope",
                        "name": "Product scope",
                        "owner_email": "maya@acmepay.dev",
                    },
                    {
                        "key": "technical-safety",
                        "name": "Technical safety",
                        "owner_email": "arjun@acmepay.dev",
                    },
                ],
            },
            headers=as_("yashwant"),
        )
        item = await client.post(
            "/api/spaces/checkout-copy/items",
            json={"url": "https://acmepay.atlassian.net/browse/PAY-150", "title": "PAY-150"},
            headers=as_("yashwant"),
        )
        outsider = await client.get("/api/spaces/checkout-copy", headers=as_("priya"))
        detail = await client.get("/api/spaces/checkout-copy", headers=as_("maya"))

    assert created.status_code == 201
    assert created.json()["head_version"] == 1
    assert item.json()["kind"] == "jira"
    assert outsider.status_code == 403
    assert {m["name"] for m in detail.json()["members"]} == {"Yashwant", "Maya Chen", "Arjun Rao"}
