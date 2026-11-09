import json

from sqlalchemy import select

from app.agents.scope import parse_agent, scoped_in
from app.db import make_sessionmaker
from app.findings import mentions_in
from app.llm.gateway import RecordedGateway
from app.models import Event, Finding, Proposal
from tests.fakes import FIXTURES, INSTALLATION_ID, REPO, FakeGitHub, pr_event, recorded, signed
from tests.test_review import FakeNotifier

FINDING = (
    "@payments-redesign finding: in staging, 2 of 40 retried payments hit the processor's "
    "rate limit on the 3rd attempt within 10 minutes. Spacing retries out may matter for D-014."
)


def as_(name: str) -> dict[str, str]:
    return {"Authorization": f"Bearer dev-{name}"}


async def new_session(client, who: str = "yashwant") -> str:
    created = await client.post(
        "/api/spaces/payments-redesign/sessions", json={"title": "Staging"}, headers=as_(who)
    )
    return created.json()["id"]


# --- agent ids -------------------------------------------------------------------------------


def test_agent_ids_parse() -> None:
    assert parse_agent("@payments-redesign/pr-284").handle == "@payments-redesign/pr-284"
    assert parse_agent("payments-redesign/d-14").decision_key == "D-014"
    assert parse_agent("@payments-redesign").kind == "space"
    assert parse_agent("@payments-redesign/pr-x") is None
    assert scoped_in("why? @payments-redesign/pr-291 failed", "payments-redesign").pr_number == 291
    assert scoped_in("@other-space/pr-1", "payments-redesign") is None
    assert mentions_in(FINDING + " see @payments-redesign/pr-291", "payments-redesign") == [
        "D-014",
        "pr-291",
    ]


# --- findings --------------------------------------------------------------------------------


async def test_finding_is_shared_without_approval(seeded_v4, engine, app_factory) -> None:
    notifier = FakeNotifier()
    llm = RecordedGateway({"router": [{"kind": "finding", "reason": "staging results"}]})
    async with app_factory(llm=llm, notifier=notifier) as (_, client):
        sid = await new_session(client)
        sent = (
            await client.post(
                f"/api/sessions/{sid}/messages", json={"text": FINDING}, headers=as_("yashwant")
            )
        ).json()
        listing = (
            await client.get("/api/spaces/payments-redesign/findings", headers=as_("maya"))
        ).json()
        state = (
            await client.get("/api/spaces/payments-redesign/state", headers=as_("maya"))
        ).json()

    assert sent["shared"]["route"] == "finding"
    assert "Shared as a finding" in sent["reply"]["text"]
    [finding] = listing
    assert finding["text"] == FINDING
    assert finding["author"]["name"] == "Yashwant"
    assert finding["mentions"] == ["D-014"]
    assert state["version"] == 4  # a finding never changes the agreed state
    assert notifier.sent[0][0] == "finding_shared"
    async with make_sessionmaker(engine)() as s:
        assert await s.scalar(select(Proposal.id).where(Proposal.status == "pending")) is None


async def test_collaborators_reply_and_author_is_told(seeded_v4, app_factory) -> None:
    notifier = FakeNotifier()
    async with app_factory(notifier=notifier) as (_, client):
        created = (
            await client.post(
                "/api/spaces/payments-redesign/findings",
                json={"text": FINDING},
                headers=as_("yashwant"),
            )
        ).json()
        fid = created["id"]
        agree = await client.post(
            f"/api/findings/{fid}/replies", json={"stance": "agree"}, headers=as_("priya")
        )
        bare = await client.post(
            f"/api/findings/{fid}/replies", json={"stance": "concern"}, headers=as_("arjun")
        )
        concern = await client.post(
            f"/api/findings/{fid}/replies",
            json={"stance": "concern", "text": "Rate limits are per merchant, not per payment."},
            headers=as_("arjun"),
        )

    assert agree.status_code == 201
    assert bare.status_code == 422  # a concern needs a line of text
    view = concern.json()
    assert view["counts"] == {"agree": 1, "concern": 1, "question": 0}
    assert [r["author"]["name"] for r in view["replies"]] == ["Priya Nair", "Arjun Rao"]
    assert [n[0] for n in notifier.sent] == ["finding_shared", "finding_reply", "finding_reply"]


