"""Sign in with Google or Microsoft (OpenID Connect, authorization code + PKCE).

The identity provider proves the email address (and enforces MFA where the company requires it);
Tenet then decides whether that email may come in:
- an existing, active user with that email, or
- someone holding an invite for that exact email, or
- anyone whose email domain a Tenet org has verified (they join the org, in no space yet).
Free-mail domains can never be a company domain. Everyone else is refused, and the refusal audited.
"""

import base64
import hashlib
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt

from app.config import Settings

FREE_MAIL = frozenset(
    "gmail.com googlemail.com outlook.com hotmail.com live.com msn.com yahoo.com ymail.com "
    "icloud.com me.com mac.com aol.com proton.me protonmail.com gmx.com gmx.net mail.com "
    "yandex.com zoho.com fastmail.com hey.com qq.com 163.com".split()
)
# Microsoft's tenant for personal accounts; work and school accounts only.
MS_CONSUMER_TENANT = "9188040d-6c67-4c5b-b112-36a304b66dad"
FLOW_TTL = 600
CLOCK_SKEW = 60


class SignInError(Exception):
    """Sign-in refused; the message is safe to show the person."""


@dataclass(frozen=True)
class Provider:
    name: str
    label: str
    authorize_url: str
    token_url: str
    jwks_url: str
    scope: str = "openid email profile"

    def issuer_ok(self, iss: str, claims: dict[str, Any]) -> bool:
        if self.name == "google":
            return iss in ("https://accounts.google.com", "accounts.google.com")
        return iss == f"https://login.microsoftonline.com/{claims.get('tid')}/v2.0"


PROVIDERS = {
    "google": Provider(
        "google",
        "Google",
        "https://accounts.google.com/o/oauth2/v2/auth",
        "https://oauth2.googleapis.com/token",
        "https://www.googleapis.com/oauth2/v3/certs",
    ),
    "microsoft": Provider(
        "microsoft",
        "Microsoft",
        "https://login.microsoftonline.com/organizations/oauth2/v2.0/authorize",
        "https://login.microsoftonline.com/organizations/oauth2/v2.0/token",
        "https://login.microsoftonline.com/organizations/discovery/v2.0/keys",
    ),
}


@dataclass
class Identity:
    provider: str
    subject: str
    email: str
    name: str
    # Google verifies the address. Microsoft lets a tenant admin set any email, so a Microsoft
    # address counts only if Microsoft says the domain's owner verified it (xms_edov) or the org
    # itself verified the domain with Tenet.
    email_verified_by_provider: bool = True

    @property
    def domain(self) -> str:
        return self.email.rsplit("@", 1)[-1]


def pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


