from datetime import UTC, datetime

from sqlalchemy import select

from app.db import make_sessionmaker
from app.github.diff import parse_diff
from app.github.signature import sign, verify
from app.llm.gateway import LLMError, RecordedGateway
from app.models import Decision, Event, PRCheck, PRLink
from app.prcheck.analysis import DecisionContext, Finding, valid_findings
from app.prcheck.links import parse_implements
from app.seed import D014
from app.steward import Approval, DecisionChange, commit_decision
from tests.fakes import (
    INSTALLATION_ID,
    PRS,
    REPO,
    WEBHOOK_SECRET,
    FakeGitHub,
    diff_fixture,
    pr_event,
    recorded,
    signed,
)

# --- pure functions -------------------------------------------------------------------------


def test_parse_implements() -> None:
    body = "Retries.\n\nImplements: D-14, d-012\nimplements:D-014 and D-7\nNot this D-099"
    assert parse_implements(body) == ["D-014", "D-012", "D-007"]
    assert parse_implements("No decisions here") == []
    assert parse_implements(None) == []


def test_signature_round_trip() -> None:
    body = b'{"zen": "Design for failure."}'
    assert verify("s3cret", body, sign("s3cret", body))
    assert not verify("s3cret", body, sign("other", body))
    assert not verify("s3cret", body, None)


def test_diff_lines_are_new_side_and_added() -> None:
    diff = parse_diff(diff_fixture(291))

    assert diff.files["payments/retry.py"].added[33].strip().startswith("attempt_key = ")
    assert diff.has_lines("payments/retry.py", 33, 34)
    assert not diff.has_lines("payments/retry.py", 1, 2)  # context only, nothing added
    assert not diff.has_lines("payments/retry.py", 88, 90)  # beyond the file
    assert not diff.has_lines("payments/other.py", 1, 1)


def test_code_drops_findings_with_unknown_constraints_or_lines() -> None:
    diff = parse_diff(diff_fixture(291))
    d014 = DecisionContext("D-014", 1, D014["title"], D014["statement"], D014["constraints"])
    real = Finding(
        decision="d-014 ",
        constraint="One idempotency key per payment, reused on every attempt",
        file="payments/retry.py",
        start_line=33,
        end_line=34,
        explanation="new key per attempt",
    )
    invented = real.model_copy(update={"constraint": "retries are logged"})
    wrong_lines = real.model_copy(update={"start_line": 88, "end_line": 90})
    other_decision = real.model_copy(update={"decision": "D-999"})

    kept = valid_findings([real, invented, wrong_lines, other_decision], [d014], diff)

    assert len(kept) == 1
    assert kept[0].decision == "D-014"
    assert kept[0].constraint == "one idempotency key per payment, reused on every attempt"


# --- webhook end to end ---------------------------------------------------------------------


async def deliver(client, payload, event="pull_request", delivery="d-1", secret=WEBHOOK_SECRET):
    body, headers = signed(payload, event, delivery, secret)
    return await client.post("/webhooks/github", content=body, headers=headers)


async def checks(engine) -> list[PRCheck]:
    async with make_sessionmaker(engine)() as s:
        return list(await s.scalars(select(PRCheck).order_by(PRCheck.created_at)))


async def test_pr_284_matches_d014_and_passes(seeded_v4, engine, app_factory) -> None:
    github = FakeGitHub()
    llm = recorded(pr_analyzer=["pr_284_analyzer.json"])
    async with app_factory(github=github, llm=llm) as (_, client):
        response = await deliver(client, pr_event(284))

    assert response.status_code == 202
    [run] = github.check_runs
    assert run["conclusion"] == "success"
    assert run["head_sha"] == PRS[284]["sha"]
    assert run["installation_id"] == INSTALLATION_ID
    assert run["output"]["title"] == "Matches D-014"
    assert "Maya Chen (product scope) and Arjun Rao (technical safety)" in run["output"]["summary"]
    assert run["details_url"] == "http://web.test/spaces/payments-redesign/prs/284"

    [analyzer_call] = llm.calls
    assert analyzer_call["tier"] == "strong"
    assert "one idempotency key per payment, reused on every attempt" in analyzer_call["prompt"]
    assert "D-013" in analyzer_call["prompt"]  # the spine: D-014's parent still applies

    async with make_sessionmaker(engine)() as s:
        link = (await s.scalars(select(PRLink))).one()
        assert (link.repo, link.pr_number, link.pinned_revision) == (REPO, 284, 1)
        types = list(await s.scalars(select(Event.type).order_by(Event.seq)))
        assert types[-2:] == ["pr.linked", "pr.checked"]


async def test_pr_291_new_key_per_retry_fails_naming_d014(seeded_v4, engine, app_factory):
    github = FakeGitHub()
    llm = recorded(pr_analyzer=["pr_291_analyzer.json"], pr_evaluator=["pr_291_evaluator.json"])
    async with app_factory(github=github, llm=llm) as (_, client):
        await deliver(client, pr_event(291))

    [run] = github.check_runs
    assert run["conclusion"] == "failure"
    assert run["output"]["title"] == (
        "Drift: D-014 — one idempotency key per payment, reused on every attempt"
    )
    summary = run["output"]["summary"]
    assert "PR #291 contradicts D-014" in summary
    assert "Maya Chen (product scope) and Arjun Rao (technical safety)" in summary
    assert "`payments/retry.py:33-34`" in summary
    [annotation] = run["output"]["annotations"]
    assert (annotation["path"], annotation["start_line"], annotation["end_line"]) == (
        "payments/retry.py",
        33,
        34,
    )

    # Two invented findings were dropped by code; only the real one reached the evaluator.
    evaluator_prompt = llm.calls[1]["prompt"]
    assert "[0] D-014" in evaluator_prompt and "[1]" not in evaluator_prompt

    [check] = await checks(engine)
    assert (check.result, check.conclusion) == ("drift", "failure")
    assert check.findings[0]["approvers"] == [
        {"name": "Maya Chen", "stage": "product scope"},
        {"name": "Arjun Rao", "stage": "technical safety"},
    ]


