"""Private sessions: each person works with their own AI; only tagged text leaves.

Private reads and writes run as the tenet_app role with tenet.user_id set, so row-level security
limits them to the caller's own rows. Agent work (routing, Capture, conflict check, Ask) runs as
tenet_agent, which has no access to private tables at all.
"""

import re
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.datastructures import State

from app.agents.capture import CaptureError, capture, check_conflicts, route
from app.agents.scope import scoped_in
from app.connectors.drive_items import attachment_view, session_attachments, share_attachments
from app.context import build_context, spine_of
from app.events import append_event
from app.findings import share_finding
from app.llm.gateway import LLMError, LLMGateway
from app.models import (
    Area,
    PrivateMessage,
    PrivateSession,
    SessionAttachment,
    Space,
    StateVersion,
    User,
)
from app.review import STAGES, Notice, ReviewError, create_proposal, require, stage_owner

HISTORY_MESSAGES = 20
ATTACHMENT_CHARS = 8_000  # per attached Doc, in your own AI's context


@asynccontextmanager
async def as_user(sessions: async_sessionmaker, user_id: uuid.UUID) -> AsyncIterator[AsyncSession]:
    """A transaction that can see only this user's private rows."""
    async with sessions() as session, session.begin():
        await session.execute(text("SET LOCAL ROLE tenet_app"))
        await session.execute(select(func.set_config("tenet.user_id", str(user_id), True)))
        yield session


@asynccontextmanager
async def as_agent(sessions: async_sessionmaker) -> AsyncIterator[AsyncSession]:
    """A transaction for agent work: private tables are off limits to this role."""
    async with sessions() as session, session.begin():
        await session.execute(text("SET LOCAL ROLE tenet_agent"))
        yield session


def tagged_text(message: str, handle: str) -> str | None:
    """The paragraphs of a message that tag @handle, and nothing else."""
    tag = re.compile(rf"(?<![\w@])@{re.escape(handle)}\b", re.IGNORECASE)
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", message) if tag.search(p)]
    return "\n\n".join(paragraphs) or None


class Reply(BaseModel):
    text: str


ASSISTANT_SYSTEM = """\
You are {name}'s own AI assistant, working privately with them on @{handle}. Nothing in this
conversation is shared with anyone. Help them think: be direct, concise, and grounded in the
team's agreed state below. When they're ready to share something, remind them that tagging
@{handle} in a message shares that paragraph, and only that paragraph, with the space."""


@dataclass
class Shared:
    tagged_text: str
    event_id: uuid.UUID
    route: str
    proposal_id: uuid.UUID | None = None
    decision_key: str | None = None
    status: str | None = None
    notes: list[str] = field(default_factory=list)
    answer: dict[str, Any] | None = None
    finding_id: uuid.UUID | None = None
    evidence: list[dict[str, Any]] = field(default_factory=list)

    def view(self) -> dict[str, Any]:
        return {
            "tagged_text": self.tagged_text,
            "event_id": str(self.event_id),
            "route": self.route,
            "finding_id": str(self.finding_id) if self.finding_id else None,
            "proposal_id": str(self.proposal_id) if self.proposal_id else None,
            "decision_key": self.decision_key,
            "status": self.status,
            "notes": self.notes,
            "answer": self.answer,
            "evidence": self.evidence,
        }


def message_view(m: PrivateMessage) -> dict[str, Any]:
    return {
        "id": str(m.id),
        "role": m.role,
        "text": m.text,
        "shared_event_id": str(m.shared_event_id) if m.shared_event_id else None,
        "created_at": m.created_at.isoformat(),
    }


async def create_session(
    state: State, user: User, space: Space, title: str = "New session"
) -> dict[str, Any]:
    async with as_user(state.sessionmaker, user.id) as s:
        ps = PrivateSession(
            owner_id=user.id, space_id=space.id, title=title.strip()[:200] or "New session"
        )
        s.add(ps)
        await s.flush()
        return {"id": str(ps.id), "title": ps.title, "space": space.handle, "messages": []}