async def test_promoting_a_finding_starts_the_normal_review(seeded_v4, engine, app_factory):
    capture = json.loads((FIXTURES / "llm" / "capture_d014.json").read_text())
    llm = RecordedGateway(
        {
            "capture": [
                {
                    **capture,
                    "title": "Space automatic retries at least 1 hour apart",
                    "constraints": ["retries are spaced at least 1 hour apart"],
                    "parents": ["D-014"],
                }
            ],
            "conflict_check": [{"conflicts": []}],
        }
    )
    async with app_factory(llm=llm) as (_, client):
        fid = (
            await client.post(
                "/api/spaces/payments-redesign/findings",
                json={"text": FINDING},
                headers=as_("priya"),
            )
        ).json()["id"]
        stranger = await client.post(f"/api/findings/{fid}/promote", headers=as_("yashwant"))
        promoted = await client.post(f"/api/findings/{fid}/promote", headers=as_("arjun"))
        again = await client.post(f"/api/findings/{fid}/promote", headers=as_("arjun"))

    assert stranger.status_code == 403  # neither its author nor an area owner
    body = promoted.json()
    assert promoted.status_code == 201, body
    assert (body["status"], body["decision_key"], body["proposal_status"]) == (
        "promoted",
        "D-015",
        "pending",
    )
    assert again.status_code == 409
    async with make_sessionmaker(engine)() as s:
        proposal = await s.get(Proposal, (await s.get(Finding, fid)).proposal_id)
        assert proposal.content["parents"] == ["D-014"]
        types = list(await s.scalars(select(Event.type).order_by(Event.seq)))
    assert types[-2:] == ["proposal.created", "finding.promoted"]


async def test_space_agent_uses_findings_as_not_agreed(seeded_v4, app_factory) -> None:
    llm = RecordedGateway({"ask": [{"answer": "x", "cited": []}]})
    async with app_factory(llm=llm) as (_, client):
        await client.post(
            "/api/spaces/payments-redesign/findings",
            json={"text": FINDING},
            headers=as_("yashwant"),
        )
        await client.post(
            "/api/spaces/payments-redesign/ask",
            json={"question": "rate limit on retries?"},
            headers=as_("maya"),
        )

    prompt = llm.calls[0]["prompt"]
    assert "NOT AGREED] " + FINDING in prompt


# --- PR and decision agents ------------------------------------------------------------------


async def run_both_prs(client) -> None:
    for number, delivery in ((284, "d284"), (291, "d291")):
        body, headers = signed(pr_event(number), "pull_request", delivery)
        await client.post("/webhooks/github", content=body, headers=headers)


def pr_llm(*extra: dict) -> RecordedGateway:
    gateway = recorded(
        pr_analyzer=["pr_284_analyzer.json", "pr_291_analyzer.json"],
        pr_evaluator=["pr_291_evaluator.json"],
    )
    for item in extra:
        for task, responses in item.items():
            gateway.responses[task].extend(responses)
    return gateway


async def test_every_pr_check_carries_its_agent_id(seeded_v4, app_factory) -> None:
    github = FakeGitHub()
    async with app_factory(github=github, llm=pr_llm()) as (_, client):
        await run_both_prs(client)

    for run, number in zip(github.check_runs, (284, 291), strict=True):
        assert f"Agent: `@payments-redesign/pr-{number}`" in run["output"]["summary"]
        assert "decision agents: @payments-redesign/D-014" in run["output"]["summary"]


async def test_pr_agent_answers_from_that_prs_record(seeded_v4, app_factory) -> None:
    llm = pr_llm(
        {"ask": [{"answer": "It reused no key.", "cited": ["D-014", "pr:" + REPO + "#291"]}]}
    )
    async with app_factory(github=FakeGitHub(), llm=llm) as (_, client):
        await run_both_prs(client)
        agents = (
            await client.get("/api/spaces/payments-redesign/agents", headers=as_("maya"))
        ).json()
        answer = (
            await client.post(
                "/api/spaces/payments-redesign/ask",
                json={"question": "why did this fail?", "agent": "@payments-redesign/pr-291"},
                headers=as_("maya"),
            )
        ).json()
        unknown = await client.post(
            "/api/spaces/payments-redesign/ask",
            json={"question": "?", "agent": "@payments-redesign/pr-999"},
            headers=as_("maya"),
        )

    assert [p["agent"] for p in agents["prs"]] == [
        "@payments-redesign/pr-284",
        "@payments-redesign/pr-291",
    ]
    [d014] = [d for d in agents["decisions"] if d["key"] == "D-014"]
    assert d014["prs"] == [284, 291]
    assert answer["agent"] == "@payments-redesign/pr-291"
    assert [s["kind"] for s in answer["sources"]] == ["decision", "pr"]
    prompt = llm.calls[-1]["prompt"]
    assert "Agent: @payments-redesign/pr-291" in prompt
    assert "one idempotency key per payment, reused on every attempt" in prompt
    assert "payments/retry.py:33-34" in prompt  # its own check finding
    assert "PR #284" not in prompt  # not the other PR's record
    assert "proposed by Yashwant" in prompt and "Maya Chen" in prompt  # how D-014 came about
    assert unknown.status_code == 404


