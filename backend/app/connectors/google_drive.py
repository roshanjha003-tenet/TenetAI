"""Google Drive connector. Every call uses one person's own OAuth grant, so Tenet can read a doc
only if that person can (connectors act with each person's own permissions)."""

import hashlib
import hmac
import re
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import Settings
from app.crypto import TokenBox
from app.models import ConnectorToken

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
DRIVE_URL = "https://www.googleapis.com/drive/v3"
SCOPES = "openid email https://www.googleapis.com/auth/drive.readonly"
DOC_MIME = "application/vnd.google-apps.document"
FILE_ID = re.compile(r"(?:/d/|[?&]id=)([A-Za-z0-9_-]{10,})")
STATE_TTL = 600


class DriveError(Exception):
    pass


class NotConnected(DriveError):
    pass


@dataclass
class TokenSet:
    access_token: str
    refresh_token: str | None
    expires_at: datetime
    scope: str
    email: str = ""


@dataclass
class Doc:
    id: str
    title: str
    url: str
    modified: str
    text: str

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.text.encode()).hexdigest()


def file_id_from(url_or_id: str) -> str | None:
    value = url_or_id.strip()
    match = FILE_ID.search(value)
    if match:
        return match.group(1)
    return value if re.fullmatch(r"[A-Za-z0-9_-]{10,}", value) else None


def is_google_doc_url(url: str) -> bool:
    return "docs.google.com/document" in url or "drive.google.com" in url


class GoogleDrive:
    def __init__(self, settings: Settings, http: Callable[[], httpx.AsyncClient] | None = None):
        self.client_id = settings.google_client_id
        self.client_secret = settings.google_client_secret
        self.redirect_uri = (
            settings.google_redirect_uri
            or f"{settings.public_url.rstrip('/')}/api/connect/google/callback"
        )
        self.secret = settings.secret_key.encode()
        self.http = http or (lambda: httpx.AsyncClient(timeout=20))
        self.box = TokenBox(settings)

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    # --- OAuth -------------------------------------------------------------------------------

    def sign_state(self, user_id: uuid.UUID, now: float | None = None) -> str:
        expires = int((now or time.time()) + STATE_TTL)
        body = f"{user_id}.{expires}.{uuid.uuid4().hex[:12]}"
        mac = hmac.new(self.secret, body.encode(), hashlib.sha256).hexdigest()[:32]
        return f"{body}.{mac}"

    def verify_state(self, state: str, now: float | None = None) -> uuid.UUID:
        try:
            user_id, expires, nonce, mac = state.split(".")
        except ValueError as exc:
            raise DriveError("malformed state") from exc
        body = f"{user_id}.{expires}.{nonce}"
        good = hmac.new(self.secret, body.encode(), hashlib.sha256).hexdigest()[:32]
        if not hmac.compare_digest(good, mac):
            raise DriveError("bad state signature")
        if int(expires) < (now or time.time()):
            raise DriveError("state expired")
        return uuid.UUID(user_id)

    def consent_url(self, state: str) -> str:
        return (
            AUTH_URL
            + "?"
            + urlencode(
                {
                    "client_id": self.client_id,
                    "redirect_uri": self.redirect_uri,
                    "response_type": "code",
                    "scope": SCOPES,
                    "access_type": "offline",
                    "prompt": "consent",
                    "include_granted_scopes": "true",
                    "state": state,
                }
            )
        )

    async def _token(self, data: dict[str, str]) -> TokenSet:
        async with self.http() as client:
            response = await client.post(
                TOKEN_URL,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    **data,
                },
            )
        if response.status_code != 200:
            raise DriveError(f"token request failed: {response.status_code}")
        body = response.json()
        return TokenSet(
            access_token=body["access_token"],
            refresh_token=body.get("refresh_token") or data.get("refresh_token"),
            expires_at=datetime.now(UTC) + timedelta(seconds=int(body.get("expires_in", 3600))),
            scope=body.get("scope", ""),
        )

    async def exchange(self, code: str) -> TokenSet:
        tokens = await self._token(
            {"code": code, "redirect_uri": self.redirect_uri, "grant_type": "authorization_code"}
        )
        async with self.http() as client:
            info = await client.get(
                USERINFO_URL, headers={"Authorization": f"Bearer {tokens.access_token}"}
            )
        if info.status_code == 200:
            tokens.email = info.json().get("email", "")
        return tokens

    async def refresh(self, refresh_token: str) -> TokenSet:
        return await self._token({"refresh_token": refresh_token, "grant_type": "refresh_token"})

    # --- Drive -------------------------------------------------------------------------------

    async def _get(self, access_token: str, path: str, **params: str) -> httpx.Response:
        async with self.http() as client:
            response = await client.get(
                f"{DRIVE_URL}{path}",
                params=params,
                headers={"Authorization": f"Bearer {access_token}"},
            )
        if response.status_code in (401, 403):
            raise NotConnected("Google says this account can't read that file")
        if response.status_code == 404:
            raise DriveError("no such Google Doc, or it isn't shared with you")
        if response.status_code != 200:
            raise DriveError(f"Drive request failed: {response.status_code}")
        return response

    async def get_doc(self, access_token: str, file_id: str) -> Doc:
        meta = (
            await self._get(
                access_token,
                f"/files/{file_id}",
                fields="id,name,mimeType,modifiedTime,webViewLink",
                supportsAllDrives="true",
            )
        ).json()
        if meta.get("mimeType") != DOC_MIME:
            raise DriveError("only Google Docs can be attached for now")
        text = (
            await self._get(access_token, f"/files/{file_id}/export", mimeType="text/plain")
        ).text.strip()
        return Doc(
            id=meta["id"],
            title=meta.get("name", "Untitled doc"),
            url=meta.get("webViewLink", f"https://docs.google.com/document/d/{file_id}"),
            modified=meta.get("modifiedTime", ""),
            text=text,
        )

    async def list_docs(self, access_token: str, query: str = "") -> list[dict[str, str]]:
        q = f"mimeType='{DOC_MIME}' and trashed=false"
        if query.strip():
            safe = query.replace("\\", "\\\\").replace("'", "\\'")
            q += f" and name contains '{safe}'"
        body = (
            await self._get(
                access_token,
                "/files",
                q=q,
                orderBy="modifiedTime desc",
                pageSize="10",
                fields="files(id,name,modifiedTime,webViewLink)",
                supportsAllDrives="true",
                includeItemsFromAllDrives="true",
            )
        ).json()
        return [
            {
                "id": f["id"],
                "title": f["name"],
                "modified": f.get("modifiedTime", ""),
                "url": f.get("webViewLink", ""),
            }
            for f in body.get("files", [])
        ]


