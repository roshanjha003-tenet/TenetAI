"""The demo, end to end, in the order CLAUDE.md lists it (steps 2-9; step 1 is the seed).

One continuous run through the real API and webhooks, with recorded model responses and
fixture diffs, so a green run here means the live demo's moving parts all line up.
"""

import json

from sqlalchemy import func, select

from app.db import make_sessionmaker
from app.llm.gateway import RecordedGateway
from app.models import Event
from app.seed import D014
from tests.fakes import FIXTURES, INSTALLATION_ID, REPO, FakeGitHub, pr_event, signed
from tests.test_review import FakeNotifier

PRIVATE_THINKING = "Based on PAY-142 and our retry policy, what's the safest way to retry?"
SHARED = (
    "I think Maya will push back on the 24h window, but here goes.\n\n"
    "@payments-redesign proposing: bounded automatic retries for transient payment failures — "
    "at most 3 attempts in 24 hours, one idempotency key per payment reused on every attempt, "
    "hard declines stay on manual recovery, and keep the checkout rollout flag."
)


def as_(name: str) -> dict[str, str]:
    return {"Authorization": f"Bearer dev-{name}"}


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / "llm" / name).read_text())


def demo_llm() -> RecordedGateway:
    return RecordedGateway(
        {
            "private_assistant": [
                {
                    "text": "Use a bounded retry policy: at most 3 attempts over 24 "
                    "hours, one idempotency key, never retry hard declines."
                }
            ],
            "router": [{"kind": "decision", "reason": "proposes a retry policy"}],
            "capture": [fixture("capture_d014.json")],
            "conflict_check": [{"conflicts": []}],
            "pr_analyzer": [fixture("pr_284_analyzer.json"), fixture("pr_291_analyzer.json")],
            "pr_evaluator": [fixture("pr_291_evaluator.json")],
            "ask": [
                {
                    "answer": "D-014 is agreed (v4), approved by Maya Chen and Arjun Rao; PR #284 "
                    "implements it and its check passes.",
                    "cited": ["D-014"],
                },
                {
                    "answer": "3 attempts in 24 hours bounds recovery while keeping hard "
                    "declines on the manual path; D-014, approved by Maya Chen and Arjun Rao.",
                    "cited": ["D-014"],
                },
                {"answer": "v3 to v4: D-014 added bounded automatic retries.", "cited": ["D-014"]},
            ],
        }
    )


async def event_count(engine) -> int:
    async with make_sessionmaker(engine)() as s:
        return await s.scalar(select(func.count()).select_from(Event))


async def comment(client, number: int, body: str, delivery: str) -> None:
    payload = {
        "action": "created",
        "installation": {"id": INSTALLATION_ID},
        "repository": {"full_name": REPO},
        "issue": {"number": number, "pull_request": {}},
        "comment": {"body": body, "user": {"login": "arjun-acme", "type": "User"}},
    }
    raw, headers = signed(payload, "issue_comment", delivery)
    await client.post("/webhooks/github", content=raw, headers=headers)


