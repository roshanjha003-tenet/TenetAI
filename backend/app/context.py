"""Bounded context for model calls: compact state + spine + top evidence + the question.

Never the full history. Sizes are measured in approximate tokens (4 characters each) so every
call stays inside a fixed budget however large the space grows. Evidence is ranked with Postgres
full-text search against the question.
"""

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import Text, cast, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Area, Event, Item, Space, StateVersion

CHARS_PER_TOKEN = 4


@dataclass
class Budget:
    total_tokens: int = 24_000
    spine_share: float = 0.15
    state_share: float = 0.45

    def chars(self, share: float = 1.0) -> int:
        return int(self.total_tokens * share * CHARS_PER_TOKEN)


@dataclass
class Context:
    text: str
    sources: list[dict[str, Any]] = field(default_factory=list)


def decision_line(d: dict[str, Any], detail: bool) -> str:
    head = f"{d['key']} (revision {d['revision']}, area {d['area']}, {d['status']}): {d['title']}"
    if not detail:
        return head + "\n  Constraints: " + "; ".join(d["constraints"])
    approvers = ", ".join(f"{a['name']} ({a['stage']})" for a in d.get("approved_by", []))
    parents = ", ".join(d.get("parents", [])) or "none"
    constraints = "\n".join(f"  - {c}" for c in d["constraints"]) or "  (none)"
    return (
        f"{head}\n  Statement: {d['statement']}\n  Parents: {parents}\n"
        f"  Approved by: {approvers or 'n/a'}\n  Constraints:\n{constraints}"
    )


def take(lines: list[str], limit: int) -> list[str]:
    out, used = [], 0
    for line in lines:
        if used + len(line) > limit:
            break
        out.append(line)
        used += len(line) + 1
    return out


def spine_of(decisions: dict[str, Any], keys: set[str]) -> list[str]:
    """Keys of every decision above the given ones, nearest parents first."""
    order, seen = [], set(keys)
    queue = [p for k in keys for p in decisions.get(k, {}).get("parents", [])]
    while queue:
        key = queue.pop(0)
        if key in seen or key not in decisions:
            continue
        seen.add(key)
        order.append(key)
        queue.extend(decisions[key].get("parents", []))
    return order


async def build_context(
    session: AsyncSession,
    space: Space,
    *,
    question: str = "",
    area_key: str | None = None,
    version: int | None = None,
    budget: Budget | None = None,
) -> Context:
    budget = budget or Budget()
    v = await session.get(StateVersion, (space.id, version or space.head_version))
    snapshot = v.snapshot if v else {"decisions": {}}
    decisions = {
        k: d for k, d in snapshot.get("decisions", {}).items() if d.get("status") != "abandoned"
    }
    sources: list[dict[str, Any]] = []

    # Current state: the area's decisions in detail (or all, without an area).
    in_area = {k for k, d in decisions.items() if area_key is None or d["area"] == area_key}
    state_lines = [decision_line(decisions[k], detail=True) for k in sorted(in_area)]
    state_lines = take(state_lines, budget.chars(budget.state_share))
    sources += [
        {
            "kind": "decision",
            "id": k,
            "revision": decisions[k]["revision"],
            "title": decisions[k]["title"],
        }
        for k in sorted(in_area)
    ]

    # The spine: decisions above, statements and constraints only, capped at its share.
    spine_keys = spine_of(decisions, in_area)
    spine_lines = take(
        [decision_line(decisions[k], detail=False) for k in spine_keys],
        budget.chars(budget.spine_share),
    )
    sources += [
        {
            "kind": "decision",
            "id": k,
            "revision": decisions[k]["revision"],
            "title": decisions[k]["title"],
        }
        for k in spine_keys[: len(spine_lines)]
    ]

    status = snapshot.get("status")
    status_line = f"Latest status ({status['by']}): {status['text']}" if status else ""

    # Evidence: linked items and recent events, ranked by relevance to the question.
    used = sum(map(len, state_lines + spine_lines)) + len(status_line)
    remaining = max(budget.chars() - used - len(question), 0)
    evidence_lines: list[str] = []
    for item in await ranked_items(session, space, question):
        evidence_lines.append(f"[item {item.kind}: {item.title}] {item.excerpt}")
        sources.append({"kind": "item", "id": str(item.id), "title": item.title, "url": item.url})
    # At HEAD, everything shared since the last commit counts; an older version sees only its past.
    cap = v if v is not None and v.version != space.head_version else None
    for event in await ranked_events(session, space, question, version_cap=cap):
        if event.type == "finding.shared":
            # Shared on purpose, never approved: the model must not treat it as agreed.
            evidence_lines.append(
                f"[finding {event.target_id}, {event.at:%b %d %H:%M}, NOT AGREED] "
                f"{event.payload.get('text', '')}"
            )
            sources.append(
                {
                    "kind": "finding",
                    "id": event.target_id,
                    "title": event.payload.get("text", "")[:80],
                }
            )
        elif event.type == "finding.replied":
            evidence_lines.append(
                f"[reply on finding {event.target_id}: {event.payload.get('stance')}] "
                f"{event.payload.get('text', '')}"
            )
        else:
            evidence_lines.append(f"[event {event.type} {event.at:%b %d %H:%M}] {event.payload}")
    evidence_lines = take(evidence_lines, remaining)

    areas = list(await session.scalars(select(Area).where(Area.space_id == space.id)))
    parts = [
        f"Space @{space.handle}: {space.name}. Goal: {space.goal}",
        f"Agreed state: version {v.version if v else 0}",
        "Areas: " + ", ".join(f"{a.key} ({a.name})" for a in areas),
        "<current_state>\n"
        + ("\n".join(state_lines) or "(no decisions yet)")
        + "\n</current_state>",
    ]
    if spine_lines:
        parts.append("<decisions_above>\n" + "\n".join(spine_lines) + "\n</decisions_above>")
    if status_line:
        parts.append(status_line)
    if evidence_lines:
        parts.append("<evidence>\n" + "\n".join(evidence_lines) + "\n</evidence>")
    return Context("\n\n".join(parts), sources)


async def ranked_items(session: AsyncSession, space: Space, question: str, limit: int = 5):
    document = func.to_tsvector("english", Item.title + literal(" ") + Item.excerpt)
    query = select(Item).where(Item.space_id == space.id)
    if question.strip():
        tsquery = func.plainto_tsquery("english", question)
        rank = func.ts_rank(document, tsquery)
        query = query.order_by(rank.desc(), Item.added_at.desc())
    else:
        query = query.order_by(Item.added_at.desc())
    return list(await session.scalars(query.limit(limit)))


async def ranked_events(
    session: AsyncSession,
    space: Space,
    question: str,
    version_cap: StateVersion | None,
    limit: int = 8,
):
    shared = (
        "session.tagged",
        "proposal.created",
        "proposal.approved",
        "proposal.rejected",
        "pushback.raised",
        "pushback.resolved",
        "pr.checked",
        "finding.shared",
        "finding.replied",
    )
    query = select(Event).where(Event.space_id == space.id, Event.type.in_(shared))
    if version_cap is not None:
        query = query.where(Event.at <= version_cap.created_at)
    if question.strip():
        document = func.to_tsvector("english", cast(Event.payload, Text))
        rank = func.ts_rank(document, func.plainto_tsquery("english", question))
        query = query.order_by(rank.desc(), Event.seq.desc())
    else:
        query = query.order_by(Event.seq.desc())
    return list(await session.scalars(query.limit(limit)))
