"""Hardening: security headers, rate limits on sign-in and webhooks, production startup checks."""

import time
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.config import Settings
from app.identity import client_ip

DEFAULT_SECRET = "dev-only-secret-change-me"
# path prefix -> (requests, per seconds) per client IP
LIMITS = {"/api/auth/": (30, 60), "/webhooks/": (300, 60)}


class RateLimiter:
    """In-process token buckets per (rule, IP); with several API processes, limit at the proxy."""

    def __init__(self) -> None:
        self.buckets: dict[tuple[str, str], tuple[float, float]] = {}

    def allow(self, rule: str, ip: str, capacity: int, per: float) -> bool:
        now = time.monotonic()
        tokens, last = self.buckets.get((rule, ip), (float(capacity), now))
        tokens = min(float(capacity), tokens + (now - last) * capacity / per)
        allowed = tokens >= 1
        self.buckets[(rule, ip)] = (tokens - 1 if allowed else tokens, now)
        return allowed


def install(app: FastAPI, settings: Settings) -> None:
    limiter = RateLimiter()
    app.state.rate_limiter = limiter
    hsts = urlparse(settings.public_url).scheme == "https"

    @app.middleware("http")
    async def guard(request: Request, call_next):
        path = request.url.path
        for prefix, (capacity, per) in LIMITS.items():
            if path.startswith(prefix) and not limiter.allow(
                prefix, client_ip(request), capacity, per
            ):
                return JSONResponse(
                    {"detail": "too many requests; slow down"},
                    status_code=429,
                    headers={"Retry-After": str(int(per))},
                )
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Cache-Control", "no-store")
        if hsts:
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response


def config_problems(settings: Settings) -> list[str]:
    """What makes this configuration unsafe outside development."""
    if settings.dev:
        return []
    problems = []
    if settings.secret_key == DEFAULT_SECRET or len(settings.secret_key) < 32:
        problems.append("SECRET_KEY must be a long random value (32+ characters)")
    for name in ("public_url", "web_url"):
        if urlparse(getattr(settings, name)).scheme != "https":
            problems.append(f"{name.upper()} must be https")
    if not any(
        (
            settings.google_signin_client_id or settings.google_client_id,
            settings.microsoft_client_id,
        )
    ):
        problems.append("no sign-in provider configured (Google or Microsoft OIDC client)")
    return problems


async def database_problems(engine: AsyncEngine, settings: Settings) -> list[str]:
    if settings.dev:
        return []
    async with engine.connect() as conn:
        row = (
            await conn.execute(
                text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")
            )
        ).one()
        owns = await conn.scalar(
            text(
                "SELECT count(*) FROM pg_tables WHERE schemaname = 'public' "
                "AND tableowner = current_user"
            )
        )
    problems = []
    if row.rolsuper or row.rolbypassrls:
        problems.append("DATABASE_URL connects as a superuser; use the tenet_api role")
    if owns:
        problems.append("DATABASE_URL's role owns the tables, so row-level security can't bind it")
    return problems