async def test_decision_agent_covers_every_pr_that_implements_it(seeded_v4, app_factory):
    llm = pr_llm({"ask": [{"answer": "#284 reuses the key; #291 doesn't.", "cited": []}]})
    async with app_factory(github=FakeGitHub(), llm=llm) as (_, client):
        await run_both_prs(client)
        answer = (
            await client.post(
                "/api/spaces/payments-redesign/ask",
                json={
                    "question": "why did #291 fail when #284 passed?",
                    "agent": "@payments-redesign/D-014",
                },
                headers=as_("arjun"),
            )
        ).json()

    assert answer["agent"] == "@payments-redesign/D-014"
    prompt = llm.calls[-1]["prompt"]
    assert "PR #284" in prompt and "matches / success" in prompt
    assert "PR #291" in prompt and "drift / failure" in prompt
    assert "stage 2 technical safety: approved by Arjun Rao" in prompt


async def test_pr_agent_reports_decisions_that_changed_since(seeded_v4, engine, app_factory):
    from datetime import UTC, datetime

    from app.seed import D014
    from app.steward import Approval, DecisionChange, commit_decision

    llm = pr_llm({"ask": [{"answer": "D-014 changed.", "cited": []}]})
    async with app_factory(github=FakeGitHub(), llm=llm) as (_, client):
        await run_both_prs(client)
        async with make_sessionmaker(engine)() as s, s.begin():
            users, areas = seeded_v4.users, seeded_v4.areas
            await commit_decision(
                s,
                space_id=seeded_v4.space.id,
                base_version=4,
                decision=DecisionChange(
                    key="D-014",
                    title=D014["title"],
                    statement=D014["statement"],
                    constraints=[*D014["constraints"], "retries are spaced at least 1 hour apart"],
                    parents=D014["parents"],
                    area=areas["technical-safety"],
                    proposer=users["arjun"],
                    approvals=[Approval(users["arjun"], "technical safety", datetime.now(UTC))],
                ),
                actor_id=users["arjun"].id,
                idempotency_key="revise-d014",
            )
        await client.post(
            "/api/spaces/payments-redesign/ask",
            json={"question": "still fine?", "agent": "@payments-redesign/pr-284"},
            headers=as_("arjun"),
        )

    prompt = llm.calls[-1]["prompt"]
    assert "Linked at D-014 revision 1" in prompt
    assert "CHANGED SINCE THIS PR LINKED IT. Now D-014 revision 2" in prompt


async def test_tenet_in_a_pr_comment_answers_as_that_prs_agent(seeded_v4, app_factory) -> None:
    github = FakeGitHub()
    llm = pr_llm({"ask": [{"answer": "Drift on the key.", "cited": ["D-014"]}]})
    comment = {
        "action": "created",
        "installation": {"id": INSTALLATION_ID},
        "repository": {"full_name": REPO},
        "issue": {"number": 291, "pull_request": {}},
        "comment": {"body": "@tenet why did this fail?", "user": {"type": "User"}},
    }
    async with app_factory(github=github, llm=llm) as (_, client):
        await run_both_prs(client)
        body, headers = signed(comment, "issue_comment", "c-291")
        await client.post("/webhooks/github", content=body, headers=headers)

    [reply] = github.comments
    assert "Drift on the key." in reply["body"]
    assert "@payments-redesign/pr-291 · @payments-redesign at v4" in reply["body"]
    assert "Agent: @payments-redesign/pr-291" in llm.calls[-1]["prompt"]


async def test_private_session_can_ask_a_pr_agent(seeded_v4, app_factory) -> None:
    llm = pr_llm({"ask": [{"answer": "It made a new key per retry.", "cited": []}]})
    async with app_factory(github=FakeGitHub(), llm=llm) as (_, client):
        await run_both_prs(client)
        sid = await new_session(client)
        sent = (
            await client.post(
                f"/api/sessions/{sid}/messages",
                json={"text": "@payments-redesign/pr-291 what went wrong here?"},
                headers=as_("yashwant"),
            )
        ).json()

    assert sent["shared"]["route"] == "question"
    assert sent["shared"]["answer"]["agent"] == "@payments-redesign/pr-291"
    assert "@payments-redesign/pr-291: It made a new key per retry." in sent["reply"]["text"]