async def test_demo_runs_end_to_end(seeded_v3, engine, app_factory) -> None:
    notifier, github, llm = FakeNotifier(), FakeGitHub(), demo_llm()
    users = seeded_v3.users
    async with app_factory(github=github, llm=llm, notifier=notifier) as (_, client):
        space = "/api/spaces/payments-redesign"

        # 2 · Private work with your own AI: nothing appears in the space.
        before = await event_count(engine)
        sid = (
            await client.post(
                f"{space}/sessions",
                json={"title": "Payment retry strategy"},
                headers=as_("yashwant"),
            )
        ).json()["id"]
        private = (
            await client.post(
                f"/api/sessions/{sid}/messages",
                json={"text": PRIVATE_THINKING},
                headers=as_("yashwant"),
            )
        ).json()
        assert private["shared"] is None and "bounded retry policy" in private["reply"]["text"]
        assert await event_count(engine) == before

        # 3 · Only the tagged text leaves.
        shared = (
            await client.post(
                f"/api/sessions/{sid}/messages", json={"text": SHARED}, headers=as_("yashwant")
            )
        ).json()["shared"]
        assert shared["tagged_text"].startswith("@payments-redesign proposing: bounded")
        assert "push back on the 24h window" not in shared["tagged_text"]

        # 4 · D-014 is review pending with its constraints and parent; Slack is told.
        assert (shared["decision_key"], shared["status"]) == ("D-014", "pending")
        pid = shared["proposal_id"]
        proposal = (await client.get(f"/api/proposals/{pid}", headers=as_("maya"))).json()
        assert proposal["content"]["constraints"] == D014["constraints"]
        assert proposal["content"]["parents"] == ["D-013"]
        assert [n[0] for n in notifier.sent[:2]] == ["proposal_created", "review_requested"]
        assert notifier.sent[1][1] == [users["maya"].id]

        # 5 · Fixed two-stage review: product scope (Maya), then technical safety (Arjun).
        skip = await client.post(f"/api/proposals/{pid}/approve", json={}, headers=as_("arjun"))
        assert skip.status_code == 403
        await client.post(
            f"/api/proposals/{pid}/approve",
            json={"note": "Scope looks right; keep hard declines manual."},
            headers=as_("maya"),
        )
        mid = (await client.get(f"{space}/state", headers=as_("arjun"))).json()
        assert mid["version"] == 3  # state stays v3 until both approve
        await client.post(
            f"/api/proposals/{pid}/approve",
            json={"note": "Idempotency guard checked."},
            headers=as_("arjun"),
        )

        # 6 · v4 is the agreed state.
        v4 = (await client.get(f"{space}/state", headers=as_("priya"))).json()
        assert v4["version"] == 4
        d014 = v4["snapshot"]["decisions"]["D-014"]
        assert [a["name"] for a in d014["approved_by"]] == ["Maya Chen", "Arjun Rao"]
        assert notifier.sent[-1][0] == "state_updated"

        # 7 · Arjun's PR #284 passes; @tenet answers in PR comments, as that PR's agent.
        raw, headers = signed(pr_event(284), "pull_request", "pr-284")
        await client.post("/webhooks/github", content=raw, headers=headers)
        assert github.check_runs[-1]["conclusion"] == "success"
        for i, q in enumerate(["where are we?", "why 3 retries?", "what changed?"]):
            await comment(client, 284, f"@tenet {q}", f"c-{i}")
        assert len(github.comments) == 3
        assert all("@payments-redesign/pr-284" in c["body"] for c in github.comments)
        assert "approved by Maya Chen and Arjun Rao" in github.comments[1]["body"]

        # 8 · The coding agent's PR #291 makes a new key per retry: the check fails, naming
        # D-014's constraint, its approvers and the lines.
        raw, headers = signed(pr_event(291), "pull_request", "pr-291")
        await client.post("/webhooks/github", content=raw, headers=headers)
        drift = github.check_runs[-1]
        assert drift["conclusion"] == "failure"
        assert (
            "one idempotency key per payment, reused on every attempt" in drift["output"]["title"]
        )
        summary = drift["output"]["summary"]
        assert "Maya Chen (product scope) and Arjun Rao (technical safety)" in summary
        assert "`payments/retry.py:33-34`" in summary

        # 9 · Read-only rewind of the retry policy, v2 → v4, step by step.
        events_before_rewind = await event_count(engine)
        rewind = (await client.get(f"{space}/rewind?from=2&to=4", headers=as_("yashwant"))).json()
        assert [s["version"] for s in rewind["steps"]] == [2, 3, 4]
        assert [[c["key"] for c in s["changes"]] for s in rewind["steps"]] == [
            ["D-012"],
            ["D-013"],
            ["D-014"],
        ]
        assert await event_count(engine) == events_before_rewind