async def test_evaluator_rejecting_every_finding_means_matches(seeded_v4, app_factory) -> None:
    github = FakeGitHub()
    llm = RecordedGateway(
        {
            "pr_analyzer": [
                {
                    "findings": [
                        {
                            "decision": "D-014",
                            "constraint": D014["constraints"][1],
                            "file": "payments/retry.py",
                            "start_line": 33,
                            "end_line": 34,
                            "explanation": "x",
                        }
                    ],
                    "confident": True,
                }
            ],
            "pr_evaluator": [{"verdicts": [{"finding": 0, "confirmed": False, "reason": "no"}]}],
        }
    )
    async with app_factory(github=github, llm=llm) as (_, client):
        await deliver(client, pr_event(291))

    assert github.check_runs[0]["conclusion"] == "success"


async def test_bad_signature_is_rejected(seeded_v4, app_factory) -> None:
    github = FakeGitHub()
    async with app_factory(github=github) as (_, client):
        response = await deliver(client, pr_event(284), secret="wrong")

    assert response.status_code == 401
    assert github.check_runs == []


async def test_redelivery_is_ignored(seeded_v4, engine, app_factory) -> None:
    github = FakeGitHub()
    llm = recorded(pr_analyzer=["pr_284_analyzer.json"])
    async with app_factory(github=github, llm=llm) as (_, client):
        first = await deliver(client, pr_event(284), delivery="same")
        second = await deliver(client, pr_event(284), delivery="same")

    assert first.json() == {"status": "accepted"}
    assert second.json() == {"status": "duplicate"}
    assert len(github.check_runs) == 1
    assert len(await checks(engine)) == 1


async def test_pr_without_implements_is_neutral(seeded_v4, app_factory) -> None:
    github = FakeGitHub()
    llm = RecordedGateway()
    async with app_factory(github=github, llm=llm) as (_, client):
        await deliver(client, pr_event(284, body="Just a refactor."))

    [run] = github.check_runs
    assert run["conclusion"] == "neutral"
    assert run["output"]["title"] == "No linked decisions"
    assert llm.calls == []


async def test_decision_revised_after_linking_is_stale(seeded_v4, engine, app_factory) -> None:
    github = FakeGitHub()
    llm = recorded(pr_analyzer=["pr_284_analyzer.json"])
    async with app_factory(github=github, llm=llm) as (_, client):
        await deliver(client, pr_event(284), delivery="first")

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

        await deliver(client, pr_event(284, action="synchronize"), delivery="second")

    assert [r["conclusion"] for r in github.check_runs] == ["success", "neutral"]
    assert "D-014 revision 1 → 2" in github.check_runs[1]["output"]["summary"]
    assert len(llm.calls) == 1  # still-current is plain code; no model call the second time


async def test_reopened_and_abandoned_decisions_are_neutral(seeded_v4, engine, app_factory):
    github = FakeGitHub()
    async with app_factory(github=github, llm=RecordedGateway()) as (_, client):
        for status, delivery in (("under_review", "a"), ("abandoned", "b")):
            async with make_sessionmaker(engine)() as s, s.begin():
                d = await s.scalar(select(Decision).where(Decision.key == "D-014"))
                d.status = status
            await deliver(client, pr_event(291), delivery=delivery)

    assert [r["output"]["title"] for r in github.check_runs] == [
        "D-014 is under review",
        "D-014 was abandoned",
    ]
    assert {r["conclusion"] for r in github.check_runs} == {"neutral"}


async def test_model_failure_fails_open(seeded_v4, app_factory) -> None:
    github = FakeGitHub()
    llm = RecordedGateway({"pr_analyzer": [LLMError("pr_analyzer: model declined")]})
    async with app_factory(github=github, llm=llm) as (_, client):
        await deliver(client, pr_event(291))

    [run] = github.check_runs
    assert run["conclusion"] == "neutral"
    assert run["output"]["title"] == "Tenet couldn't check this PR"


async def test_no_gateway_configured_is_neutral(seeded_v4, app_factory) -> None:
    github = FakeGitHub()
    async with app_factory(github=github, llm=None) as (_, client):
        await deliver(client, pr_event(291))

    assert github.check_runs[0]["conclusion"] == "neutral"


async def test_unlinked_repo_is_ignored(seeded_v4, engine, app_factory) -> None:
    github = FakeGitHub()
    payload = pr_event(284)
    payload["repository"]["full_name"] = "someone/else"
    async with app_factory(github=github, llm=RecordedGateway()) as (_, client):
        response = await deliver(client, payload)

    assert response.status_code == 202
    assert github.check_runs == []
    assert await checks(engine) == []
