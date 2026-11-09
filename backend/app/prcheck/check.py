"""The PR check: is this PR still current with, and does it still match, the decisions it names?

Order: link + pin -> still current (plain code) -> still matches (model + code + evaluator).
Only a confirmed contradiction fails the check; anything uncertain is neutral (fail open).
"""

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.scope import decision_agent, pr_agent
from app.events import append_event
from app.github.diff import parse_diff
from app.llm.gateway import LLMError, LLMGateway
from app.models import Decision, DecisionRevision, PRCheck, Space, StateVersion
from app.prcheck.analysis import MAX_DIFF_CHARS, DecisionContext, Finding, still_matches
from app.prcheck.links import Link, link_pr, parse_implements

log = logging.getLogger(__name__)

CHECK_NAME = "Tenet · decisions"
CONCLUSIONS = {
    "matches": "success",
    "drift": "failure",
    "stale": "neutral",
    "under_review": "neutral",
    "orphaned": "neutral",
    "not_linked": "neutral",
    "unsure": "neutral",
    "error": "neutral",
}


@dataclass
class PRInfo:
    repo: str
    number: int
    head_sha: str
    title: str
    body: str
    author: str = ""
    url: str = ""


@dataclass
class Outcome:
    result: str
    title: str
    summary: str
    findings: list[dict[str, Any]] = field(default_factory=list)

    @property
    def conclusion(self) -> str:
        return CONCLUSIONS[self.result]


def approvers_text(approvers: list[dict]) -> str:
    names = [f"{a['name']} ({a['stage']})" for a in approvers]
    return " and ".join(names) if names else "no recorded approver"


async def decision_context(
    session: AsyncSession, decision: Decision, revision: int, linked: bool
) -> DecisionContext:
    rev = await session.get(DecisionRevision, (decision.id, revision))
    return DecisionContext(
        key=decision.key,
        revision=revision,
        title=decision.title,
        statement=rev.statement,
        constraints=list(rev.constraints),
        approvers=[{"name": a["name"], "stage": a["stage"]} for a in rev.approvals],
        linked=linked,
    )


async def spine(session: AsyncSession, space: Space, keys: list[str]) -> list[DecisionContext]:
    """Every active decision above the given ones (statements and constraints only)."""
    head = await session.get(StateVersion, (space.id, space.head_version))
    decisions = head.snapshot.get("decisions", {}) if head else {}
    seen: set[str] = set(keys)
    queue = [p for k in keys for p in decisions.get(k, {}).get("parents", [])]
    out: list[DecisionContext] = []
    while queue:
        key = queue.pop(0)
        if key in seen or key not in decisions:
            continue
        seen.add(key)
        d = decisions[key]
        if d.get("status") == "abandoned":
            continue
        out.append(
            DecisionContext(
                key=key,
                revision=d["revision"],
                title=d["title"],
                statement=d["statement"],
                constraints=d["constraints"],
                approvers=d.get("approved_by", []),
                linked=False,
            )
        )
        queue.extend(d.get("parents", []))
    return out


def still_current(links: list[Link]) -> Outcome | None:
    """Plain-code check of each link's pinned revision against the decision as it is now."""
    orphaned = [link for link in links if link.decision.status == "abandoned"]
    if orphaned:
        keys = ", ".join(link.decision.key for link in orphaned)
        return Outcome(
            "orphaned",
            f"{keys} was abandoned",
            f"This PR implements {keys}, which the team has since abandoned. Re-link the PR to the "
            "decision that replaced it.",
        )
    reviewing = [link for link in links if link.decision.status == "under_review"]
    if reviewing:
        keys = ", ".join(link.decision.key for link in reviewing)
        return Outcome(
            "under_review",
            f"{keys} is under review",
            f"{keys} has been reopened. Ask its owner before merging; the check will rerun when "
            "the review ends.",
        )
    stale = [link for link in links if link.decision.current_revision > link.pinned_revision]
    if stale:
        changes = "; ".join(
            f"{d.key} revision {link.pinned_revision} → {d.current_revision}"
            for link in stale
            for d in [link.decision]
        )
        return Outcome(
            "stale",
            "Linked decisions changed since this PR linked them",
            f"Revised since this PR linked them: {changes}. Review the change and update the PR.",
        )
    return None


def drift_outcome(pr: PRInfo, contexts: list[DecisionContext], findings: list[Finding]) -> Outcome:
    by_key = {c.key: c for c in contexts}
    first = findings[0]
    rows, out = [], []
    for f in findings:
        d = by_key[f.decision]
        lines = f"{f.file}:{f.start_line}" + (
            f"-{f.end_line}" if f.end_line != f.start_line else ""
        )
        rows.append(f"| **{f.decision}** · {f.constraint} | `{lines}` | {f.explanation} |")
        out.append(
            {
                "decision": f.decision,
                "decision_title": d.title,
                "revision": d.revision,
                "constraint": f.constraint,
                "approvers": d.approvers,
                "file": f.file,
                "start_line": f.start_line,
                "end_line": f.end_line,
                "explanation": f.explanation,
            }
        )
    d = by_key[first.decision]
    summary = (
        f"**PR #{pr.number} contradicts {first.decision}** — {d.title}, approved by "
        f"{approvers_text(d.approvers)}.\n\n"
        "| Decision · constraint | Lines | Why |\n|---|---|---|\n" + "\n".join(rows)
    )
    return Outcome("drift", f"Drift: {first.decision} — {first.constraint}"[:300], summary, out)


