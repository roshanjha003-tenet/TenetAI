"""Authentication: cookie sessions, CSRF, dev-token gating, Google/Microsoft sign-in, invites,
verified domains, and the audit trail they leave."""

import time
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.responses import Response
from sqlalchemy import select, update

from app.config import Settings
from app.db import make_sessionmaker
from app.identity import COOKIE, set_cookie
from app.models import AuditLog, AuthSession, Member, User
from app.oidc import OIDC, PROVIDERS, SignInError
from tests.fakes import WEBHOOK_SECRET

WEB = "http://web.test"
CSRF = {"X-Tenet-CSRF": "1"}
GOOGLE_ID = "google-client-id"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
JWK = {**jwt.algorithms.RSAAlgorithm.to_jwk(KEY.public_key(), as_dict=True), "kid": "k1"}


def as_(name: str) -> dict[str, str]:
    return {"Authorization": f"Bearer dev-{name}"}


async def sign_in_dev(client: httpx.AsyncClient, who: str) -> str:
    response = await client.post("/api/auth/dev", json={"token": f"dev-{who}"}, headers=CSRF)
    assert response.status_code == 200, response.text
    return response.cookies[COOKIE]


async def audit_rows(engine, action: str) -> list[AuditLog]:
    async with make_sessionmaker(engine)() as s:
        return list(
            await s.scalars(select(AuditLog).where(AuditLog.action == action).order_by("seq"))
        )


# --- sessions and CSRF -----------------------------------------------------------------------


async def test_dev_sign_in_gives_an_httponly_session_cookie(seeded_v3, engine, app_factory):
    async with app_factory() as (_, client):
        response = await client.post("/api/auth/dev", json={"token": "dev-maya"}, headers=CSRF)
        cookie = response.headers["set-cookie"].lower()
        me = await client.get("/api/me")  # the cookie alone identifies Maya

    assert "httponly" in cookie and "samesite=lax" in cookie and "path=/" in cookie
    assert "secure" not in cookie  # dev runs on http://localhost
    assert me.json()["name"] == "Maya Chen"
    async with make_sessionmaker(engine)() as s:
        stored = (await s.scalars(select(AuthSession))).one()
    assert stored.token_hash != response.cookies[COOKIE]  # only the hash is kept
    [signed_in] = await audit_rows(engine, "auth.sign_in")
    assert (signed_in.outcome, signed_in.details) == ("success", {"provider": "dev"})


def test_cookie_is_secure_outside_dev() -> None:
    response = Response()
    set_cookie(response, Settings(env="prod"), "token")
    assert "secure" in response.headers["set-cookie"].lower()


async def test_cookie_requests_need_the_csrf_header_and_our_origin(seeded_v3, app_factory):
    finding = {"text": "Card networks cap retries at 15 per 30 days."}
    url = "/api/spaces/payments-redesign/findings"
    async with app_factory() as (_, client):
        await sign_in_dev(client, "arjun")
        no_header = await client.post(url, json=finding)
        foreign = await client.post(url, json=finding, headers={**CSRF, "Origin": "https://evil"})
        ours = await client.post(url, json=finding, headers={**CSRF, "Origin": WEB})
        read = await client.get(url)  # reads need no header

    assert (no_header.status_code, foreign.status_code) == (403, 403)
    assert ours.status_code == 201
    assert read.status_code == 200


async def test_sessions_expire_when_idle_and_at_their_limit(seeded_v3, engine, app_factory):
    async with app_factory() as (_, client):
        await sign_in_dev(client, "maya")
        sessions = make_sessionmaker(engine)
        async with sessions() as s, s.begin():
            await s.execute(
                update(AuthSession).values(last_seen_at=datetime.now(UTC) - timedelta(hours=13))
            )
        idle = await client.get("/api/me")

        await sign_in_dev(client, "maya")
        async with sessions() as s, s.begin():
            await s.execute(
                update(AuthSession)
                .where(AuthSession.revoked_at.is_(None))
                .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
            )
        expired = await client.get("/api/me")

    assert idle.status_code == 401
    assert expired.status_code == 401


async def test_logout_and_logout_all_revoke(seeded_v3, engine, app_factory):
    async with app_factory() as (app, laptop), app_factory() as (_, phone):
        await sign_in_dev(laptop, "maya")
        await sign_in_dev(phone, "maya")
        listed = (await laptop.get("/api/auth/sessions")).json()
        assert len(listed) == 2 and sum(s["current"] for s in listed) == 1

        await laptop.post("/api/auth/logout-all", headers=CSRF)
        assert (await phone.get("/api/me")).status_code == 401

        await sign_in_dev(phone, "maya")
        await phone.post("/api/auth/logout", headers=CSRF)
        assert (await phone.get("/api/me")).status_code == 401

    actions = [r.action for r in await audit_rows(engine, "auth.sign_out")]
    assert actions == ["auth.sign_out"]
    [revoked] = await audit_rows(engine, "auth.sessions_revoked")
    assert revoked.details == {"count": 2, "scope": "all"}