async def list_sessions(state: State, user: User) -> list[dict[str, Any]]:
    async with as_user(state.sessionmaker, user.id) as s:
        rows = await s.execute(
            select(PrivateSession, Space.handle)
            .join(Space, Space.id == PrivateSession.space_id)
            .order_by(PrivateSession.created_at.desc())
        )
        return [
            {
                "id": str(ps.id),
                "title": ps.title,
                "space": handle,
                "created_at": ps.created_at.isoformat(),
            }
            for ps, handle in rows.all()
        ]


async def read_session(state: State, user: User, session_id: uuid.UUID) -> dict[str, Any] | None:
    async with as_user(state.sessionmaker, user.id) as s:
        ps = await s.get(PrivateSession, session_id)
        if ps is None:
            return None
        space = await s.get(Space, ps.space_id)
        messages = await s.scalars(
            select(PrivateMessage)
            .where(PrivateMessage.session_id == ps.id)
            .order_by(PrivateMessage.created_at, PrivateMessage.role.desc())
        )
        attachments = await s.scalars(
            select(SessionAttachment)
            .where(SessionAttachment.session_id == ps.id)
            .order_by(SessionAttachment.created_at)
        )
        return {
            "id": str(ps.id),
            "title": ps.title,
            "space": space.handle,
            "messages": [message_view(m) for m in messages],
            "attachments": [attachment_view(a) for a in attachments],
        }


async def post_message(
    state: State,
    user: User,
    session_id: uuid.UUID,
    message: str,
    action: str | None = None,
    attachment_ids: list[uuid.UUID] | None = None,
) -> tuple[dict[str, Any] | None, list[Notice]]:
    """attachment_ids: Docs to share along with the tagged text. Untagged messages share
    nothing; your own AI reads every Doc attached to the session either way."""
    message = message.strip()
    if not message:
        raise ReviewError("message is empty")
    async with as_user(state.sessionmaker, user.id) as s:
        ps = await s.get(PrivateSession, session_id)
        if ps is None:
            return None, []
        space = await s.get(Space, ps.space_id)
        handle, space_id = space.handle, space.id
        mine = PrivateMessage(session_id=ps.id, owner_id=user.id, role="user", text=message)
        s.add(mine)
        await s.flush()
        mine_id = mine.id
        history = list(
            await s.scalars(
                select(PrivateMessage)
                .where(PrivateMessage.session_id == ps.id)
                .order_by(PrivateMessage.created_at.desc())
                .limit(HISTORY_MESSAGES)
            )
        )[::-1]
        history_text = "\n\n".join(f"{m.role}: {m.text}" for m in history)

    attached = await session_attachments(state, user, session_id)
    chosen = [a for a in attached if attachment_ids and uuid.UUID(a["id"]) in attachment_ids]
    if attachment_ids and len(chosen) != len(set(attachment_ids)):
        raise ReviewError("some attachments aren't in this session")

    notices: list[Notice] = []
    shared: Shared | None = None
    tag = tagged_text(message, handle)
    if tag:
        shared, notices = await share(state, user, space_id, tag, action, attachments=chosen)
        async with as_user(state.sessionmaker, user.id) as s:
            (await s.get(PrivateMessage, mine_id)).shared_event_id = shared.event_id

    docs = "\n\n".join(
        f'<doc title="{a["title"]}">\n{a["text"][:ATTACHMENT_CHARS]}\n</doc>' for a in attached
    )
    reply = await assistant_reply(state, user, space_id, handle, history_text, shared, docs)
    async with as_user(state.sessionmaker, user.id) as s:
        answer = PrivateMessage(
            session_id=session_id, owner_id=user.id, role="assistant", text=reply
        )
        s.add(answer)
        await s.flush()
        saved = await s.get(PrivateMessage, mine_id)
        result = {
            "message": message_view(saved),
            "reply": message_view(answer),
            "shared": shared.view() if shared else None,
        }
    return result, notices


