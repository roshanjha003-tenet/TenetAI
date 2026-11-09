"""Minimal GitHub App client: installation tokens, PR diffs, check runs, comments."""

import time
from pathlib import Path
from typing import Any, Protocol

import httpx
import jwt

from app.config import Settings


class GitHubAPI(Protocol):
    async def get_pull_diff(self, installation_id: int, repo: str, number: int) -> str: ...

    async def create_check_run(
        self, installation_id: int, repo: str, payload: dict[str, Any]
    ) -> dict[str, Any]: ...

    async def create_comment(
        self, installation_id: int, repo: str, number: int, body: str
    ) -> dict[str, Any]: ...


class GitHubApp:
    def __init__(self, app_id: str, private_key: str, api_url: str = "https://api.github.com"):
        self.app_id = app_id
        self.private_key = private_key
        self.api_url = api_url.rstrip("/")
        self._tokens: dict[int, tuple[str, float]] = {}

    def app_jwt(self) -> str:
        now = int(time.time())
        claims = {"iat": now - 60, "exp": now + 540, "iss": self.app_id}
        return jwt.encode(claims, self.private_key, algorithm="RS256")

    async def installation_token(self, installation_id: int) -> str:
        cached = self._tokens.get(installation_id)
        if cached and cached[1] > time.time() + 60:
            return cached[0]
        async with httpx.AsyncClient(base_url=self.api_url, timeout=20) as http:
            response = await http.post(
                f"/app/installations/{installation_id}/access_tokens",
                headers={
                    "Authorization": f"Bearer {self.app_jwt()}",
                    "Accept": "application/vnd.github+json",
                },
            )
            response.raise_for_status()
        token = response.json()["token"]
        self._tokens[installation_id] = (token, time.time() + 50 * 60)
        return token

    async def _request(
        self, installation_id: int, method: str, path: str, accept: str, json: Any = None
    ) -> httpx.Response:
        token = await self.installation_token(installation_id)
        async with httpx.AsyncClient(base_url=self.api_url, timeout=30) as http:
            response = await http.request(
                method,
                path,
                json=json,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": accept,
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
            response.raise_for_status()
            return response

    async def get_pull_diff(self, installation_id: int, repo: str, number: int) -> str:
        response = await self._request(
            installation_id, "GET", f"/repos/{repo}/pulls/{number}", "application/vnd.github.diff"
        )
        return response.text

    async def create_check_run(
        self, installation_id: int, repo: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        response = await self._request(
            installation_id,
            "POST",
            f"/repos/{repo}/check-runs",
            "application/vnd.github+json",
            json=payload,
        )
        return response.json()

    async def create_comment(
        self, installation_id: int, repo: str, number: int, body: str
    ) -> dict[str, Any]:
        response = await self._request(
            installation_id,
            "POST",
            f"/repos/{repo}/issues/{number}/comments",
            "application/vnd.github+json",
            json={"body": body},
        )
        return response.json()


def make_github(settings: Settings) -> GitHubAPI | None:
    if not (settings.github_app_id and settings.github_private_key):
        return None
    key = Path(settings.github_private_key).expanduser().read_text()
    return GitHubApp(settings.github_app_id, key, settings.github_api_url)
