import json

import httpx

from app.db import make_sessionmaker
from app.models import User
from app.notify.slack import SlackNotifier
from tests.test_review import D014_BODY, as_


class SlackRecorder:
    def __init__(self, fail: bool = False) -> None:
        self.posts: list[dict] = []
        self.fail = fail

    def client(self) -> httpx.AsyncClient:
        def handle(request: httpx.Request) -> httpx.Response:
            assert request.headers["Authorization"] == "Bearer xoxb-test"
            self.posts.append(json.loads(request.content))
            if self.fail:
                return httpx.Response(200, json={"ok": False, "error": "channel_not_found"})
            return httpx.Response(200, json={"ok": True})

        return httpx.AsyncClient(transport=httpx.MockTransport(handle))


def notifier(recorder: SlackRecorder) -> SlackNotifier:
    return SlackNotifier("xoxb-test", "#payments", "http://web.test", http=recorder.client)


async def test_d014_review_flow_posts_to_slack(seeded_v3, engine, app_factory) -> None:
    async with make_sessionmaker(engine)() as s, s.begin():
        (await s.get(User, seeded_v3.users["maya"].id)).slack_user_id = "U0MAYA"

    slack = SlackRecorder()
    async with app_factory(notifier=notifier(slack)) as (_, client):
        pid = (
            await client.post(
                "/api/spaces/payments-redesign/proposals", json=D014_BODY, headers=as_("yashwant")
            )
        ).json()["id"]
        await client.post(f"/api/proposals/{pid}/approve", json={}, headers=as_("maya"))
        await client.post(f"/api/proposals/{pid}/approve", json={}, headers=as_("arjun"))

    channels = [p["channel"] for p in slack.posts]
    texts = [p["text"] for p in slack.posts]
    assert channels == ["#payments", "U0MAYA", "#payments", "#payments"]
    assert texts[0] == (
        "Yashwant proposed D-014 · Enable bounded automatic retries for transient payment "
        "failures in @payments-redesign"
    )
    assert texts[1].startswith("Your turn to review D-014") and "(product scope)" in texts[1]
    assert "(technical safety)" in texts[2]
    assert texts[3].startswith("v4 is the agreed state of @payments-redesign: D-014")

    created_blocks = json.dumps(slack.posts[0]["blocks"], ensure_ascii=False)
    assert "one idempotency key per payment, reused on every attempt" in created_blocks
    assert "product scope: Maya Chen → technical safety: Arjun Rao" in created_blocks
    assert f"http://web.test/spaces/payments-redesign/proposals/{pid}" in created_blocks
    assert "<@U0MAYA>" in json.dumps(slack.posts[1]["blocks"])  # mapped user gets a real mention
    assert "*Arjun Rao*" in json.dumps(slack.posts[2]["blocks"])  # unmapped user: bold name


async def test_slack_failure_never_breaks_the_review(seeded_v3, app_factory) -> None:
    slack = SlackRecorder(fail=True)
    async with app_factory(notifier=notifier(slack)) as (_, client):
        created = await client.post(
            "/api/spaces/payments-redesign/proposals", json=D014_BODY, headers=as_("yashwant")
        )

    assert created.status_code == 201
    assert len(slack.posts) == 2  # both attempted, both failed, the proposal still exists
