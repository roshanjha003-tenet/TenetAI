"""Agent IDs: the space's master agent (@space), one per PR (@space/pr-284) and one per decision
(@space/D-014), which covers every PR that implements it.

An agent is not a process: it's a scope and a retrieval filter over the same event log and state
(HLD, "Master agents and child agents"). Because the log is append-only, asking a PR's agent
weeks later still gets the record as it was, plus anything that changed since.
"""

import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.context import Budget, Context, decision_line, spine_of, take
from app.models import (
    Decision,
    DecisionRevision,
    Finding,
    PRCheck,
    PRLink,
    Proposal,
    ProposalReview,
    Pushback,
    Space,
    StateVersion,
    User,
)

SCOPED_HANDLE = re.compile(
    r"(?<![\w@])@(?P<space>[a-z0-9][a-z0-9-]{1,62})/(?P<scope>pr-\d{1,7}|d-\d{1,5})\b",
    re.IGNORECASE,
)
ANY_HANDLE = re.compile(
    r"^@?(?P<space>[a-z0-9][a-z0-9-]{1,62})(?:/(?P<scope>pr-\d{1,7}|d-\d{1,5}))?$",
    re.IGNORECASE,
)


class UnknownAgent(Exception):
    pass


@dataclass(frozen=True)
class Scope:
    space: str
    kind: str  # space | pr | decision
    pr_number: int | None = None
    decision_key: str | None = None

    @property
    def handle(self) -> str:
        if self.kind == "pr":
            return f"@{self.space}/pr-{self.pr_number}"
        if self.kind == "decision":
            return f"@{self.space}/{self.decision_key}"
        return f"@{self.space}"


def parse_agent(value: str) -> Scope | None:
    match = ANY_HANDLE.match(value.strip())
    if not match:
        return None
    space, scoped = match.group("space").lower(), match.group("scope")
    if not scoped:
        return Scope(space, "space")
    if scoped.lower().startswith("pr-"):
        return Scope(space, "pr", pr_number=int(scoped[3:]))
    return Scope(space, "decision", decision_key=f"D-{int(scoped[2:]):03d}")


def scoped_in(text: str, space: str) -> Scope | None:
    """The first PR or decision agent of this space that a piece of text addresses."""
    for match in SCOPED_HANDLE.finditer(text):
        if match.group("space").lower() == space.lower():
            return parse_agent(match.group(0))
    return None


def pr_agent(space: str, number: int) -> str:
    return Scope(space, "pr", pr_number=number).handle


def decision_agent(space: str, key: str) -> str:
    return Scope(space, "decision", decision_key=key).handle


async def resolve(session: AsyncSession, space: Space, scope: Scope) -> None:
    if scope.kind == "pr":
        found = await session.scalar(
            select(PRCheck.id)
            .where(PRCheck.space_id == space.id, PRCheck.pr_number == scope.pr_number)
            .limit(1)
        ) or await session.scalar(
            select(PRLink.id)
            .where(PRLink.space_id == space.id, PRLink.pr_number == scope.pr_number)
            .limit(1)
        )
        if not found:
            raise UnknownAgent(f"{scope.handle}: Tenet hasn't seen PR #{scope.pr_number}")
    elif scope.kind == "decision":
        found = await session.scalar(
            select(Decision.id).where(
                Decision.space_id == space.id, Decision.key == scope.decision_key
            )
        )
        if not found:
            raise UnknownAgent(f"{scope.handle}: no decision {scope.decision_key}")


# --- scoped context ----------------------------------------------------------------------


def revision_text(key: str, title: str, rev: DecisionRevision, users: dict) -> str:
    approvers = ", ".join(f"{a['name']} ({a['stage']})" for a in rev.approvals) or "n/a"
    constraints = "\n".join(f"    - {c}" for c in rev.constraints) or "    (none)"
    return (
        f"{key} revision {rev.revision}: {title}\n  Statement: {rev.statement}\n"
        f"  Parents: {', '.join(rev.parents) or 'none'}\n  Approved by: {approvers}\n"
        f"  Constraints:\n{constraints}"
    )


def check_text(c: PRCheck) -> str:
    lines = [
        f"- {c.created_at:%b %d %H:%M} PR #{c.pr_number} ({c.repo} @ {c.head_sha[:7]}): "
        f"{c.result} / {c.conclusion} — {c.title}"
    ]
    for f in c.findings:
        lines.append(
            f"    finding: {f['decision']} · {f['constraint']} · "
            f"{f['file']}:{f['start_line']}-{f['end_line']} · {f['explanation']}"
        )
    return "\n".join(lines)