async def share(
    state: State,
    user: User,
    space_id: uuid.UUID,
    tag: str,
    action: str | None,
    attachments: list[dict[str, Any]] | None = None,
) -> tuple[Shared, list[Notice]]:
    """Only the tagged text (and the Docs chosen with it) crosses into the space: as an event,
    then a route to act on it."""
    llm: LLMGateway | None = state.llm
    async with as_agent(state.sessionmaker) as s:
        space = await s.get(Space, space_id)
        await require(s, user, "finding.share", space)
        event = await append_event(
            s,
            space_id=space.id,
            type="session.tagged",
            actor_id=user.id,
            target_kind="space",
            target_id=space.handle,
            payload={"text": tag},
            idempotency_key=f"tagged:{uuid.uuid4()}",
        )
        shared = Shared(tag, event.id, action or "finding")
        scope = scoped_in(tag, space.handle)
        if action is None and scope is not None:
            shared.route = "question"  # addressed to a PR or decision agent: ask it
        elif action is None:
            if llm is None:
                shared.notes.append("model gateway not configured; shared as a finding")
            else:
                try:
                    shared.route = (await route(llm, tag)).kind
                except LLMError:
                    shared.notes.append("couldn't classify the shared text; shared as a finding")

    evidence = await share_attachments(state, user, space_id, attachments or [], shared.event_id)
    shared.evidence = evidence
    if shared.route == "finding":
        async with as_agent(state.sessionmaker) as s:
            space = await s.get(Space, space_id)
            finding, notices = await share_finding(
                s,
                space=space,
                author=user,
                text=tag,
                evidence=evidence or [],
                caused_by=shared.event_id,
            )
            shared.finding_id = finding.id
        return shared, notices
    if shared.route == "decision":
        return shared, await propose_decision(state, user, space_id, shared)
    if shared.route == "status":
        async with as_agent(state.sessionmaker) as s:
            space = await s.get(Space, space_id)
            proposal, notices = await create_proposal(
                s,
                space=space,
                proposer=user,
                type="status",
                title=first_line(tag),
                content={"text": tag},
                base_version=space.head_version,
                caused_by=shared.event_id,
            )
            shared.proposal_id, shared.status = proposal.id, proposal.status
        return shared, notices
    if shared.route == "question" and llm is not None:
        from app.agents.scope import UnknownAgent, resolve
        from app.ask.ask import answer_question

        async with as_agent(state.sessionmaker) as s:
            space = await s.get(Space, space_id)
            scope = scoped_in(tag, space.handle)
            try:
                if scope is not None:
                    await resolve(s, space, scope)
                shared.answer = (await answer_question(s, llm, space, tag, scope=scope)).view()
            except UnknownAgent as exc:
                shared.notes.append(str(exc))
            except LLMError:
                shared.notes.append("couldn't answer just now")
    return shared, []


def first_line(text_: str) -> str:
    line = text_.strip().splitlines()[0]
    line = re.sub(r"@[\w-]+\s*(proposing|update|status)?:?\s*", "", line, flags=re.I).strip()
    return (line[:1].upper() + line[1:])[:120] or "Shared update"


