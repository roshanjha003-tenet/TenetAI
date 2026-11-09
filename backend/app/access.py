"""Who gets in: admitting a verified identity, invites, and verified email domains.

Every function here leaves the transaction acting for the org it admitted the person to.
"""

import secrets
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.events import append_event
from app.identity import audit, hash_token
from app.models import MEMBER_ROLES, Invite, Member, OrgDomain, Space, User
from app.oidc import FREE_MAIL, Identity, SignInError
from app.review import Conflict, NotFound, ReviewError
from app.tenancy import domain_org, email_org, invite_org, set_org

INVITE_DAYS = 7
TXT_PREFIX = "tenet-verification="
TxtLookup = Callable[[str], Awaitable[list[str]]]


def now() -> datetime:
    return datetime.now(UTC)


def domain_of(email: str) -> str:
    return email.rsplit("@", 1)[-1].lower()


async def company_org(session: AsyncSession, email: str) -> uuid.UUID | None:
    domain = domain_of(email)
    return None if domain in FREE_MAIL else await domain_org(session, domain)


async def admit(
    session: AsyncSession,
    identity: Identity,
    *,
    invite_token: str | None = None,
    request: Request | None = None,
) -> User:
    """The user this verified identity signs in as, or SignInError (audited by the caller)."""
    owner = await company_org(session, identity.email)

    def trusted_for(org: uuid.UUID) -> bool:
        return identity.email_verified_by_provider or owner == org

    if invite_token:
        org = await invite_org(session, invite_token)
        if org is None:
            raise SignInError("that invite link isn't valid")
        await set_org(session, org)
        if not trusted_for(org):
            raise SignInError("your Microsoft account's email isn't verified for this org")
        return await accept_invite(session, invite_token, identity.email, identity.name, request)

    org = await email_org(session, identity.email)
    if org is not None:
        await set_org(session, org)
        if not trusted_for(org):
            raise SignInError("your Microsoft account's email isn't verified for this org")
        user = await session.scalar(select(User).where(User.email == identity.email))
        if user is None or not user.active:
            raise SignInError("your Tenet account is turned off; ask your org admin")
        return user

    if owner is not None:
        await set_org(session, owner)
        user = User(org_id=owner, email=identity.email, name=identity.name[:200])
        session.add(user)
        await session.flush()
        await audit(
            session,
            "user.joined",
            request=request,
            actor=user,
            subject=user.email,
            details={"via": "verified domain", "domain": identity.domain},
        )
        return user

    raise SignInError(f"{identity.email} hasn't been invited to Tenet; ask your org admin")


# --- invites ---------------------------------------------------------------------------------


async def create_invite(
    session: AsyncSession,
    admin: User,
    email: str,
    *,
    space: Space | None = None,
    role: str = "member",
    request: Request | None = None,
) -> tuple[Invite, str]:
    email = email.strip().lower()
    if "@" not in email:
        raise ReviewError("that isn't an email address")
    if role not in MEMBER_ROLES:
        raise ReviewError(f"role must be one of {', '.join(MEMBER_ROLES)}")
    existing = await email_org(session, email)
    if existing is not None and existing != admin.org_id:
        raise Conflict(f"{email} already belongs to another Tenet org")
    token = secrets.token_urlsafe(32)
    invite = Invite(
        org_id=admin.org_id,
        space_id=space.id if space else None,
        email=email,
        role=role,
        token_hash=hash_token(token),
        invited_by=admin.id,
        expires_at=now() + timedelta(days=INVITE_DAYS),
    )
    session.add(invite)
    await session.flush()
    await audit(
        session,
        "invite.created",
        request=request,
        actor=admin,
        subject=email,
        details={"space": space.handle if space else None, "role": role},
    )
    return invite, token


async def accept_invite(
    session: AsyncSession, token: str, email: str, name: str, request: Request | None = None
) -> User:
    """Accept as `email`, which the identity provider (or the signed-in session) proved."""
    invite = await session.scalar(select(Invite).where(Invite.token_hash == hash_token(token)))
    if invite is None:
        raise SignInError("that invite link isn't valid")
    if invite.accepted_at is not None:
        raise SignInError("that invite was already used")
    if invite.expires_at <= now():
        raise SignInError("that invite has expired; ask for a new one")
    if invite.email != email.lower():
        raise SignInError(f"this invite is for {invite.email}; sign in with that account")

    user = await session.scalar(select(User).where(User.email == invite.email))
    if user is None:
        external = await company_org(session, invite.email) != invite.org_id
        user = User(org_id=invite.org_id, email=invite.email, name=name[:200], external=external)
        session.add(user)
        try:
            await session.flush()
        except IntegrityError as exc:
            raise SignInError(f"{invite.email} already belongs to another Tenet org") from exc
    elif not user.active:
        raise SignInError("your Tenet account is turned off; ask your org admin")

    if (
        invite.space_id is not None
        and await session.get(Member, (invite.space_id, user.id)) is None
    ):
        session.add(Member(space_id=invite.space_id, user_id=user.id, role=invite.role))
        await append_event(
            session,
            space_id=invite.space_id,
            type="member.added",
            actor_id=invite.invited_by,
            target_kind="user",
            target_id=str(user.id),
            payload={"name": user.name, "role": invite.role, "via": "invite"},
            idempotency_key=f"member:{invite.space_id}:{user.id}",
        )
    invite.accepted_at = now()
    await audit(
        session,
        "invite.accepted",
        request=request,
        actor=user,
        subject=invite.email,
        details={"invite": str(invite.id)},
    )
    return user


# --- domains ---------------------------------------------------------------------------------


async def add_domain(
    session: AsyncSession, admin: User, domain: str, request: Request | None = None
) -> OrgDomain:
    domain = domain.strip().lower().lstrip("@")
    if "." not in domain or "/" in domain or " " in domain:
        raise ReviewError("enter a domain like acmepay.com")
    if domain in FREE_MAIL:
        raise ReviewError(f"{domain} is a public email provider, not a company domain")
    row = OrgDomain(domain=domain, org_id=admin.org_id, verification_token=secrets.token_hex(16))
    try:
        async with session.begin_nested():
            session.add(row)
    except IntegrityError as exc:
        raise Conflict(f"{domain} is already claimed") from exc
    await audit(session, "domain.added", request=request, actor=admin, subject=domain)
    return row


async def verify_domain(
    session: AsyncSession, admin: User, domain: str, lookup: TxtLookup, request=None
) -> OrgDomain:
    row = await session.get(OrgDomain, domain.strip().lower())
    if row is None:
        raise NotFound(f"no domain {domain}")
    if row.verified_at is None:
        try:
            records = await lookup(row.domain)
        except Exception:
            records = []
        if f"{TXT_PREFIX}{row.verification_token}" not in [r.strip('"') for r in records]:
            await audit(
                session,
                "domain.verified",
                request=request,
                actor=admin,
                subject=row.domain,
                outcome="failure",
                reason="TXT record not found",
            )
            raise ReviewError(
                f"no TXT record {TXT_PREFIX}{row.verification_token} on {row.domain} yet; "
                "DNS changes can take a few minutes"
            )
        row.verified_at = now()
        await audit(session, "domain.verified", request=request, actor=admin, subject=row.domain)
    return row


async def dns_txt(domain: str) -> list[str]:
    import dns.asyncresolver

    answer = await dns.asyncresolver.resolve(domain, "TXT", lifetime=5)
    return [b"".join(r.strings).decode() for r in answer]