async def evaluate(
    session: AsyncSession,
    space: Space,
    pr: PRInfo,
    diff_text: str | None,
    llm: LLMGateway | None,
) -> Outcome:
    keys = parse_implements(pr.body)
    links, unknown = await link_pr(session, space=space, repo=pr.repo, number=pr.number, keys=keys)
    if not links:
        detail = f" ({', '.join(unknown)} not found in @{space.handle})" if unknown else ""
        return Outcome(
            "not_linked",
            "No linked decisions",
            "Add a line like `Implements: D-014` to the PR description so Tenet can check this PR "
            f"against the decisions it implements{detail}.",
        )

    current = still_current(links)
    if current is not None:
        return current

    contexts = [
        await decision_context(session, link.decision, link.pinned_revision, linked=True)
        for link in links
    ]
    contexts += await spine(session, space, [c.key for c in contexts])
    if llm is None or diff_text is None or len(diff_text) > MAX_DIFF_CHARS:
        reason = (
            "model gateway is not configured"
            if llm is None
            else "the diff couldn't be read"
            if diff_text is None
            else "the diff is larger than the check's budget"
        )
        return Outcome("unsure", "Tenet couldn't check this PR", f"No result: {reason}.")

    match = await still_matches(llm, contexts, pr.title, pr.body, parse_diff(diff_text))
    if match.findings:
        return drift_outcome(pr, contexts, match.findings)
    if not match.confident:
        return Outcome(
            "unsure", "Tenet couldn't tell", "The analysis was not confident either way; no result."
        )
    linked = [c for c in contexts if c.linked]
    lines = "\n".join(
        f"- **{c.key}** revision {c.revision} · {c.title} — "
        f"approved by {approvers_text(c.approvers)}"
        for c in linked
    )
    keys_text = ", ".join(c.key for c in linked)
    return Outcome(
        "matches",
        f"Matches {keys_text}",
        f"Linked decisions are current and no contradiction was found.\n\n{lines}",
    )


async def run_pr_check(
    session: AsyncSession,
    space: Space,
    pr: PRInfo,
    diff_text: str | None,
    llm: LLMGateway | None,
) -> PRCheck:
    try:
        async with session.begin_nested():
            outcome = await evaluate(session, space, pr, diff_text, llm)
    except LLMError as exc:
        log.warning("pr check %s#%s: model call failed: %s", pr.repo, pr.number, exc)
        outcome = Outcome(
            "unsure", "Tenet couldn't check this PR", "No result: the analysis failed."
        )
    except Exception:
        log.exception("pr check %s#%s failed", pr.repo, pr.number)
        outcome = Outcome("error", "Tenet hit an error", "No result: Tenet hit an internal error.")

    # Every PR carries its agent ID, so it can be asked about weeks later.
    agent = pr_agent(space.handle, pr.number)
    keys = parse_implements(pr.body)
    group = (
        f" · decision agents: {', '.join(decision_agent(space.handle, k) for k in keys)}"
        if keys
        else ""
    )
    outcome.summary += (
        f"\n\n---\nAgent: `{agent}`{group}. Ask it anything with `@tenet` in a comment here, "
        f"or `{agent}` in Tenet."
    )

    check = PRCheck(
        id=uuid.uuid4(),
        space_id=space.id,
        repo=pr.repo,
        pr_number=pr.number,
        head_sha=pr.head_sha,
        result=outcome.result,
        conclusion=outcome.conclusion,
        title=outcome.title,
        summary=outcome.summary,
        findings=outcome.findings,
        pr_title=pr.title,
        pr_author=pr.author,
        pr_url=pr.url,
    )
    session.add(check)
    await append_event(
        session,
        space_id=space.id,
        type="pr.checked",
        target_kind="pr",
        target_id=f"{pr.repo}#{pr.number}",
        idempotency_key=f"pr-check:{check.id}",
        payload={
            "result": outcome.result,
            "conclusion": outcome.conclusion,
            "head_sha": pr.head_sha,
            "title": outcome.title,
        },
    )
    await session.flush()
    return check


def check_run_payload(check: PRCheck, details_url: str | None = None) -> dict[str, Any]:
    annotations = [
        {
            "path": f["file"],
            "start_line": f["start_line"],
            "end_line": f["end_line"],
            "annotation_level": "failure",
            "title": f"{f['decision']}: {f['constraint']}"[:255],
            "message": f"{f['explanation']} Approved by {approvers_text(f['approvers'])}.",
        }
        for f in check.findings
    ]
    payload: dict[str, Any] = {
        "name": CHECK_NAME,
        "head_sha": check.head_sha,
        "status": "completed",
        "conclusion": check.conclusion,
        "output": {"title": check.title, "summary": check.summary, "annotations": annotations[:50]},
    }
    if details_url:
        payload["details_url"] = details_url
    return payload


async def latest_check(session: AsyncSession, repo: str, number: int) -> PRCheck | None:
    return await session.scalar(
        select(PRCheck)
        .where(PRCheck.repo == repo, PRCheck.pr_number == number)
        .order_by(PRCheck.created_at.desc())
        .limit(1)
    )
