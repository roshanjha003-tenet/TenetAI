"""Which org a transaction acts for.

Row-level security (migration 0008) shows a transaction only the rows of the org in its
`tenet.org_id` setting. Every transaction gets that setting from `current_org` when it begins: the
signed-in user's org for a request, the repo's org for a webhook, each org in turn for a background
job. With no org set, org-scoped tables look empty.

Before the org is known, a few SECURITY DEFINER lookups (`*_org` below) answer "which org is
this?" and nothing more.
"""

import hashlib
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from sqlalchemy import event, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

current_org: ContextVar[uuid.UUID | None] = ContextVar("tenet_org", default=None)


@event.listens_for(Session, "after_begin")
def scope_transaction(session, transaction, connection) -> None:
    org = current_org.get()
    connection.execute(
        text("SELECT set_config('tenet.org_id', :org, true)"), {"org": str(org) if org else ""}
    )


async def set_org(session: AsyncSession, org_id: uuid.UUID) -> None:
    """Act for this org from now on: in the open transaction and every later one."""
    current_org.set(org_id)
    await session.execute(select(func.set_config("tenet.org_id", str(org_id), True)))


@contextmanager
def org_context(org_id: uuid.UUID | None) -> Iterator[None]:
    token = current_org.set(org_id)
    try:
        yield
    finally:
        current_org.reset(token)


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


async def _lookup(session: AsyncSession, fn, arg) -> uuid.UUID | None:
    return await session.scalar(select(fn(arg)))


async def session_org(session: AsyncSession, cookie_token: str) -> uuid.UUID | None:
    return await _lookup(session, func.tenet_session_org, sha256(cookie_token))


async def dev_token_org(session: AsyncSession, token: str) -> uuid.UUID | None:
    return await _lookup(session, func.tenet_token_org, token)


async def email_org(session: AsyncSession, email: str) -> uuid.UUID | None:
    return await _lookup(session, func.tenet_email_org, email)


async def domain_org(session: AsyncSession, domain: str) -> uuid.UUID | None:
    """The org that has verified this email domain, if any."""
    return await _lookup(session, func.tenet_domain_org, domain)


async def invite_org(session: AsyncSession, invite_token: str) -> uuid.UUID | None:
    return await _lookup(session, func.tenet_invite_org, sha256(invite_token))


async def repo_org(session: AsyncSession, repo: str) -> uuid.UUID | None:
    return await _lookup(session, func.tenet_repo_org, repo)


async def user_org(session: AsyncSession, user_id: uuid.UUID) -> uuid.UUID | None:
    return await _lookup(session, func.tenet_user_org, user_id)


async def all_orgs(session: AsyncSession) -> list[uuid.UUID]:
    return list(await session.scalars(select(func.tenet_orgs())))
