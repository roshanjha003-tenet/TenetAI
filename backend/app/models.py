"""ORM models for every HLD entity.

Agreed state (decisions, decision revisions, state versions) is written only by app.steward.
`events`, `state_versions` and `decision_revisions` are append-only, enforced by triggers
(migration 0002).
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    type_annotation_map = {dict[str, Any]: JSONB, list[Any]: JSONB, uuid.UUID: UUID(as_uuid=True)}


def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(primary_key=True, default=uuid.uuid4)


def created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


MEMBER_ROLES = ("admin", "owner", "member", "viewer", "guest")
DECISION_STATUSES = ("active", "under_review", "abandoned")
PROPOSAL_TYPES = ("status", "decision", "callback", "revision", "pivot")
PROPOSAL_STATUSES = ("pending", "approved", "rejected", "blocked")


def one_of(column: str, values: tuple[str, ...]) -> CheckConstraint:
    allowed = ", ".join(f"'{v}'" for v in values)
    return CheckConstraint(f"{column} IN ({allowed})", name=f"{column}_allowed")


class Org(Base):
    __tablename__ = "orgs"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(200))
    # Spending cap on model calls per calendar month (USD); None means no cap.
    monthly_cap_usd: Mapped[float | None] = mapped_column(Numeric(10, 2), default=50)
    created_at: Mapped[datetime] = created_at()


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = uuid_pk()
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orgs.id"))
    email: Mapped[str] = mapped_column(String(320), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    title: Mapped[str | None] = mapped_column(String(200))
    # Accepted only when ENV=dev (seeded users). Real sign-in is Google / Microsoft OIDC.
    api_token: Mapped[str | None] = mapped_column(String(200), unique=True)
    github_login: Mapped[str | None] = mapped_column(String(100), unique=True)
    slack_user_id: Mapped[str | None] = mapped_column(String(50))
    active: Mapped[bool] = mapped_column(default=True, server_default="true")
    is_org_admin: Mapped[bool] = mapped_column(default=False, server_default="false")
    # A guest from outside the org's verified domains, limited to the spaces they're invited to.
    external: Mapped[bool] = mapped_column(default=False, server_default="false")
    created_at: Mapped[datetime] = created_at()


class AuthSession(Base):
    """A signed-in browser. The cookie holds a random token; only its SHA-256 is stored."""

    __tablename__ = "auth_sessions"

    id: Mapped[uuid.UUID] = uuid_pk()
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    provider: Mapped[str] = mapped_column(String(20))  # google | microsoft | dev
    ip: Mapped[str] = mapped_column(String(64), default="")
    user_agent: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[datetime] = created_at()
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditLog(Base):
    """Append-only record of access: sign-ins, sessions, roles, invites, domains, connectors."""

    __tablename__ = "audit_log"
    __table_args__ = (one_of("outcome", ("success", "failure")),)

    id: Mapped[uuid.UUID] = uuid_pk()
    seq: Mapped[int] = mapped_column(BigInteger, Identity(always=True), unique=True)
    org_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("orgs.id"), index=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(60))
    subject: Mapped[str] = mapped_column(String(320), default="")
    outcome: Mapped[str] = mapped_column(String(10), default="success")
    reason: Mapped[str] = mapped_column(Text, default="")
    ip: Mapped[str] = mapped_column(String(64), default="")
    user_agent: Mapped[str] = mapped_column(String(300), default="")
    details: Mapped[dict[str, Any]] = mapped_column(default=dict)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OrgDomain(Base):
    __tablename__ = "org_domains"

    domain: Mapped[str] = mapped_column(String(253), primary_key=True)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orgs.id"), index=True)
    verification_token: Mapped[str] = mapped_column(String(64))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at()


class Invite(Base):
    __tablename__ = "invites"

    id: Mapped[uuid.UUID] = uuid_pk()
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orgs.id"), index=True)
    space_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("spaces.id"))
    email: Mapped[str] = mapped_column(String(320), index=True)
    role: Mapped[str] = mapped_column(String(20), default="member")
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    invited_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at()


class UsageRecord(Base):
    """One metered model call, for accounting and the per-org spending cap."""

    __tablename__ = "usage_records"

    id: Mapped[uuid.UUID] = uuid_pk()
    org_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("orgs.id"), index=True)
    task: Mapped[str] = mapped_column(String(60))
    model: Mapped[str] = mapped_column(String(60))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Numeric(12, 6), default=0)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Space(Base):
    __tablename__ = "spaces"

    id: Mapped[uuid.UUID] = uuid_pk()
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orgs.id"))
    handle: Mapped[str] = mapped_column(
        String(100), unique=True
    )  # "payments-redesign" for @payments-redesign
    name: Mapped[str] = mapped_column(String(200))
    goal: Mapped[str] = mapped_column(Text, default="")
    head_version: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = created_at()


class Area(Base):
    __tablename__ = "areas"
    __table_args__ = (UniqueConstraint("space_id", "key"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    space_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("spaces.id"))
    key: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(200))
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))


class Member(Base):
    __tablename__ = "members"
    __table_args__ = (one_of("role", MEMBER_ROLES),)

    space_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("spaces.id"), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    role: Mapped[str] = mapped_column(String(20))
    added_at: Mapped[datetime] = created_at()


class Item(Base):
    __tablename__ = "items"

    id: Mapped[uuid.UUID] = uuid_pk()
    space_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("spaces.id"))
    kind: Mapped[str] = mapped_column(String(50))  # jira | notion | slack | github | doc
    url: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(String(300))
    excerpt: Mapped[str] = mapped_column(Text, default="")
    content_hash: Mapped[str] = mapped_column(String(64))
    added_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    added_at: Mapped[datetime] = created_at()
    # Connector-backed items (Google Docs) keep the source file id and re-sync with the
    # permissions of the person who added them.
    source_id: Mapped[str | None] = mapped_column(String(200))
    synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Event(Base):
    """Append-only record of everything that happened in a space."""

    __tablename__ = "events"
    __table_args__ = (UniqueConstraint("space_id", "idempotency_key"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    seq: Mapped[int] = mapped_column(BigInteger, Identity(always=True), unique=True)
    space_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("spaces.id"), index=True)
    type: Mapped[str] = mapped_column(String(100))
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    target_kind: Mapped[str] = mapped_column(String(50))
    target_id: Mapped[str] = mapped_column(String(100))
    target_revision: Mapped[int | None] = mapped_column(Integer)
    payload: Mapped[dict[str, Any]] = mapped_column(default=dict)
    caused_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("events.id"))
    idempotency_key: Mapped[str] = mapped_column(String(200))


class StateVersion(Base):
    """A commit: snapshot of the agreed state plus a pointer to its parent."""

    __tablename__ = "state_versions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["space_id", "parent_version"], ["state_versions.space_id", "state_versions.version"]
        ),
    )

    space_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("spaces.id"), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    parent_version: Mapped[int | None] = mapped_column(Integer)
    snapshot: Mapped[dict[str, Any]] = mapped_column()
    summary: Mapped[str] = mapped_column(Text)
    committed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("events.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Decision(Base):
    """Current pointer for a decision; each revision's content lives in DecisionRevision."""

    __tablename__ = "decisions"
    __table_args__ = (UniqueConstraint("space_id", "key"), one_of("status", DECISION_STATUSES))

    id: Mapped[uuid.UUID] = uuid_pk()
    space_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("spaces.id"))
    key: Mapped[str] = mapped_column(String(20))  # "D-014"
    area_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("areas.id"))
    title: Mapped[str] = mapped_column(String(300))
    current_revision: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = created_at()


