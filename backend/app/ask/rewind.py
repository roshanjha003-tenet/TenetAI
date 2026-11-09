"""Rewind: a read-only, step-by-step view of how the agreed state moved between versions."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.views import event_view, user_view, users_by_id
from app.models import Event, Space, StateVersion


def changes(before: dict[str, Any], after: dict[str, Any]) -> list[dict[str, Any]]:
    a, b = before.get("decisions", {}), after.get("decisions", {})
    out = []
    for key in sorted(set(a) | set(b)):
        if key not in a:
            out.append({"key": key, "change": "added", "decision": b[key]})
        elif key not in b:
            out.append({"key": key, "change": "removed", "decision": a[key]})
        elif a[key] != b[key]:
            kind = "abandoned" if b[key].get("status") == "abandoned" else "revised"
            out.append({"key": key, "change": kind, "decision": b[key], "previous": a[key]})
    if before.get("status") != after.get("status") and after.get("status"):
        out.append({"key": "status", "change": "status", "status": after["status"]})
    return out


async def rewind(
    session: AsyncSession, space: Space, start: int, end: int, decision: str | None = None
) -> dict[str, Any]:
    start, end = max(1, start), min(end, space.head_version)
    versions = list(
        await session.scalars(
            select(StateVersion)
            .where(
                StateVersion.space_id == space.id,
                StateVersion.version >= max(1, start - 1),
                StateVersion.version <= end,
            )
            .order_by(StateVersion.version)
        )
    )
    events = list(
        await session.scalars(select(Event).where(Event.space_id == space.id).order_by(Event.seq))
    )
    users = await users_by_id(
        session, {v.committed_by for v in versions} | {e.actor_id for e in events}
    )
    by_version: dict[int, StateVersion] = {v.version: v for v in versions}

    steps = []
    for n in range(start, end + 1):
        v = by_version.get(n)
        if v is None:
            continue
        previous = by_version.get(n - 1)
        before = previous.snapshot if previous else {"decisions": {}}
        diff = changes(before, v.snapshot)
        if decision:
            diff = [c for c in diff if c["key"] == decision]
        window = [
            e
            for e in events
            if (previous is None or e.at > previous.created_at)
            and e.at <= v.created_at
            and e.type not in ("state.committed", "decision.created", "decision.revised")
        ]
        steps.append(
            {
                "version": v.version,
                "parent_version": v.parent_version,
                "summary": v.summary,
                "at": v.created_at.isoformat(),
                "committed_by": user_view(users.get(v.committed_by)),
                "changes": diff,
                "agreed": v.snapshot.get("decisions", {}),
                "events": [event_view(e, users) for e in window],
            }
        )
    return {
        "space": space.handle,
        "from": start,
        "to": end,
        "head_version": space.head_version,
        "decision": decision,
        "steps": steps,
    }