async def test_turning_someone_off_ends_their_sessions(seeded_v3, engine, app_factory):
    maya_id = seeded_v3.users["maya"].id
    async with app_factory() as (_, maya), app_factory() as (_, admin):
        await sign_in_dev(maya, "maya")
        not_admin = await maya.patch(
            f"/api/admin/people/{seeded_v3.users['arjun'].id}",
            json={"active": False},
            headers=CSRF,
        )
        off = await admin.patch(
            f"/api/admin/people/{maya_id}", json={"active": False}, headers=as_("yashwant")
        )
        after = await maya.get("/api/me")
        dev_token = await admin.get("/api/me", headers=as_("maya"))

    assert not_admin.status_code == 403
    assert off.json()["active"] is False
    assert after.status_code == 401 and dev_token.status_code == 401
    [row] = await audit_rows(engine, "user.deactivated")
    assert row.subject == "maya@acmepay.dev" and row.details["sessions_revoked"] == 1


async def test_dev_tokens_only_work_in_dev(seeded_v3, test_api_database_url, engine):
    from app.main import create_app

    prod = Settings(env="prod", web_url=WEB, github_webhook_secret=WEBHOOK_SECRET)
    app = create_app(
        test_api_database_url,
        settings=prod,
        github=None,
        llm=None,
        notifier=None,
        drive=None,
        background_sync=False,
    )
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        bearer = await c.get("/api/me", headers=as_("maya"))
        dev = await c.post("/api/auth/dev", json={"token": "dev-maya"}, headers=CSRF)
        config = (await c.get("/api/auth/config")).json()
    await app.state.engine.dispose()

    assert bearer.status_code == 401 and dev.status_code == 404
    assert config["dev"] is False


def test_production_config_problems_are_named() -> None:
    from app.hardening import config_problems

    problems = config_problems(Settings(env="prod", public_url="http://api", web_url="http://w"))
    assert any("SECRET_KEY" in p for p in problems)
    assert any("PUBLIC_URL must be https" in p for p in problems)
    assert any("sign-in provider" in p for p in problems)
    assert config_problems(Settings(env="dev")) == []


async def test_sign_in_is_rate_limited(seeded_v3, app_factory):
    async with app_factory() as (_, client):
        codes = [
            (await client.post("/api/auth/dev", json={"token": "nope"}, headers=CSRF)).status_code
            for _ in range(31)
        ]
    assert codes[:30] == [401] * 30 and codes[30] == 429


# --- Google / Microsoft sign-in ----------------------------------------------------------------


class FakeIdP:
    """Google's token and key endpoints, signing ID tokens with a test RSA key."""

    def __init__(self) -> None:
        self.claims: dict[str, Any] = {}
        self.key = KEY

    def id_token(self, nonce: str) -> str:
        now = int(time.time())
        claims = {
            "iss": "https://accounts.google.com",
            "aud": GOOGLE_ID,
            "sub": "g-123",
            "iat": now,
            "exp": now + 600,
            "nonce": nonce,
            "email_verified": True,
            **self.claims,
        }
        return jwt.encode(claims, self.key, algorithm="RS256", headers={"kid": "k1"})

    def handle(self, request: httpx.Request) -> httpx.Response:
        if request.url == PROVIDERS["google"].jwks_url:
            return httpx.Response(200, json={"keys": [JWK]})
        if request.url == PROVIDERS["google"].token_url:
            form = parse_qs(request.content.decode())
            assert form["code_verifier"][0] and form["client_id"] == [GOOGLE_ID]
            return httpx.Response(200, json={"id_token": self.id_token(self.nonce)})
        return httpx.Response(404)

    def oidc(self) -> OIDC:
        settings = Settings(
            google_signin_client_id=GOOGLE_ID,
            google_signin_client_secret="s",
            web_url=WEB,
            public_url="http://api.test",
        )
        return OIDC(
            settings, http=lambda: httpx.AsyncClient(transport=httpx.MockTransport(self.handle))
        )


async def google_sign_in(client, idp: FakeIdP, **claims) -> httpx.Response:
    """Run the whole flow: start, (the person signs in at Google), callback."""
    start_params = claims.pop("start", {})
    start = await client.get(
        "/api/auth/google/start", params={"next": "/approvals", **start_params}
    )
    assert start.status_code == 302, start.text
    query = parse_qs(urlparse(start.headers["location"]).query)
    assert query["code_challenge_method"] == ["S256"]
    idp.nonce = claims.pop("nonce", query["nonce"][0])
    idp.claims = claims
    state = claims.pop("state", None) or query["state"][0]
    return await client.get("/api/auth/google/callback", params={"code": "c", "state": state})


