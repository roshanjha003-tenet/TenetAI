"""Findings: share what you found with the space, get responses, promote it when it's ready.

Sharing never waits on approval (vision: "Not an approval-workflow tool"). A finding is visible
to every member at once and the master agent uses it as evidence, always labelled as not agreed.
Only a promoted finding that goes through the two-stage review changes the agreed state.
"""

import re
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.views import user_view, users_by_id
from app.events import append_event
from app.models import Finding, FindingReply, Member, Space, User
from app.review import Conflict, NotFound, Notice, ReviewError, require

STANCES = ("agree", "concern", "question")
DECISION_KEY = re.compile(r"\bD-(\d{1,5})\b", re.IGNORECASE)


def mentions_in(text: str, handle: str) -> list[str]:
    """Decision keys and agent handles a finding refers to, so scoped agents can find it."""
    from app.agents.scope import SCOPED_HANDLE

    found: list[str] = []
    for number in DECISION_KEY.findall(text):
        key = f"D-{int(number):03d}"
        if key not in found:
            found.append(key)
    for match in SCOPED_HANDLE.finditer(text):
        if match.group("space").lower() == handle.lower():
            scoped = match.group("scope").lower()
            scoped = scoped.upper() if scoped.startswith("d-") else scoped
            if scoped not in found:
                found.append(scoped)
    return found


async def members_of(session: AsyncSession, space: Space) -> list[uuid.UUID]:
    return list(await session.scalars(select(Member.user_id).where(Member.space_id == space.id)))


async def share_finding(
    session: AsyncSession,
    *,
    space: Space,
    author: User,
    text: str,
    evidence: list[dict[str, Any]] | None = None,
    caused_by: uuid.UUID | None = None,
) -> tuple[Finding, list[Notice]]:
    await require(session, author, "finding.share", space)
    text = text.strip()
    if not text:
        raise ReviewError("a finding needs text")
    finding = Finding(
        space_id=space.id,
        author_id=author.id,
        text=text,
        evidence=evidence or [],
        mentions=mentions_in(text, space.handle),
    )
    session.add(finding)
    await session.flush()
    event = await append_event(
        session,
        space_id=space.id,
        type="finding.shared",
        actor_id=author.id,
        target_kind="finding",
        target_id=str(finding.id),
        payload={
            "text": text,
            "mentions": finding.mentions,
            "evidence": [e.get("title") for e in finding.evidence],
        },
        caused_by=caused_by,
        idempotency_key=f"finding:{finding.id}:shared",
    )
    finding.event_id = event.id
    others = [m for m in await members_of(session, space) if m != author.id]
    return finding, [Notice("finding_shared", None, others, {}, finding_id=finding.id)]


async def reply(
    session: AsyncSession, *, finding_id: uuid.UUID, author: User, stance: str, text: str = ""
) -> tuple[FindingReply, list[Notice]]:
    finding = await session.get(Finding, finding_id)
    if finding is None:
        raise NotFound("no such finding")
    space = await session.get(Space, finding.space_id)
    await require(session, author, "finding.reply", space)
    if stance not in STANCES:
        raise ReviewError("stance must be agree, concern or question")
    text = text.strip()
    if stance != "agree" and not text:
        raise ReviewError(f"a {stance} needs a line of text")
    row = FindingReply(finding_id=finding.id, author_id=author.id, stance=stance, text=text)
    session.add(row)
    await session.flush()
    await append_event(
        session,
        space_id=space.id,
        type="finding.replied",
        actor_id=author.id,
        target_kind="finding",
        target_id=str(finding.id),
        payload={"stance": stance, "text": text},
        caused_by=finding.event_id,
        idempotency_key=f"finding-reply:{row.id}",
    )
    notices = []
    if author.id != finding.author_id:
        notices.append(
            Notice(
                "finding_reply",
                None,
                [finding.author_id],
                {"stance": stance, "text": text, "by": author.name},
                finding_id=finding.id,
            )
        )
    return row, notices


async def mark_promoted(
    session: AsyncSession, finding: Finding, proposal_id: uuid.UUID, by: User
) -> None:
    if finding.status == "promoted":
        raise Conflict("this finding was already promoted")
    finding.status, finding.proposal_id = "promoted", proposal_id
    await append_event(
        session,
        space_id=finding.space_id,
        type="finding.promoted",
        actor_id=by.id,
        target_kind="finding",
        target_id=str(finding.id),
        payload={"proposal": str(proposal_id)},
        caused_by=finding.event_id,
        idempotency_key=f"finding:{finding.id}:promoted",
    )


async def finding_views(session: AsyncSession, findings: list[Finding]) -> list[dict[str, Any]]:
    if not findings:
        return []
    ids = [f.id for f in findings]
    replies = list(
        await session.scalars(
            select(FindingReply)
            .where(FindingReply.finding_id.in_(ids))
            .order_by(FindingReply.created_at)
        )
    )
    users = await users_by_id(
        session, {f.author_id for f in findings} | {r.author_id for r in replies}
    )
    by_finding: dict[uuid.UUID, list[FindingReply]] = {}
    for r in replies:
        by_finding.setdefault(r.finding_id, []).append(r)
    out = []
    for f in findings:
        rs = by_finding.get(f.id, [])
        out.append(
            {
                "id": str(f.id),
                "text": f.text,
                "author": user_view(users.get(f.author_id)),
                "evidence": f.evidence,
                "mentions": f.mentions,
                "status": f.status,
                "proposal_id": str(f.proposal_id) if f.proposal_id else None,
                "created_at": f.created_at.isoformat(),
                "counts": {s: sum(1 for r in rs if r.stance == s) for s in STANCES},
                "replies": [
                    {
                        "id": str(r.id),
                        "stance": r.stance,
                        "text": r.text,
                        "author": user_view(users.get(r.author_id)),
                        "created_at": r.created_at.isoformat(),
                    }
                    for r in rs
                ],
            }
        )
    return out


async def list_findings(
    session: AsyncSession, space: Space, mention: str | None = None, limit: int = 50
) -> list[Finding]:
    query = select(Finding).where(Finding.space_id == space.id)
    if mention:
        query = query.where(Finding.mentions.contains([mention]))
    return list(await session.scalars(query.order_by(Finding.created_at.desc()).limit(limit)))


async def reply_counts(session: AsyncSession, finding_ids: list[uuid.UUID]) -> dict[Any, dict]:
    rows = await session.execute(
        select(FindingReply.finding_id, FindingReply.stance, func.count())
        .where(FindingReply.finding_id.in_(finding_ids))
        .group_by(FindingReply.finding_id, FindingReply.stance)
    )
    counts: dict[Any, dict] = {}
    for fid, stance, n in rows.all():
        counts.setdefault(fid, {s: 0 for s in STANCES})[stance] = n
    return counts