async def propose_decision(
    state: State, user: User, space_id: uuid.UUID, shared: Shared
) -> list[Notice]:
    llm: LLMGateway | None = state.llm
    if llm is None:
        shared.notes.append("model gateway not configured; couldn't draft a decision")
        return []
    async with as_agent(state.sessionmaker) as s:
        space = await s.get(Space, space_id)
        head = await s.get(StateVersion, (space.id, space.head_version))
        decisions = head.snapshot.get("decisions", {}) if head else {}
        area_keys = list(await s.scalars(select(Area.key).where(Area.space_id == space.id)))
        context = await build_context(s, space, question=shared.tagged_text)
        try:
            draft, notes = await capture(
                llm, shared.tagged_text, context.text, area_keys, decisions
            )
        except (CaptureError, LLMError) as exc:
            shared.notes.append(f"couldn't draft a decision: {exc}")
            return []
        shared.notes += notes

        in_area = {k for k, d in decisions.items() if d["area"] == draft.area}
        against_keys = in_area | set(spine_of(decisions, set(draft.parents))) | set(draft.parents)
        against = {k: decisions[k] for k in against_keys if k in decisions}
        try:
            conflicts = await check_conflicts(llm, draft, against)
        except LLMError:
            conflicts = []
            shared.notes.append("conflict check unavailable; reviewers should check by hand")

        proposal, notices = await create_proposal(
            s,
            space=space,
            proposer=user,
            type="decision",
            title=draft.title,
            content={
                "statement": draft.statement,
                "constraints": draft.constraints,
                "parents": draft.parents,
                "area": draft.area,
                "tagged_text": shared.tagged_text,
                "conflicts": [c.model_dump() for c in conflicts],
            },
            evidence=(
                shared.evidence
                + [
                    {k: src.get(k) for k in ("kind", "id", "title", "url") if src.get(k)}
                    for src in context.sources
                    if src["kind"] == "item" and src["id"] not in {e["id"] for e in shared.evidence}
                ]
            )[: max(3, len(shared.evidence))],
            base_version=space.head_version,
            caused_by=shared.event_id,
        )
        if conflicts:
            proposal.status = "blocked"
            await append_event(
                s,
                space_id=space.id,
                type="proposal.blocked",
                actor_id=None,
                target_kind="proposal",
                target_id=str(proposal.id),
                payload={"conflicts_with": sorted({c.decision for c in conflicts})},
                idempotency_key=f"proposal:{proposal.id}:conflict",
            )
            notices = [
                Notice(
                    "blocked",
                    proposal.id,
                    [user.id],
                    {"conflicts_with": sorted({c.decision for c in conflicts})},
                )
            ]
        shared.proposal_id = proposal.id
        shared.decision_key = proposal.decision_key
        shared.status = proposal.status
    return notices


async def assistant_reply(
    state: State,
    user: User,
    space_id: uuid.UUID,
    handle: str,
    history: str,
    shared: Shared | None,
    docs: str = "",
) -> str:
    if shared is not None:
        return await share_receipt(state, space_id, handle, shared)
    llm: LLMGateway | None = state.llm
    if llm is None:
        return "Your AI isn't configured yet (set ANTHROPIC_API_KEY). Nothing was shared."
    async with as_agent(state.sessionmaker) as s:
        context = await build_context(s, await s.get(Space, space_id))
    try:
        reply = await llm.structured(
            task="private_assistant",
            tier="strong",
            system=ASSISTANT_SYSTEM.format(name=user.name, handle=handle),
            prompt=(
                f"{context.text}\n\n"
                + (f"<your_attached_docs>\n{docs}\n</your_attached_docs>\n\n" if docs else "")
                + f"<conversation>\n{history}\n</conversation>"
            ),
            schema=Reply,
            effort="medium",
        )
    except LLMError:
        return "I couldn't answer just now. Nothing was shared."
    return reply.text


async def share_receipt(state: State, space_id: uuid.UUID, handle: str, shared: Shared) -> str:
    """A plain-code receipt, so the person sees exactly what left the session."""
    lines = [f"Shared with @{handle}:", f"> {shared.tagged_text}"]
    if shared.evidence:
        lines.append("With: " + ", ".join(e["title"] for e in shared.evidence))
    if shared.decision_key and shared.status == "pending":
        async with as_agent(state.sessionmaker) as s:
            owner = await stage_owner(s, await s.get(Space, space_id), STAGES[0])
        lines.append(
            f"{shared.decision_key} is now review pending — {STAGES[0].name} "
            f"({owner.name}) reviews it first."
        )
    elif shared.decision_key and shared.status == "blocked":
        lines.append(
            f"{shared.decision_key} conflicts with an agreed decision and is held for "
            "you to revise or reopen the decision above it."
        )
    elif shared.route == "status" and shared.proposal_id:
        lines.append("Sent as a status update for review.")
    elif shared.finding_id:
        lines.append(
            "Shared as a finding: everyone in the space can see it and reply now. It isn't part "
            "of the agreed state; promote it to a proposal when it's ready."
        )
    elif shared.answer:
        lines.append(f"{shared.answer['agent']}: {shared.answer['answer']}")
    lines += [f"({note})" for note in shared.notes]
    return "\n".join(lines)
