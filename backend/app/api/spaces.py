"""REST API for spaces, state, decisions, proposals and PR checks. Identity comes from the token."""

import hashlib
import re
import uuid
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.views import (
    check_view,
    event_view,
    item_view,
    proposal_detail,
    space_detail,
    space_view,
    user_view,
    users_by_id,
    version_view,
)
from app.auth import current_user
from app.authz import require
from app.db import get_session
from app.events import append_event
from app.models import (
    MEMBER_ROLES,
    Area,
    Decision,
    DecisionRevision,
    Event,
    Item,
    Member,
    PRCheck,
    PRLink,
    Proposal,
    Space,
    StateVersion,
    User,
)
from app.notify import dispatch
from app.review import (
    STAGES,
    Forbidden,
    NotFound,
    ReviewError,
    approve,
    create_proposal,
    process_queue,
    raise_pushback,
    reject,
    resolve_pushback,
)
from app.steward import commit

router = APIRouter()
HANDLE = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")


async def get_space(session: AsyncSession, handle: str, user: User) -> Space:
    space = await session.scalar(select(Space).where(Space.handle == handle.lstrip("@")))
    if space is None:
        raise HTTPException(404, f"no space @{handle}")
    await require(session, user, "space.read", space)
    return space


# --- me and spaces -------------------------------------------------------------------------