async def test_google_sign_in_for_an_existing_user(seeded_v3, engine, app_factory):
    idp = FakeIdP()
    async with app_factory(oidc=idp.oidc()) as (_, client):
        config = (await client.get("/api/auth/config")).json()
        done = await google_sign_in(client, idp, email="maya@acmepay.dev", name="Maya")
        me = await client.get("/api/me")

    assert config["providers"] == [{"id": "google", "label": "Google"}]
    assert done.status_code == 302 and done.headers["location"] == f"{WEB}/approvals"
    assert me.json()["name"] == "Maya Chen"
    [row] = await audit_rows(engine, "auth.sign_in")
    assert row.subject == "maya@acmepay.dev" and row.details == {"provider": "google"}


async def test_verified_domain_lets_colleagues_join(seeded_v3, engine, app_factory):
    idp = FakeIdP()
    async with app_factory(oidc=idp.oidc()) as (_, client):
        await google_sign_in(client, idp, email="dana@acmepay.dev", name="Dana Ortiz")
        me = (await client.get("/api/me")).json()

    assert me["name"] == "Dana Ortiz" and me["spaces"] == []  # in the org, in no space yet
    async with make_sessionmaker(engine)() as s:
        dana = await s.scalar(select(User).where(User.email == "dana@acmepay.dev"))
    assert dana.org_id == seeded_v3.org.id and not dana.external


@pytest.mark.parametrize(
    ("claims", "reason"),
    [
        ({"email": "stranger@elsewhere.example"}, "hasn't been invited"),
        ({"email": "someone@gmail.com"}, "hasn't been invited"),
        ({"email": "maya@acmepay.dev", "email_verified": False}, "isn't verified"),
        ({"email": "maya@acmepay.dev", "nonce": "wrong"}, "nonce"),
        ({"email": "maya@acmepay.dev", "aud": "someone-else"}, "didn't verify"),
        ({"email": "maya@acmepay.dev", "iss": "https://evil.example"}, "wrong issuer"),
        ({"email": "maya@acmepay.dev", "exp": 1_000_000}, "didn't verify"),
        ({"email": "maya@acmepay.dev", "state": "forged"}, "state didn't match"),
    ],
)
async def test_sign_in_refusals_are_audited(seeded_v3, engine, app_factory, claims, reason):
    idp = FakeIdP()
    async with app_factory(oidc=idp.oidc()) as (_, client):
        done = await google_sign_in(client, idp, **claims)
        me = await client.get("/api/me")

    assert done.status_code == 302
    assert done.headers["location"].startswith(f"{WEB}/login?error=")
    assert me.status_code == 401
    [row] = await audit_rows(engine, "auth.sign_in")
    assert row.outcome == "failure" and reason in row.reason


async def test_unsigned_id_token_is_refused(seeded_v3, app_factory):
    idp = FakeIdP()
    idp.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)  # not Google's key
    async with app_factory(oidc=idp.oidc()) as (_, client):
        done = await google_sign_in(client, idp, email="maya@acmepay.dev")
    assert "error=" in done.headers["location"]


def test_microsoft_needs_a_work_account() -> None:
    oidc = OIDC(Settings(microsoft_client_id="m", microsoft_client_secret="s"))
    ms = PROVIDERS["microsoft"]
    with pytest.raises(SignInError, match="work or school"):
        oidc.identity(
            ms,
            {"sub": "1", "tid": "9188040d-6c67-4c5b-b112-36a304b66dad", "email": "me@outlook.com"},
        )
    work = oidc.identity(ms, {"sub": "1", "tid": "t-1", "preferred_username": "Ann@Acme.com"})
    assert work.email == "ann@acme.com" and not work.email_verified_by_provider
    assert ms.issuer_ok("https://login.microsoftonline.com/t-1/v2.0", {"tid": "t-1"})
    assert not ms.issuer_ok("https://login.microsoftonline.com/t-2/v2.0", {"tid": "t-1"})


# --- invites and domains -----------------------------------------------------------------------


async def invite_guest(client) -> str:
    created = await client.post(
        "/api/admin/invites",
        json={"email": "lee@partner.example", "space": "@payments-redesign", "role": "guest"},
        headers=as_("yashwant"),
    )
    assert created.status_code == 201, created.text
    return created.json()["link"].rsplit("/", 1)[-1]


