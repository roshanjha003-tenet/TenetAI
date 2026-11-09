from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.config import Settings
from app.connectors.google_drive import GoogleDrive, TokenSet, file_id_from, save_tokens
from app.crypto import TokenBox
from app.db import make_sessionmaker
from app.llm.gateway import RecordedGateway
from app.models import ConnectorToken, Event, Item, SessionAttachment
from app.sessions import as_agent, as_user
from tests.fakes import WEBHOOK_SECRET

DOC_ID = "1RetryPolicyDocAbCdEfGh"
DOC_URL = f"https://docs.google.com/document/d/{DOC_ID}/edit"
DOC_TEXT = (
    "Retry experiment notes. Processor rate limits are per merchant: 10 retries per minute. "
    "Spacing retries 1 hour apart avoided every rate-limit error in staging."
)


def as_(name: str) -> dict[str, str]:
    return {"Authorization": f"Bearer dev-{name}"}


class FakeGoogle:
    """Google's OAuth, userinfo and Drive endpoints, in memory."""

    def __init__(self) -> None:
        self.docs = {
            DOC_ID: {
                "name": "Retry experiment",
                "text": DOC_TEXT,
                "mime": "application/vnd.google-apps.document",
            },
            "1SpreadsheetNotADoc00": {
                "name": "Sheet",
                "text": "",
                "mime": "application/vnd.google-apps.spreadsheet",
            },
        }
        self.requests: list[httpx.Request] = []
        self.refreshes = 0

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if request.url.host == "oauth2.googleapis.com":
            form = parse_qs(request.content.decode())
            if form["grant_type"] == ["refresh_token"]:
                self.refreshes += 1
            return httpx.Response(
                200,
                json={
                    "access_token": f"at-{len(self.requests)}",
                    "refresh_token": "rt-1",
                    "expires_in": 3600,
                    "scope": "drive.readonly",
                },
            )
        if request.url.host == "openidconnect.googleapis.com":
            return httpx.Response(200, json={"email": "yashwant@acmepay.dev"})
        assert request.headers["Authorization"].startswith("Bearer at-")
        if path == "/drive/v3/files":
            return httpx.Response(
                200,
                json={
                    "files": [
                        {
                            "id": i,
                            "name": d["name"],
                            "modifiedTime": "2026-10-20T10:00:00Z",
                            "webViewLink": f"https://docs.google.com/document/d/{i}/edit",
                        }
                        for i, d in self.docs.items()
                        if d["mime"].endswith("document")
                    ]
                },
            )
        file_id = path.split("/")[4]
        doc = self.docs.get(file_id)
        if doc is None:
            return httpx.Response(404)
        if path.endswith("/export"):
            return httpx.Response(200, text=doc["text"])
        return httpx.Response(
            200,
            json={
                "id": file_id,
                "name": doc["name"],
                "mimeType": doc["mime"],
                "modifiedTime": "2026-10-20T10:00:00Z",
                "webViewLink": f"https://docs.google.com/document/d/{file_id}/edit",
            },
        )

    def drive(self) -> GoogleDrive:
        settings = Settings(
            google_client_id="cid",
            google_client_secret="secret",
            public_url="http://api.test",
            web_url="http://web.test",
            github_webhook_secret=WEBHOOK_SECRET,
        )
        return GoogleDrive(
            settings, http=lambda: httpx.AsyncClient(transport=httpx.MockTransport(self.handle))
        )


async def connect(engine, user_id, expires_in: int = 3600) -> None:
    await save_tokens(
        make_sessionmaker(engine),
        user_id,
        TokenSet(
            access_token="at-0",
            refresh_token="rt-1",
            expires_at=datetime.now(UTC) + timedelta(seconds=expires_in),
            scope="drive.readonly",
            email="yashwant@acmepay.dev",
        ),
        TokenBox(Settings()),
    )


async def new_session(client, who: str = "yashwant") -> str:
    created = await client.post(
        "/api/spaces/payments-redesign/sessions", json={"title": "Retries"}, headers=as_(who)
    )
    return created.json()["id"]