async def findings_text(
    session: AsyncSession, space: Space, mentions: list[str], limit: int = 5
) -> tuple[list[str], list[dict[str, Any]]]:
    if not mentions:
        return [], []
    query = select(Finding).where(Finding.space_id == space.id)
    rows = list(await session.scalars(query.order_by(Finding.created_at.desc()).limit(200)))
    wanted = {m.lower() for m in mentions}
    hits = [f for f in rows if wanted & {m.lower() for m in f.mentions}][:limit]
    authors = {
        u.id: u.name
        for u in await session.scalars(
            select(User).where(User.id.in_({f.author_id for f in hits} or {None}))
        )
    }
    lines = [
        f"[finding by {authors.get(f.author_id, '?')}, {f.created_at:%b %d}, not agreed, "
        f"{f.status}] {f.text}"
        for f in hits
    ]
    sources = [{"kind": "finding", "id": str(f.id), "title": f.text[:80]} for f in hits]
    return lines, sources


async def spine_lines(
    session: AsyncSession, space: Space, keys: set[str], budget: Budget
) -> tuple[list[str], dict[str, Any]]:
    head = await session.get(StateVersion, (space.id, space.head_version))
    decisions = head.snapshot.get("decisions", {}) if head else {}
    order = spine_of(decisions, keys)
    lines = take(
        [decision_line(decisions[k], detail=False) for k in order], budget.chars(budget.spine_share)
    )
    return lines, decisions


async def pr_context(
    session: AsyncSession, space: Space, number: int, budget: Budget | None = None
) -> Context:
    budget = budget or Budget()
    checks = list(
        await session.scalars(
            select(PRCheck)
            .where(PRCheck.space_id == space.id, PRCheck.pr_number == number)
            .order_by(PRCheck.created_at.desc())
            .limit(6)
        )
    )
    rows = (
        await session.execute(
            select(PRLink, Decision)
            .join(Decision, Decision.id == PRLink.decision_id)
            .where(PRLink.space_id == space.id, PRLink.pr_number == number)
        )
    ).all()
    sources: list[dict[str, Any]] = []
    latest = checks[0] if checks else None
    repo = latest.repo if latest else (rows[0][0].repo if rows else "")
    header = f"PR #{number} in {repo}"
    if latest:
        header += f": {latest.pr_title} (by {latest.pr_author or 'unknown'}) {latest.pr_url}"
        sources.append(
            {"kind": "pr", "id": f"{repo}#{number}", "title": latest.pr_title, "url": latest.pr_url}
        )

    decision_parts, keys = [], set()
    for link, decision in rows:
        keys.add(decision.key)
        pinned = await session.get(DecisionRevision, (decision.id, link.pinned_revision))
        part = ["Linked at " + revision_text(decision.key, decision.title, pinned, {})]
        if decision.current_revision != link.pinned_revision:
            current = await session.get(DecisionRevision, (decision.id, decision.current_revision))
            part.append(
                "CHANGED SINCE THIS PR LINKED IT. Now "
                + revision_text(decision.key, decision.title, current, {})
            )
        if decision.status != "active":
            part.append(f"{decision.key} is now {decision.status}.")
        decision_parts.append("\n".join(part))
        sources.append(
            {
                "kind": "decision",
                "id": decision.key,
                "revision": link.pinned_revision,
                "title": decision.title,
            }
        )

    spine, _ = await spine_lines(session, space, keys, budget)
    origin = await origin_lines(session, space, keys)
    found, found_sources = await findings_text(session, space, [f"pr-{number}", *keys])
    sources += found_sources

    parts = [
        f"Agent: {pr_agent(space.handle, number)} — the record of one pull request in "
        f"@{space.handle} (agreed state now v{space.head_version}).",
        header,
        "<decisions_this_pr_implements>\n"
        + ("\n\n".join(decision_parts) or "(none linked)")
        + "\n</decisions_this_pr_implements>",
        "<check_history>\n"
        + (
            "\n".join(take([check_text(c) for c in checks], budget.chars(0.25)))
            or "(no checks yet)"
        )
        + "\n</check_history>",
    ]
    if spine:
        parts.append("<decisions_above>\n" + "\n".join(spine) + "\n</decisions_above>")
    if origin:
        parts.append("<how_it_started>\n" + "\n".join(origin) + "\n</how_it_started>")
    if found:
        parts.append("<findings>\n" + "\n".join(take(found, budget.chars(0.15))) + "\n</findings>")
    return Context("\n\n".join(parts), sources)


