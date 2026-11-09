"""Link a PR to the decisions it names, pinning each link to the revision current at link time."""

import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.events import append_event
from app.models import Decision, PRLink, Space

IMPLEMENTS = re.compile(r"^\s*implements\s*:\s*(.+)$", re.IGNORECASE | re.MULTILINE)
KEY = re.compile(r"\bD-(\d{1,5})\b", re.IGNORECASE)


def normalize_key(number: str) -> str:
    return f"D-{int(number):03d}"


def parse_implements(body: str | None) -> list[str]:
    """Decision keys from `Implements: D-7, D-012` lines, in order, without duplicates."""
    keys: list[str] = []
    for line in IMPLEMENTS.findall(body or ""):
        for number in KEY.findall(line):
            key = normalize_key(number)
            if key not in keys:
                keys.append(key)
    return keys


@dataclass
class Link:
    decision: Decision
    pinned_revision: int
    new: bool


async def link_pr(
    session: AsyncSession, *, space: Space, repo: str, number: int, keys: list[str]
) -> tuple[list[Link], list[str]]:
    """Returns the links (existing ones keep their pin) and keys that name no decision."""
    if not keys:
        return [], []
    decisions = {
        d.key: d
        for d in await session.scalars(
            select(Decision).where(Decision.space_id == space.id, Decision.key.in_(keys))
        )
    }
    existing = {
        link.decision_id: link
        for link in await session.scalars(
            select(PRLink).where(PRLink.repo == repo, PRLink.pr_number == number)
        )
    }
    links: list[Link] = []
    for key in keys:
        decision = decisions.get(key)
        if decision is None:
            continue
        current = existing.get(decision.id)
        if current is not None:
            links.append(Link(decision, current.pinned_revision, new=False))
            continue
        session.add(
            PRLink(
                space_id=space.id,
                repo=repo,
                pr_number=number,
                decision_id=decision.id,
                pinned_revision=decision.current_revision,
            )
        )
        await append_event(
            session,
            space_id=space.id,
            type="pr.linked",
            target_kind="pr",
            target_id=f"{repo}#{number}",
            payload={"decision": key, "pinned_revision": decision.current_revision},
            idempotency_key=f"pr-link:{repo}#{number}:{key}",
        )
        links.append(Link(decision, decision.current_revision, new=True))
    await session.flush()
    unknown = [k for k in keys if k not in decisions]
    return links, unknown