def test_file_ids_from_links() -> None:
    assert file_id_from(DOC_URL) == DOC_ID
    assert file_id_from(f"https://drive.google.com/open?id={DOC_ID}") == DOC_ID
    assert file_id_from(DOC_ID) == DOC_ID
    assert file_id_from("https://example.com/nope") is None


async def test_connect_google_with_your_own_account(seeded_v4, engine, app_factory) -> None:
    google = FakeGoogle()
    drive = google.drive()
    async with app_factory(drive=drive) as (_, client):
        before = (await client.get("/api/connect/google", headers=as_("yashwant"))).json()
        url = (await client.post("/api/connect/google/start", headers=as_("yashwant"))).json()
        query = parse_qs(urlparse(url["url"]).query)
        back = await client.get(
            "/api/connect/google/callback", params={"code": "c-1", "state": query["state"][0]}
        )
        forged = await client.get(
            "/api/connect/google/callback", params={"code": "c-2", "state": query["state"][0] + "x"}
        )
        after = (await client.get("/api/connect/google", headers=as_("yashwant"))).json()
        maya = (await client.get("/api/connect/google", headers=as_("maya"))).json()

    assert before == {"configured": True, "connected": False, "email": None}
    assert query["client_id"] == ["cid"]
    assert "drive.readonly" in query["scope"][0]
    assert query["redirect_uri"] == ["http://api.test/api/connect/google/callback"]
    assert back.status_code == 307
    assert back.headers["location"] == "http://web.test/settings/connections?google=connected"
    assert "google=error" in forged.headers["location"]
    assert after == {"configured": True, "connected": True, "email": "yashwant@acmepay.dev"}
    assert maya["connected"] is False  # each person connects their own account


async def test_attached_doc_stays_private_until_shared(seeded_v4, engine, app_factory) -> None:
    google = FakeGoogle()
    llm = RecordedGateway({"private_assistant": [{"text": "Space them out."}]})
    async with app_factory(drive=google.drive(), llm=llm) as (_, client):
        sid = await new_session(client)
        not_connected = await client.post(
            f"/api/sessions/{sid}/attachments", json={"url": DOC_URL}, headers=as_("yashwant")
        )
        await connect(engine, seeded_v4.users["yashwant"].id)
        attached = await client.post(
            f"/api/sessions/{sid}/attachments", json={"url": DOC_URL}, headers=as_("yashwant")
        )
        sheet = await client.post(
            f"/api/sessions/{sid}/attachments",
            json={"url": "1SpreadsheetNotADoc00"},
            headers=as_("yashwant"),
        )
        await client.post(
            f"/api/sessions/{sid}/messages",
            json={"text": "What does my doc say about rate limits?"},
            headers=as_("yashwant"),
        )
        session = (await client.get(f"/api/sessions/{sid}", headers=as_("yashwant"))).json()
        theirs = await client.get(f"/api/sessions/{sid}", headers=as_("maya"))

    assert not_connected.status_code == 409
    assert attached.status_code == 201
    assert attached.json()["title"] == "Retry experiment"
    assert sheet.status_code == 422
    assert [a["title"] for a in session["attachments"]] == ["Retry experiment"]
    assert theirs.status_code == 404
    assert DOC_TEXT in llm.calls[0]["prompt"]  # your own AI reads it
    async with make_sessionmaker(engine)() as s:
        assert (await s.scalars(select(Item).where(Item.kind == "gdoc"))).all() == []
        payloads = [str(p) for p in await s.scalars(select(Event.payload))]
    assert not any("rate limits are per merchant" in p for p in payloads)