async def access_token_for(
    drive: GoogleDrive, sessions: async_sessionmaker, user_id: uuid.UUID
) -> str:
    """The person's own access token, refreshed if it is about to expire."""
    from app.sessions import as_user

    async with as_user(sessions, user_id) as s:
        token = await s.get(ConnectorToken, (user_id, "google"))
        if token is None:
            raise NotConnected("connect Google Drive first")
        access = drive.box.open(token.access_token)
        if access and token.expires_at > datetime.now(UTC) + timedelta(seconds=60):
            return access
        refresh = drive.box.open(token.refresh_token)
        if not refresh:
            raise NotConnected("Google access expired; connect Google Drive again")
        fresh = await drive.refresh(refresh)
        token.access_token, token.expires_at = drive.box.seal(fresh.access_token), fresh.expires_at
        token.updated_at = datetime.now(UTC)
        return fresh.access_token


async def save_tokens(
    sessions: async_sessionmaker, user_id: uuid.UUID, tokens: TokenSet, box: TokenBox
) -> None:
    """Tokens are stored encrypted (app.crypto)."""
    from app.sessions import as_user

    async with as_user(sessions, user_id) as s:
        row = await s.get(ConnectorToken, (user_id, "google"))
        if row is None:
            row = ConnectorToken(owner_id=user_id, provider="google")
            s.add(row)
        row.access_token, row.expires_at, row.scope = (
            box.seal(tokens.access_token),
            tokens.expires_at,
            tokens.scope,
        )
        row.refresh_token = box.seal(tokens.refresh_token) or row.refresh_token
        row.account_email = tokens.email or row.account_email or ""
        row.updated_at = datetime.now(UTC)


def make_drive(settings: Settings) -> GoogleDrive:
    return GoogleDrive(settings)