async def test_invited_guest_signs_in_and_sees_only_their_space(seeded_v3, engine, app_factory):
    idp = FakeIdP()
    async with (
        app_factory(oidc=idp.oidc()) as (_, admin),
        app_factory(oidc=idp.oidc()) as (
            _,
            guest,
        ),
    ):
        token = await invite_guest(admin)
        info = (await guest.get(f"/api/invites/{token}")).json()
        wrong = await google_sign_in(
            guest, idp, email="mallory@partner.example", start={"invite": token}
        )
        right = await google_sign_in(
            guest, idp, email="lee@partner.example", name="Lee Park", start={"invite": token}
        )
        me = (await guest.get("/api/me")).json()
        space = await guest.get("/api/spaces/payments-redesign")
        directory = await guest.get("/api/users")
        new_space = await guest.post(
            "/api/spaces", json={"handle": "side-project", "name": "Side"}, headers=CSRF
        )
        share = await guest.post(
            "/api/spaces/payments-redesign/findings", json={"text": "hi"}, headers=CSRF
        )
        again = await google_sign_in(
            guest, idp, email="lee@partner.example", start={"invite": token}
        )

    assert info == {
        "org": "Acme Pay",
        "space": "@payments-redesign",
        "role": "guest",
        "email": "lee@partner.example",
        "invited_by": "Yashwant",
        "expired": False,
        "accepted": False,
    }
    assert (
        "sign in with that account"
        in parse_qs(urlparse(wrong.headers["location"]).query)["error"][0]
    )
    assert right.headers["location"] == f"{WEB}/approvals"
    assert [s["role"] for s in me["spaces"]] == ["guest"]
    assert space.status_code == 200  # guests read their space...
    assert directory.status_code == 403  # ...but not the org's people
    assert new_space.status_code == 403 and share.status_code == 403
    assert "already used" in again.headers["location"].replace("+", " ")
    async with make_sessionmaker(engine)() as s:
        lee = await s.scalar(select(User).where(User.email == "lee@partner.example"))
        role = await s.scalar(select(Member.role).where(Member.user_id == lee.id))
    assert lee.external and role == "guest"


async def test_expired_invite_is_refused(seeded_v3, engine, app_factory):
    from app.models import Invite

    idp = FakeIdP()
    async with app_factory(oidc=idp.oidc()) as (_, client):
        token = await invite_guest(client)
        async with make_sessionmaker(engine)() as s, s.begin():
            await s.execute(update(Invite).values(expires_at=datetime.now(UTC) - timedelta(days=1)))
        done = await google_sign_in(
            client, idp, email="lee@partner.example", start={"invite": token}
        )
    assert "expired" in done.headers["location"]


async def test_only_admins_invite_and_manage_domains(seeded_v3, app_factory):
    async with app_factory() as (_, client):
        invite = await client.post(
            "/api/admin/invites", json={"email": "x@acmepay.dev"}, headers=as_("maya")
        )
        domain = await client.post(
            "/api/admin/domains", json={"domain": "acme.example"}, headers=as_("maya")
        )
        audit = await client.get("/api/admin/audit", headers=as_("arjun"))
    assert (invite.status_code, domain.status_code, audit.status_code) == (403, 403, 403)


async def test_domain_verification_by_dns_txt(seeded_v3, engine, app_factory):
    records: list[str] = []

    async def dns(domain: str) -> list[str]:
        assert domain == "acmepay.example"
        return records

    idp = FakeIdP()
    async with app_factory(oidc=idp.oidc(), dns_txt=dns) as (_, client):
        free = await client.post(
            "/api/admin/domains", json={"domain": "gmail.com"}, headers=as_("yashwant")
        )
        added = (
            await client.post(
                "/api/admin/domains", json={"domain": "AcmePay.example"}, headers=as_("yashwant")
            )
        ).json()
        before = await google_sign_in(client, idp, email="kim@acmepay.example")
        not_yet = await client.post(
            "/api/admin/domains/acmepay.example/verify", headers=as_("yashwant")
        )
        records.append(f'"{added["txt_record"]}"')
        verified = await client.post(
            "/api/admin/domains/acmepay.example/verify", headers=as_("yashwant")
        )
        after = await google_sign_in(client, idp, email="kim@acmepay.example", name="Kim")

    assert free.status_code == 422
    assert added["verified"] is False and added["txt_record"].startswith("tenet-verification=")
    assert "error=" in before.headers["location"]
    assert not_yet.status_code == 422 and "TXT record" in not_yet.json()["detail"]
    assert verified.json()["verified"] is True
    assert after.headers["location"] == f"{WEB}/approvals"
    outcomes = [r.outcome for r in await audit_rows(engine, "domain.verified")]
    assert outcomes == ["failure", "success"]