class DecisionRevision(Base):
    __tablename__ = "decision_revisions"

    decision_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("decisions.id"), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, primary_key=True)
    statement: Mapped[str] = mapped_column(Text)
    constraints: Mapped[list[Any]] = mapped_column(default=list)  # short must / must-not lines
    parents: Mapped[list[Any]] = mapped_column(default=list)  # decision keys this builds on
    evidence: Mapped[list[Any]] = mapped_column(default=list)
    proposer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    approvals: Mapped[list[Any]] = mapped_column(default=list)  # [{user_id, name, stage, at}]
    state_version: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Proposal(Base):
    __tablename__ = "proposals"
    __table_args__ = (one_of("type", PROPOSAL_TYPES), one_of("status", PROPOSAL_STATUSES))

    id: Mapped[uuid.UUID] = uuid_pk()
    space_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("spaces.id"), index=True)
    type: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(300))
    content: Mapped[dict[str, Any]] = mapped_column(default=dict)
    evidence: Mapped[list[Any]] = mapped_column(default=list)
    base_version: Mapped[int] = mapped_column(Integer)
    decision_key: Mapped[str | None] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    current_stage: Mapped[int] = mapped_column(Integer, default=1)
    proposer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    committed_version: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = created_at()
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProposalReview(Base):
    __tablename__ = "proposal_reviews"
    __table_args__ = (
        UniqueConstraint("proposal_id", "stage"),
        one_of("outcome", ("approved", "rejected")),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    proposal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proposals.id"))
    stage: Mapped[int] = mapped_column(Integer)
    stage_name: Mapped[str] = mapped_column(String(100))
    reviewer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    outcome: Mapped[str] = mapped_column(String(20))
    note: Mapped[str] = mapped_column(Text, default="")
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Pushback(Base):
    __tablename__ = "pushbacks"
    __table_args__ = (one_of("outcome", ("accepted", "overruled", "withdrawn")),)

    id: Mapped[uuid.UUID] = uuid_pk()
    proposal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proposals.id"))
    raised_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    reason: Mapped[str] = mapped_column(Text)
    evidence: Mapped[list[Any]] = mapped_column(default=list)
    outcome: Mapped[str | None] = mapped_column(String(20))
    note: Mapped[str | None] = mapped_column(Text)
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at()


class Branch(Base):
    __tablename__ = "branches"
    __table_args__ = (
        UniqueConstraint("space_id", "name"),
        one_of("status", ("open", "merged", "abandoned")),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    space_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("spaces.id"))
    name: Mapped[str] = mapped_column(String(200))
    base_version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="open")
    created_at: Mapped[datetime] = created_at()


