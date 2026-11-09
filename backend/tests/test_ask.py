from app.ask.pr_comments import question_from
from app.llm.gateway import RecordedGateway
from tests.fakes import INSTALLATION_ID, REPO, FakeGitHub, signed


def as_(name: str) -> dict[str, str]:
    return {"Authorization": f"Bearer dev-{name}"}


WHERE_ARE_WE = {
    "answer": "Retries are agreed: D-014 allows up to 3 automatic attempts in 24 hours with one "
    "idempotency key per payment, approved by Maya Chen and Arjun Rao. It builds on D-013.",
    "cited": ["D-014", "D-013", "D-404", "item:not-a-real-item"],
}


async def test_ask_answers_with_sources_from_the_context(seeded_v4, app_factory) -> None:
    llm = RecordedGateway({"ask": [WHERE_ARE_WE]})
    async with app_factory(llm=llm) as (_, client):
        response = await client.post(
            "/api/spaces/payments-redesign/ask",
            json={"question": "Where are we on retries?"},
            headers=as_("priya"),
        )

    body = response.json()
    assert response.status_code == 200
    assert body["version"] == 4
    # Invented citations are dropped; only sources that were in the context survive.
    assert [s["id"] for s in body["sources"]] == ["D-014", "D-013"]
    prompt = llm.calls[0]["prompt"]
    assert "<versions>" in prompt and "v4" in prompt and "D-014: Enable bounded" in prompt
    assert len(prompt) < 16_000 * 4  # inside the fixed budget


async def test_ask_at_an_older_version_sees_only_that_state(seeded_v4, app_factory) -> None:
    llm = RecordedGateway({"ask": [{"answer": "At v2 failed payments were manual.", "cited": []}]})
    async with app_factory(llm=llm) as (_, client):
        response = await client.post(
            "/api/spaces/payments-redesign/ask",
            json={"question": "Where were we?", "version": 2},
            headers=as_("priya"),
        )

    assert response.json()["version"] == 2
    prompt = llm.calls[0]["prompt"]
    assert "D-012" in prompt and "D-014" not in prompt


async def test_rewind_v2_to_v4_step_by_step(seeded_v4, app_factory) -> None:
    async with app_factory() as (_, client):
        response = await client.get(
            "/api/spaces/payments-redesign/rewind?from=2&to=4", headers=as_("priya")
        )

    steps = response.json()["steps"]
    assert [s["version"] for s in steps] == [2, 3, 4]
    assert [[c["key"] for c in s["changes"]] for s in steps] == [["D-012"], ["D-013"], ["D-014"]]
    assert list(steps[0]["agreed"]) == ["D-012"]
    assert sorted(steps[2]["agreed"]) == ["D-012", "D-013", "D-014"]
    # The journey to v4: proposal, then product scope, then technical safety.
    assert [e["type"] for e in steps[2]["events"]] == [
        "proposal.created",
        "proposal.approved",
        "proposal.approved",
    ]
    assert steps[2]["events"][1]["actor"]["name"] == "Maya Chen"
    assert steps[2]["committed_by"]["name"] == "Arjun Rao"


async def test_rewind_is_read_only(seeded_v4, app_factory) -> None:
    async with app_factory() as (_, client):
        before = (
            await client.get("/api/spaces/payments-redesign/events?limit=500", headers=as_("priya"))
        ).json()
        await client.get("/api/spaces/payments-redesign/rewind?from=1", headers=as_("priya"))
        after = (
            await client.get("/api/spaces/payments-redesign/events?limit=500", headers=as_("priya"))
        ).json()
        state = await client.get("/api/spaces/payments-redesign/state", headers=as_("priya"))

    assert before == after
    assert state.json()["version"] == 4


def test_question_from_mentions() -> None:
    assert question_from("@tenet where are we?") == "where are we?"
    assert question_from("thanks! @tenet: why 3 retries?") == "why 3 retries?"
    assert question_from("@tenet") == "Where are we?"
    assert question_from("me@tenet.dev is my email") is None


async def test_tenet_answers_in_pr_comments(seeded_v4, app_factory) -> None:
    github = FakeGitHub()
    llm = RecordedGateway(
        {
            "ask": [
                {
                    "answer": "3 retries because D-014 bounds automatic attempts to 3 within "
                    "24 hours, approved by Maya Chen and Arjun Rao.",
                    "cited": ["D-014"],
                }
            ]
        }
    )
    payload = {
        "action": "created",
        "installation": {"id": INSTALLATION_ID},
        "repository": {"full_name": REPO},
        "issue": {"number": 284, "pull_request": {"url": "..."}},
        "comment": {
            "body": "@tenet why 3 retries?",
            "user": {"login": "priya-acme", "type": "User"},
        },
    }
    async with app_factory(github=github, llm=llm) as (_, client):
        body, headers = signed(payload, "issue_comment", "c-1")
        await client.post("/webhooks/github", content=body, headers=headers)
        # Tenet's own comment comes back as a webhook; it must not answer itself.
        bot = {**payload, "comment": {"body": "@tenet ...", "user": {"type": "Bot"}}}
        body, headers = signed(bot, "issue_comment", "c-2")
        await client.post("/webhooks/github", content=body, headers=headers)

    [comment] = github.comments
    assert comment["number"] == 284
    assert "D-014 bounds automatic attempts to 3" in comment["body"]
    assert (
        "[D-014 rev 1](http://web.test/spaces/payments-redesign/decisions/D-014)"
        in (comment["body"])
    )
    assert llm.calls[0]["prompt"].endswith("<question>\nwhy 3 retries?\n</question>")