async def origin_lines(session: AsyncSession, space: Space, keys: set[str]) -> list[str]:
    """How the decisions came about: the shared text, the proposer, reviews and pushbacks."""
    if not keys:
        return []
    proposals = list(
        await session.scalars(
            select(Proposal)
            .where(Proposal.space_id == space.id, Proposal.decision_key.in_(keys))
            .order_by(Proposal.created_at)
        )
    )
    ids = [p.id for p in proposals]
    reviews = list(
        await session.scalars(
            select(ProposalReview)
            .where(ProposalReview.proposal_id.in_(ids or [None]))
            .order_by(ProposalReview.stage)
        )
    )
    pushbacks = list(
        await session.scalars(select(Pushback).where(Pushback.proposal_id.in_(ids or [None])))
    )
    names = {
        u.id: u.name
        for u in await session.scalars(
            select(User).where(
                User.id.in_(
                    {p.proposer_id for p in proposals}
                    | {r.reviewer_id for r in reviews}
                    | {p.raised_by for p in pushbacks}
                    or {None}
                )
            )
        )
    }
    lines = []
    for p in proposals:
        shared = p.content.get("tagged_text")
        lines.append(
            f"{p.decision_key} proposed by {names.get(p.proposer_id)} on "
            f"{p.created_at:%b %d %H:%M} ({p.status})" + (f': "{shared}"' if shared else "")
        )
        for r in (r for r in reviews if r.proposal_id == p.id):
            lines.append(
                f"  stage {r.stage} {r.stage_name}: {r.outcome} by "
                f"{names.get(r.reviewer_id)} {r.at:%b %d %H:%M}"
                + (f' — "{r.note}"' if r.note else "")
            )
        for pb in (pb for pb in pushbacks if pb.proposal_id == p.id):
            lines.append(
                f"  pushback by {names.get(pb.raised_by)}: {pb.reason} "
                f"→ {pb.outcome or 'open'}" + (f" ({pb.note})" if pb.note else "")
            )
    return lines


async def decision_context(
    session: AsyncSession, space: Space, key: str, budget: Budget | None = None
) -> Context:
    budget = budget or Budget()
    decision = await session.scalar(
        select(Decision).where(Decision.space_id == space.id, Decision.key == key)
    )
    revisions = list(
        await session.scalars(
            select(DecisionRevision)
            .where(DecisionRevision.decision_id == decision.id)
            .order_by(DecisionRevision.revision)
        )
    )
    sources: list[dict[str, Any]] = [
        {
            "kind": "decision",
            "id": key,
            "revision": decision.current_revision,
            "title": decision.title,
        }
    ]
    links = list(
        await session.scalars(
            select(PRLink).where(PRLink.decision_id == decision.id).order_by(PRLink.pr_number)
        )
    )
    pr_lines = []
    for link in links:
        latest = await session.scalar(
            select(PRCheck)
            .where(PRCheck.repo == link.repo, PRCheck.pr_number == link.pr_number)
            .order_by(PRCheck.created_at.desc())
            .limit(1)
        )
        line = f"PR #{link.pr_number} ({link.repo}) linked revision {link.pinned_revision}"
        if latest:
            line = (
                f'{line}: "{latest.pr_title}" by {latest.pr_author} — latest check '
                f"{latest.result} / {latest.conclusion}: {latest.title}"
            )
            for f in latest.findings:
                line += (
                    f"\n    finding: {f['constraint']} at "
                    f"{f['file']}:{f['start_line']}-{f['end_line']} — {f['explanation']}"
                )
            sources.append(
                {
                    "kind": "pr",
                    "id": f"{link.repo}#{link.pr_number}",
                    "title": latest.pr_title,
                    "url": latest.pr_url,
                }
            )
        pr_lines.append(line)

    spine, _ = await spine_lines(session, space, {key}, budget)
    origin = await origin_lines(session, space, {key})
    found, found_sources = await findings_text(session, space, [key])
    sources += found_sources
    history = take(
        [revision_text(key, decision.title, r, {}) for r in revisions][::-1], budget.chars(0.3)
    )[::-1]
    parts = [
        f"Agent: {decision_agent(space.handle, key)} — decision {key} in @{space.handle} and every "
        f"PR that implements it (agreed state now v{space.head_version}; {key} is "
        f"{decision.status}, current revision {decision.current_revision}).",
        "<revisions>\n" + "\n\n".join(history) + "\n</revisions>",
        "<prs>\n"
        + ("\n".join(take(pr_lines, budget.chars(0.25))) or "(no PRs linked)")
        + "\n</prs>",
    ]
    if spine:
        parts.append("<decisions_above>\n" + "\n".join(spine) + "\n</decisions_above>")
    if origin:
        parts.append("<how_it_was_decided>\n" + "\n".join(origin) + "\n</how_it_was_decided>")
    if found:
        parts.append("<findings>\n" + "\n".join(take(found, budget.chars(0.15))) + "\n</findings>")
    return Context("\n\n".join(parts), sources)


async def scoped_context(
    session: AsyncSession, space: Space, scope: Scope, budget: Budget | None = None
) -> Context:
    if scope.kind == "pr":
        return await pr_context(session, space, scope.pr_number, budget)
    return await decision_context(session, space, scope.decision_key, budget)