class PRLink(Base):
    """A code PR linked to a decision, pinned to the revision it was written against."""

    __tablename__ = "pr_links"
    __table_args__ = (UniqueConstraint("repo", "pr_number", "decision_id"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    space_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("spaces.id"))
    repo: Mapped[str] = mapped_column(String(200))  # "acme-pay/payments-service"
    pr_number: Mapped[int] = mapped_column(Integer)
    decision_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("decisions.id"))
    pinned_revision: Mapped[int] = mapped_column(Integer)
    linked_at: Mapped[datetime] = created_at()


class PRCheck(Base):
    __tablename__ = "pr_checks"

    id: Mapped[uuid.UUID] = uuid_pk()
    space_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("spaces.id"))
    repo: Mapped[str] = mapped_column(String(200))
    pr_number: Mapped[int] = mapped_column(Integer)
    head_sha: Mapped[str] = mapped_column(String(64))
    result: Mapped[str] = mapped_column(String(30))  # matches | drift | stale | ... | error
    conclusion: Mapped[str] = mapped_column(String(20))  # success | failure | neutral
    title: Mapped[str] = mapped_column(String(300))
    summary: Mapped[str] = mapped_column(Text)
    findings: Mapped[list[Any]] = mapped_column(default=list)
    pr_title: Mapped[str] = mapped_column(String(300), default="")
    pr_author: Mapped[str] = mapped_column(String(100), default="")
    pr_url: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = created_at()