class OIDC:
    def __init__(self, settings: Settings, http: Callable[[], httpx.AsyncClient] | None = None):
        self.settings = settings
        self.http = http or (lambda: httpx.AsyncClient(timeout=15))
        self.clients = {
            "google": (
                settings.google_signin_client_id or settings.google_client_id,
                settings.google_signin_client_secret or settings.google_client_secret,
            ),
            "microsoft": (settings.microsoft_client_id, settings.microsoft_client_secret),
        }
        self._jwks: dict[str, tuple[float, dict[str, Any]]] = {}
        # The flow cookie's signing key: derived, so it is full-length whatever SECRET_KEY is.
        self.flow_key = hashlib.sha256(f"tenet-oidc:{settings.secret_key}".encode()).hexdigest()

    def enabled(self) -> dict[str, bool]:
        return {name: all(self.clients[name]) for name in PROVIDERS}

    def provider(self, name: str) -> Provider:
        if name not in PROVIDERS or not all(self.clients[name]):
            raise SignInError(f"sign-in with {name} isn't set up on this server")
        return PROVIDERS[name]

    def redirect_uri(self, name: str) -> str:
        return f"{self.settings.public_url.rstrip('/')}/api/auth/{name}/callback"

    # --- the flow ----------------------------------------------------------------------------

    def start(self, name: str, after: str = "/", invite: str | None = None) -> tuple[str, str]:
        """Returns (provider URL to send the browser to, signed flow cookie)."""
        provider = self.provider(name)
        state, nonce, verifier = (secrets.token_urlsafe(24) for _ in range(3))
        flow = jwt.encode(
            {
                "p": name,
                "s": state,
                "n": nonce,
                "v": verifier,
                "a": after if after.startswith("/") and not after.startswith("//") else "/",
                "i": invite,
                "exp": int(time.time()) + FLOW_TTL,
            },
            self.flow_key,
            algorithm="HS256",
        )
        params = {
            "client_id": self.clients[name][0],
            "redirect_uri": self.redirect_uri(name),
            "response_type": "code",
            "scope": provider.scope,
            "state": state,
            "nonce": nonce,
            "code_challenge": pkce_challenge(verifier),
            "code_challenge_method": "S256",
            "prompt": "select_account",
        }
        return f"{provider.authorize_url}?{urlencode(params)}", flow

    def read_flow(self, name: str, flow_cookie: str | None, state: str) -> dict[str, Any]:
        if not flow_cookie:
            raise SignInError("sign-in took too long or started in another browser; try again")
        try:
            flow = jwt.decode(flow_cookie, self.flow_key, algorithms=["HS256"])
        except jwt.PyJWTError as exc:
            raise SignInError("sign-in expired; try again") from exc
        if flow["p"] != name or not secrets.compare_digest(flow["s"], state or ""):
            raise SignInError("sign-in state didn't match; try again")
        return flow

    async def finish(self, name: str, code: str, flow: dict[str, Any]) -> Identity:
        provider = self.provider(name)
        client_id, client_secret = self.clients[name]
        async with self.http() as client:
            response = await client.post(
                provider.token_url,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": self.redirect_uri(name),
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "code_verifier": flow["v"],
                },
                headers={"Accept": "application/json"},
            )
        if response.status_code != 200:
            raise SignInError(f"{provider.label} didn't accept the sign-in")
        id_token = response.json().get("id_token")
        if not id_token:
            raise SignInError(f"{provider.label} returned no identity")
        claims = await self.verify(provider, id_token, client_id, flow["n"])
        return self.identity(provider, claims)

    async def verify(
        self, provider: Provider, id_token: str, audience: str, nonce: str
    ) -> dict[str, Any]:
        try:
            header = jwt.get_unverified_header(id_token)
            key = await self.signing_key(provider, header.get("kid", ""))
            claims = jwt.decode(
                id_token,
                key=key,
                algorithms=["RS256"],
                audience=audience,
                leeway=CLOCK_SKEW,
                options={"require": ["exp", "iat", "iss", "aud", "sub"], "verify_iss": False},
            )
        except jwt.PyJWTError as exc:
            raise SignInError(f"{provider.label} identity didn't verify ({exc})") from exc
        if not provider.issuer_ok(claims["iss"], claims):
            raise SignInError(f"{provider.label} identity came from the wrong issuer")
        if not secrets.compare_digest(str(claims.get("nonce", "")), nonce):
            raise SignInError("sign-in nonce didn't match; try again")
        return claims

    async def signing_key(self, provider: Provider, kid: str) -> Any:
        for refresh in (False, True):
            keys = await self.jwks(provider, refresh)
            for jwk in keys.get("keys", []):
                if jwk.get("kid") == kid:
                    return jwt.PyJWK(jwk).key
        raise jwt.InvalidTokenError("unknown signing key")

    async def jwks(self, provider: Provider, refresh: bool = False) -> dict[str, Any]:
        cached = self._jwks.get(provider.name)
        if cached and not refresh and cached[0] > time.time():
            return cached[1]
        async with self.http() as client:
            response = await client.get(provider.jwks_url)
        response.raise_for_status()
        keys = response.json()
        self._jwks[provider.name] = (time.time() + 3600, keys)
        return keys

    def identity(self, provider: Provider, claims: dict[str, Any]) -> Identity:
        if provider.name == "google":
            email = claims.get("email", "")
            if not claims.get("email_verified"):
                raise SignInError("your Google email isn't verified")
        else:
            if not claims.get("tid") or claims["tid"] == MS_CONSUMER_TENANT:
                raise SignInError("use a work or school Microsoft account")
            email = claims.get("email") or claims.get("preferred_username", "")
        email = email.strip().lower()
        if "@" not in email:
            raise SignInError(f"{provider.label} didn't share an email address")
        verified = provider.name == "google" or claims.get("xms_edov") in (True, 1, "1", "true")
        return Identity(provider.name, claims["sub"], email, claims.get("name") or email, verified)


def make_oidc(settings: Settings) -> OIDC:
    return OIDC(settings)