async def test_tagging_shares_the_doc_with_the_master_agent(seeded_v4, engine, app_factory):
    google = FakeGoogle()
    llm = RecordedGateway({"ask": [{"answer": "Per merchant.", "cited": []}]})
    await connect(engine, seeded_v4.users["yashwant"].id)
    async with app_factory(drive=google.drive(), llm=llm) as (_, client):
        sid = await new_session(client)
        doc = (
            await client.post(
                f"/api/sessions/{sid}/attachments", json={"url": DOC_URL}, headers=as_("yashwant")
            )
        ).json()
        sent = (
            await client.post(
                f"/api/sessions/{sid}/messages",
                json={
                    "text": "@payments-redesign finding: retries hit per-merchant rate limits; "
                    "spacing them out fixed it in staging.",
                    "action": "finding",
                    "attachment_ids": [doc["id"]],
                },
                headers=as_("yashwant"),
            )
        ).json()
        findings = (
            await client.get("/api/spaces/payments-redesign/findings", headers=as_("arjun"))
        ).json()
        await client.post(
            "/api/spaces/payments-redesign/ask",
            json={"question": "what are the processor rate limits for retries?"},
            headers=as_("arjun"),
        )
        session = (await client.get(f"/api/sessions/{sid}", headers=as_("yashwant"))).json()

    assert "With: Retry experiment" in sent["reply"]["text"]
    [finding] = findings
    assert [e["title"] for e in finding["evidence"]] == ["Retry experiment"]
    assert session["attachments"][0]["shared_item_id"] == finding["evidence"][0]["id"]
    assert "Processor rate limits are per merchant" in llm.calls[0]["prompt"]


async def test_shared_docs_resync_with_the_sharers_permissions(seeded_v4, engine, app_factory):
    google = FakeGoogle()
    await connect(engine, seeded_v4.users["yashwant"].id, expires_in=-10)  # needs a refresh
    async with app_factory(drive=google.drive()) as (_, client):
        added = await client.post(
            "/api/spaces/payments-redesign/docs", json={"url": DOC_URL}, headers=as_("yashwant")
        )
        item_id = added.json()["id"]
        unchanged = (
            await client.post("/api/spaces/payments-redesign/sync", headers=as_("maya"))
        ).json()
        google.docs[DOC_ID]["text"] = DOC_TEXT + " Update: limits doubled on Oct 21."
        updated = (
            await client.post(
                f"/api/spaces/payments-redesign/items/{item_id}/sync", headers=as_("maya")
            )
        ).json()
        no_maya = await client.post(
            "/api/spaces/payments-redesign/docs", json={"url": DOC_URL}, headers=as_("maya")
        )

    assert added.status_code == 201 and added.json()["kind"] == "gdoc"
    assert google.refreshes == 1  # an expired token is refreshed, not re-asked
    assert [r["status"] for r in unchanged] == ["unchanged"]
    assert updated["status"] == "updated"
    assert no_maya.status_code == 409  # Maya hasn't connected Google; her permissions apply
    async with make_sessionmaker(engine)() as s:
        item = await s.get(Item, item_id)
        types = list(await s.scalars(select(Event.type).order_by(Event.seq)))
    assert item.excerpt.endswith("limits doubled on Oct 21.")
    assert types[-1] == "item.synced"


async def test_agents_cannot_read_tokens_or_attachments(seeded_v4, engine) -> None:
    await connect(engine, seeded_v4.users["yashwant"].id)
    sessions = make_sessionmaker(engine)
    for table in ("connector_tokens", "session_attachments"):
        with pytest.raises(DBAPIError, match="permission denied"):
            async with as_agent(sessions) as s:
                await s.execute(text(f"SELECT * FROM {table}"))
    async with as_user(sessions, seeded_v4.users["maya"].id) as s:
        assert (await s.scalars(select(ConnectorToken))).all() == []
        assert (await s.scalars(select(SessionAttachment))).all() == []
    async with as_user(sessions, seeded_v4.users["yashwant"].id) as s:
        assert len((await s.scalars(select(ConnectorToken))).all()) == 1


async def test_without_google_configured_drive_is_off(seeded_v4, app_factory) -> None:
    async with app_factory() as (_, client):
        status = (await client.get("/api/connect/google", headers=as_("yashwant"))).json()
        start = await client.post("/api/connect/google/start", headers=as_("yashwant"))

    assert status == {"configured": False, "connected": False, "email": None}
    assert start.status_code == 503