class Repo(Base):
    """A code repository whose PRs are checked against a space's decisions."""

    __tablename__ = "repos"

    id: Mapped[uuid.UUID] = uuid_pk()
    space_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("spaces.id"))
    full_name: Mapped[str] = mapped_column(String(200), unique=True)  # "acme-pay/payments-service"
    installation_id: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = created_at()


class StewardJob(Base):
    """The space queue: approved proposals waiting for the State steward, one lane per space."""

    __tablename__ = "steward_jobs"
    __table_args__ = (one_of("status", ("queued", "done", "blocked", "failed")),)

    id: Mapped[uuid.UUID] = uuid_pk()
    seq: Mapped[int] = mapped_column(BigInteger, Identity(always=True), unique=True)
    space_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("spaces.id"), index=True)
    proposal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proposals.id"), unique=True)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    result: Mapped[dict[str, Any]] = mapped_column(default=dict)
    created_at: Mapped[datetime] = created_at()
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PrivateSession(Base):
    """One person's private AI conversation. Row-level security: only its owner can read it."""

    __tablename__ = "private_sessions"

    id: Mapped[uuid.UUID] = uuid_pk()
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    space_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("spaces.id"))
    title: Mapped[str] = mapped_column(String(200), default="New session")
    created_at: Mapped[datetime] = created_at()


class PrivateMessage(Base):
    __tablename__ = "private_messages"
    __table_args__ = (one_of("role", ("user", "assistant")),)

    id: Mapped[uuid.UUID] = uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("private_sessions.id"), index=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    role: Mapped[str] = mapped_column(String(20))
    text: Mapped[str] = mapped_column(Text)
    # Set on a user message whose tagged text was shared; points at the shared event, not back.
    shared_event_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = created_at()


class Finding(Base):
    """Something a person deliberately shared with the space: visible to everyone at once, no
    approval needed, never part of the agreed state unless promoted to a proposal and approved."""

    __tablename__ = "findings"
    __table_args__ = (one_of("status", ("open", "promoted")),)

    id: Mapped[uuid.UUID] = uuid_pk()
    space_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("spaces.id"), index=True)
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    text: Mapped[str] = mapped_column(Text)
    evidence: Mapped[list[Any]] = mapped_column(default=list)
    mentions: Mapped[list[Any]] = mapped_column(default=list)  # decision keys and PR handles
    status: Mapped[str] = mapped_column(String(20), default="open")
    proposal_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("proposals.id"))
    event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("events.id"))
    created_at: Mapped[datetime] = created_at()


class FindingReply(Base):
    __tablename__ = "finding_replies"
    __table_args__ = (one_of("stance", ("agree", "concern", "question")),)

    id: Mapped[uuid.UUID] = uuid_pk()
    finding_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("findings.id"), index=True)
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    stance: Mapped[str] = mapped_column(String(20))
    text: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = created_at()


class SessionAttachment(Base):
    """A document attached to a private session. Private (RLS) until its owner shares it."""

    __tablename__ = "session_attachments"

    id: Mapped[uuid.UUID] = uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("private_sessions.id"), index=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    kind: Mapped[str] = mapped_column(String(30))  # gdoc
    source_id: Mapped[str] = mapped_column(String(200))
    url: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(String(300))
    text: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    shared_item_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = created_at()


class ConnectorToken(Base):
    """A person's own OAuth grant for a connector. Readable only by its owner (RLS)."""

    __tablename__ = "connector_tokens"

    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    provider: Mapped[str] = mapped_column(String(30), primary_key=True)  # google
    account_email: Mapped[str] = mapped_column(String(320), default="")
    access_token: Mapped[str] = mapped_column(Text)
    refresh_token: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    scope: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = created_at()


class WebhookDelivery(Base):
    """Every webhook delivery we accepted; a redelivery with the same id is ignored."""

    __tablename__ = "webhook_deliveries"

    source: Mapped[str] = mapped_column(String(20), primary_key=True)  # github | slack
    delivery_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    event: Mapped[str] = mapped_column(String(100))
    received_at: Mapped[datetime] = created_at()