@router.get("/me")
async def me(
    user: User = Depends(current_user), session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    rows = await session.execute(
        select(Space, Member.role)
        .join(Member, Member.space_id == Space.id)
        .where(Member.user_id == user.id)
        .order_by(Space.created_at)
    )
    return {
        **user_view(user),
        "is_org_admin": user.is_org_admin,
        "external": user.external,
        "spaces": [{**space_view(s), "role": role} for s, role in rows.all()],
    }


@router.get("/users")
async def org_users(
    user: User = Depends(current_user), session: AsyncSession = Depends(get_session)
) -> list[dict[str, Any]]:
    await require(session, user, "org.directory")
    users = await session.scalars(
        select(User).where(User.org_id == user.org_id).order_by(User.name)
    )
    return [user_view(u) for u in users]


@router.get("/approvals")
async def my_approvals(
    user: User = Depends(current_user), session: AsyncSession = Depends(get_session)
) -> list[dict[str, Any]]:
    """Pending proposals whose current stage is yours to approve, across your spaces."""
    rows = await session.execute(
        select(Proposal, Space, Area)
        .join(Space, Space.id == Proposal.space_id)
        .join(Area, Area.space_id == Proposal.space_id)
        .where(Proposal.status == "pending", Area.owner_id == user.id)
        .order_by(Proposal.created_at)
    )
    out = []
    for proposal, space, area in rows.all():
        stage = STAGES[proposal.current_stage - 1]
        if stage.area_key == area.key:
            out.append({**await proposal_detail(session, proposal), "space": space_view(space)})
    return out


class AreaIn(BaseModel):
    key: str
    name: str
    owner_email: str


class SpaceIn(BaseModel):
    handle: str
    name: str
    goal: str = ""
    areas: list[AreaIn] = Field(default_factory=list)


@router.post("/spaces", status_code=201)
async def create_space(
    body: SpaceIn,
    request: Request,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    await require(session, user, "space.create")
    handle = body.handle.strip().lstrip("@").lower()
    if not HANDLE.match(handle):
        raise HTTPException(422, "handle: lowercase letters, digits and dashes")
    if await session.scalar(select(Space.id).where(Space.handle == handle)):
        raise HTTPException(409, f"@{handle} already exists")
    space = Space(
        org_id=user.org_id,
        handle=handle,
        name=body.name.strip() or handle,
        goal=body.goal.strip(),
        created_by=user.id,
    )
    session.add(space)
    try:
        await session.flush()
    except IntegrityError as exc:  # taken by another org, whose spaces this one can't see
        raise HTTPException(409, f"@{handle} already exists") from exc
    session.add(Member(space_id=space.id, user_id=user.id, role="admin"))
    areas = body.areas or [
        AreaIn(key=s.area_key, name=s.name.capitalize(), owner_email=user.email) for s in STAGES
    ]
    for a in areas:
        owner = await session.scalar(
            select(User).where(User.email == a.owner_email, User.org_id == user.org_id)
        )
        if owner is None:
            raise HTTPException(422, f"no one in your org has the email {a.owner_email}")
        session.add(Area(space_id=space.id, key=a.key, name=a.name, owner_id=owner.id))
        if owner.id != user.id and not await session.get(Member, (space.id, owner.id)):
            session.add(Member(space_id=space.id, user_id=owner.id, role="owner"))
    await session.flush()
    created = await append_event(
        session,
        space_id=space.id,
        type="space.created",
        actor_id=user.id,
        target_kind="space",
        target_id=handle,
        payload={"name": space.name, "goal": space.goal},
        idempotency_key=f"space:{space.id}:created",
    )
    await commit(
        session,
        space_id=space.id,
        base_version=0,
        change=lambda s: s,
        summary="Space created",
        actor_id=user.id,
        idempotency_key=f"space:{space.id}:v1",
        caused_by=created.id,
    )
    await session.commit()
    return await space_detail(session, space)


@router.get("/spaces/{handle}")
async def read_space(
    handle: str, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    space = await get_space(session, handle, user)
    detail = await space_detail(session, space)
    detail["pending_proposals"] = await session.scalar(
        select(func.count())
        .select_from(Proposal)
        .where(Proposal.space_id == space.id, Proposal.status == "pending")
    )
    return detail


class MemberIn(BaseModel):
    email: str
    role: str = "member"


@router.post("/spaces/{handle}/members", status_code=201)
async def add_member(
    handle: str,
    body: MemberIn,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    space = await get_space(session, handle, user)
    await require(session, user, "member.manage", space)
    if body.role not in MEMBER_ROLES:
        raise HTTPException(422, f"role must be one of {', '.join(MEMBER_ROLES)}")
    invitee = await session.scalar(
        select(User).where(User.email == body.email.strip().lower(), User.org_id == user.org_id)
    )
    if invitee is None:
        raise HTTPException(422, f"no one in your org has the email {body.email}")
    if await session.get(Member, (space.id, invitee.id)):
        raise HTTPException(409, f"{invitee.name} is already a member")
    session.add(Member(space_id=space.id, user_id=invitee.id, role=body.role))
    await append_event(
        session,
        space_id=space.id,
        type="member.added",
        actor_id=user.id,
        target_kind="user",
        target_id=str(invitee.id),
        payload={"name": invitee.name, "role": body.role},
        idempotency_key=f"member:{space.id}:{invitee.id}",
    )
    await session.commit()
    return {**user_view(invitee), "role": body.role}


KINDS = {
    "atlassian.net": "jira",
    "notion.so": "notion",
    "slack.com": "slack",
    "github.com": "github",
    "docs.google.com": "doc",
}


class ItemIn(BaseModel):
    url: str
    title: str = ""
    excerpt: str = ""


@router.post("/spaces/{handle}/items", status_code=201)
async def link_item(
    handle: str,
    body: ItemIn,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Pull an item in by link. Fetching is stubbed for the demo: title and excerpt are stored."""
    space = await get_space(session, handle, user)
    await require(session, user, "item.add", space)
    url = body.url.strip()
    host = urlparse(url).netloc.lower()
    if not host:
        raise HTTPException(422, "that doesn't look like a link")
    kind = next((k for suffix, k in KINDS.items() if host.endswith(suffix)), "doc")
    title = body.title.strip() or url.rstrip("/").rsplit("/", 1)[-1] or host
    item = Item(
        space_id=space.id,
        kind=kind,
        url=url,
        title=title,
        excerpt=body.excerpt.strip(),
        content_hash=hashlib.sha256((body.excerpt or url).encode()).hexdigest(),
        added_by=user.id,
    )
    session.add(item)
    await session.flush()
    await append_event(
        session,
        space_id=space.id,
        type="item.linked",
        actor_id=user.id,
        target_kind="item",
        target_id=str(item.id),
        payload={"kind": kind, "title": title, "url": url},
        idempotency_key=f"item:{item.id}:linked",
    )
    await session.commit()
    return item_view(item)


# --- agreed state ----------------------------------------------------------------------------


@router.get("/spaces/{handle}/state")
async def read_state(
    handle: str,
    version: int | None = None,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    space = await get_space(session, handle, user)
    v = await session.get(StateVersion, (space.id, version or space.head_version))
    if v is None:
        raise HTTPException(404, f"@{space.handle} has no version {version}")
    users = await users_by_id(session, {v.committed_by})
    return {**version_view(v, users), "head_version": space.head_version}


@router.get("/spaces/{handle}/versions")
async def list_versions(
    handle: str, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)
) -> list[dict[str, Any]]:
    space = await get_space(session, handle, user)
    versions = list(
        await session.scalars(
            select(StateVersion)
            .where(StateVersion.space_id == space.id)
            .order_by(StateVersion.version)
        )
    )
    users = await users_by_id(session, {v.committed_by for v in versions})
    return [version_view(v, users) for v in versions]


@router.get("/spaces/{handle}/events")
async def list_events(
    handle: str,
    limit: int = Query(50, le=500),
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    space = await get_space(session, handle, user)
    events = list(
        await session.scalars(
            select(Event).where(Event.space_id == space.id).order_by(Event.seq.desc()).limit(limit)
        )
    )
    users = await users_by_id(session, {e.actor_id for e in events})
    return [event_view(e, users) for e in events]


@router.get("/spaces/{handle}/decisions")
async def list_decisions(
    handle: str, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)
) -> list[dict[str, Any]]:
    space = await get_space(session, handle, user)
    head = await session.get(StateVersion, (space.id, space.head_version))
    decisions = (head.snapshot if head else {}).get("decisions", {})
    statuses = dict(
        (
            await session.execute(
                select(Decision.key, Decision.status).where(Decision.space_id == space.id)
            )
        ).all()
    )
    return [{**d, "status": statuses.get(k, d.get("status"))} for k, d in sorted(decisions.items())]


@router.get("/spaces/{handle}/decisions/{key}")
async def read_decision(
    handle: str,
    key: str,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    space = await get_space(session, handle, user)
    decision = await session.scalar(
        select(Decision).where(Decision.space_id == space.id, Decision.key == key.upper())
    )
    if decision is None:
        raise HTTPException(404, f"no decision {key}")
    revisions = list(
        await session.scalars(
            select(DecisionRevision)
            .where(DecisionRevision.decision_id == decision.id)
            .order_by(DecisionRevision.revision)
        )
    )
    area = await session.get(Area, decision.area_id)
    links = list(await session.scalars(select(PRLink).where(PRLink.decision_id == decision.id)))
    users = await users_by_id(session, {r.proposer_id for r in revisions} | {area.owner_id})
    return {
        "key": decision.key,
        "title": decision.title,
        "status": decision.status,
        "current_revision": decision.current_revision,
        "area": {"key": area.key, "name": area.name, "owner": user_view(users[area.owner_id])},
        "revisions": [
            {
                "revision": r.revision,
                "statement": r.statement,
                "constraints": r.constraints,
                "parents": r.parents,
                "evidence": r.evidence,
                "approvals": r.approvals,
                "proposer": user_view(users.get(r.proposer_id)),
                "state_version": r.state_version,
                "created_at": r.created_at.isoformat(),
            }
            for r in revisions
        ],
        "prs": [
            {"repo": link.repo, "number": link.pr_number, "pinned_revision": link.pinned_revision}
            for link in links
        ],
    }


# --- proposals and review ------------------------------------------------------------------


class ProposalIn(BaseModel):
    type: str = "decision"
    title: str
    content: dict[str, Any]
    base_version: int | None = None
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    decision_key: str | None = None


@router.get("/spaces/{handle}/proposals")
async def list_proposals(
    handle: str,
    status: str | None = None,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    space = await get_space(session, handle, user)
    query = select(Proposal).where(Proposal.space_id == space.id)
    if status:
        query = query.where(Proposal.status == status)
    proposals = await session.scalars(query.order_by(Proposal.created_at.desc()))
    return [await proposal_detail(session, p) for p in proposals]


@router.post("/spaces/{handle}/proposals", status_code=201)
async def propose(
    handle: str,
    body: ProposalIn,
    request: Request,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    space = await get_space(session, handle, user)
    proposal, notices = await create_proposal(
        session,
        space=space,
        proposer=user,
        type=body.type,
        title=body.title,
        content=body.content,
        base_version=body.base_version or space.head_version,
        evidence=body.evidence,
        decision_key=body.decision_key,
    )
    await session.commit()
    await dispatch(request.app.state, notices)
    return await proposal_detail(session, proposal)


async def load_proposal(session: AsyncSession, proposal_id: uuid.UUID, user: User) -> Proposal:
    proposal = await session.get(Proposal, proposal_id)
    if proposal is None:
        raise HTTPException(404, "no such proposal")
    await require(session, user, "space.read", await session.get(Space, proposal.space_id))
    return proposal


@router.get("/proposals/{proposal_id}")
async def read_proposal(
    proposal_id: uuid.UUID,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    return await proposal_detail(session, await load_proposal(session, proposal_id, user))


class NoteIn(BaseModel):
    note: str = ""


class ReasonIn(BaseModel):
    reason: str
    evidence: list[dict[str, Any]] = Field(default_factory=list)


class ResolveIn(BaseModel):
    outcome: str
    note: str = ""


@router.post("/proposals/{proposal_id}/approve")
async def approve_stage(
    proposal_id: uuid.UUID,
    body: NoteIn,
    request: Request,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    proposal = await load_proposal(session, proposal_id, user)
    notices = await approve(session, proposal_id=proposal.id, reviewer=user, note=body.note)
    await session.commit()
    # Final approval queued the proposal; the steward drains the space's lane now.
    notices += await process_queue(session, proposal.space_id)
    await session.commit()
    await dispatch(request.app.state, notices)
    await session.refresh(proposal)
    return await proposal_detail(session, proposal)


@router.post("/proposals/{proposal_id}/reject")
async def reject_proposal(
    proposal_id: uuid.UUID,
    body: ReasonIn,
    request: Request,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    proposal = await load_proposal(session, proposal_id, user)
    notices = await reject(session, proposal_id=proposal.id, reviewer=user, reason=body.reason)
    await session.commit()
    await dispatch(request.app.state, notices)
    await session.refresh(proposal)
    return await proposal_detail(session, proposal)


@router.post("/proposals/{proposal_id}/pushbacks", status_code=201)
async def push_back(
    proposal_id: uuid.UUID,
    body: ReasonIn,
    request: Request,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    proposal = await load_proposal(session, proposal_id, user)
    _, notices = await raise_pushback(
        session, proposal_id=proposal.id, user=user, reason=body.reason, evidence=body.evidence
    )
    await session.commit()
    await dispatch(request.app.state, notices)
    return await proposal_detail(session, proposal)


@router.post("/pushbacks/{pushback_id}/resolve")
async def resolve(
    pushback_id: uuid.UUID,
    body: ResolveIn,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    await resolve_pushback(
        session, pushback_id=pushback_id, user=user, outcome=body.outcome, note=body.note
    )
    await session.commit()
    return {"status": body.outcome}


# --- ask and rewind --------------------------------------------------------------------------


async def agent_scope(session: AsyncSession, space: Space, handle: str):
    from app.agents.scope import UnknownAgent, parse_agent, resolve

    scope = parse_agent(handle)
    if scope is None:
        raise HTTPException(422, "agent ids look like @space, @space/pr-284 or @space/D-014")
    if scope.space != space.handle:
        raise HTTPException(422, f"{scope.handle} isn't an agent of @{space.handle}")
    try:
        await resolve(session, space, scope)
    except UnknownAgent as exc:
        raise HTTPException(404, str(exc)) from exc
    return scope


@router.get("/spaces/{handle}/agents")
async def list_agents(
    handle: str, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    """Every agent you can ask in this space: the space, each decision, each PR."""
    from app.agents.scope import decision_agent, pr_agent

    space = await get_space(session, handle, user)
    decisions = list(
        await session.scalars(
            select(Decision).where(Decision.space_id == space.id).order_by(Decision.key)
        )
    )
    checks = list(
        await session.scalars(
            select(PRCheck).where(PRCheck.space_id == space.id).order_by(PRCheck.created_at.desc())
        )
    )
    latest: dict[int, PRCheck] = {}
    for c in checks:
        latest.setdefault(c.pr_number, c)
    links = (
        await session.execute(
            select(PRLink.pr_number, Decision.key)
            .join(Decision, Decision.id == PRLink.decision_id)
            .where(PRLink.space_id == space.id)
        )
    ).all()
    implements: dict[int, list[str]] = {}
    for number, key in links:
        implements.setdefault(number, []).append(key)
    return {
        "space": {"agent": f"@{space.handle}", "name": space.name},
        "decisions": [
            {
                "agent": decision_agent(space.handle, d.key),
                "key": d.key,
                "title": d.title,
                "status": d.status,
                "prs": sorted(n for n, keys in implements.items() if d.key in keys),
            }
            for d in decisions
        ],
        "prs": [
            {
                "agent": pr_agent(space.handle, n),
                "number": n,
                "repo": c.repo,
                "title": c.pr_title,
                "url": c.pr_url,
                "result": c.result,
                "conclusion": c.conclusion,
                "implements": sorted(implements.get(n, [])),
            }
            for n, c in sorted(latest.items())
        ],
    }


class AskIn(BaseModel):
    question: str
    area: str | None = None
    version: int | None = None
    agent: str | None = None  # "@space/pr-284" or "@space/D-014"; omitted -> the space's agent


@router.post("/spaces/{handle}/ask")
async def ask(
    handle: str,
    body: AskIn,
    request: Request,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    from app.ask.ask import answer_question
    from app.llm.gateway import LLMError

    space = await get_space(session, handle, user)
    if not body.question.strip():
        raise HTTPException(422, "ask a question")
    llm = request.app.state.llm
    if llm is None:
        raise HTTPException(503, "the model gateway isn't configured (ANTHROPIC_API_KEY)")
    if body.version is not None and not 1 <= body.version <= space.head_version:
        raise HTTPException(422, f"version must be between 1 and {space.head_version}")
    scope = await agent_scope(session, space, body.agent) if body.agent else None
    try:
        answer = await answer_question(
            session, llm, space, body.question, area=body.area, version=body.version, scope=scope
        )
    except LLMError as exc:
        raise HTTPException(502, "Tenet couldn't answer just now") from exc
    return answer.view()


@router.get("/spaces/{handle}/rewind")
async def rewind_space(
    handle: str,
    start: int = Query(1, alias="from"),
    end: int | None = Query(None, alias="to"),
    decision: str | None = None,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Read-only: what was agreed at each version between `from` and `to`, step by step."""
    from app.ask.rewind import rewind

    space = await get_space(session, handle, user)
    end = end or space.head_version
    if start > end:
        raise HTTPException(422, "from must not be after to")
    return await rewind(session, space, start, end, decision.upper() if decision else None)


# --- PR checks -------------------------------------------------------------------------------


@router.get("/spaces/{handle}/prs")
async def list_prs(
    handle: str, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)
) -> list[dict[str, Any]]:
    space = await get_space(session, handle, user)
    checks = list(
        await session.scalars(
            select(PRCheck).where(PRCheck.space_id == space.id).order_by(PRCheck.created_at.desc())
        )
    )
    latest: dict[tuple[str, int], PRCheck] = {}
    for c in checks:
        latest.setdefault((c.repo, c.pr_number), c)
    return [check_view(c) for c in latest.values()]


@router.get("/spaces/{handle}/prs/{number}")
async def read_pr(
    handle: str,
    number: int,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    space = await get_space(session, handle, user)
    checks = list(
        await session.scalars(
            select(PRCheck)
            .where(PRCheck.space_id == space.id, PRCheck.pr_number == number)
            .order_by(PRCheck.created_at.desc())
        )
    )
    if not checks:
        raise HTTPException(404, f"no checks for PR #{number}")
    rows = await session.execute(
        select(PRLink, Decision)
        .join(Decision, Decision.id == PRLink.decision_id)
        .where(PRLink.space_id == space.id, PRLink.pr_number == number)
    )
    return {
        "latest": check_view(checks[0]),
        "history": [check_view(c) for c in checks],
        "links": [
            {
                "decision": d.key,
                "title": d.title,
                "pinned_revision": link.pinned_revision,
                "current_revision": d.current_revision,
                "status": d.status,
            }
            for link, d in rows.all()
        ],
    }


def install_error_handlers(app: Any) -> None:
    from fastapi.responses import JSONResponse

    @app.exception_handler(ReviewError)
    async def review_error(request: Request, exc: ReviewError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=exc.status_code)


__all__ = ["router", "install_error_handlers", "Forbidden", "NotFound"]
