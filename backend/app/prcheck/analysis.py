"""'Still matches': a model drafts findings, code drops invalid ones, an evaluator confirms."""

from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from app.github.diff import Diff
from app.llm.gateway import LLMGateway

# Bounded context: a diff larger than this is not analysed (the check reports "unsure").
MAX_DIFF_CHARS = 120_000


@dataclass
class DecisionContext:
    key: str
    revision: int
    title: str
    statement: str
    constraints: list[str]
    approvers: list[dict] = field(default_factory=list)  # [{name, stage}]
    linked: bool = True  # False for decisions above the linked ones (the spine)


class Finding(BaseModel):
    decision: str = Field(description="Decision key, e.g. D-014")
    constraint: str = Field(description="The constraint text, copied exactly as listed")
    file: str = Field(description="File path as shown in the diff")
    start_line: int = Field(description="First new-side line number that breaks the constraint")
    end_line: int = Field(description="Last new-side line number that breaks the constraint")
    explanation: str = Field(description="One sentence: how these lines contradict the constraint")


class Analysis(BaseModel):
    findings: list[Finding]
    confident: bool = Field(description="False if you could not tell whether the diff complies")


class Verdict(BaseModel):
    finding: int = Field(description="Index of the finding being judged")
    confirmed: bool
    reason: str


class Evaluation(BaseModel):
    verdicts: list[Verdict]


ANALYZER_SYSTEM = """\
You check whether a code change still follows decisions a team agreed on.

Report a finding only when lines added by the diff clearly contradict one listed constraint.
For each finding, copy the constraint text exactly as listed, and cite new-side line numbers
exactly as they appear in the numbered diff. Do not report style issues, missing tests, or
constraints the diff does not touch. Code that complies is not a finding. If you cannot tell
whether the diff complies, return no findings and set confident to false."""

EVALUATOR_SYSTEM = """\
You review draft findings from a decision check before anyone sees them.

For each finding, re-read the cited lines and the constraint. Confirm it only if those lines,
as written, contradict the constraint. Reject it if the lines comply, if they don't do what
the finding says, or if the contradiction depends on code not shown."""


def render_decisions(decisions: list[DecisionContext]) -> str:
    blocks = []
    for d in decisions:
        role = "linked by this PR" if d.linked else "above the linked decisions; still applies"
        constraints = "\n".join(f"  - {c}" for c in d.constraints) or "  (none)"
        blocks.append(
            f"{d.key} (revision {d.revision}, {role}): {d.title}\n"
            f"  Statement: {d.statement}\n  Constraints:\n{constraints}"
        )
    return "\n\n".join(blocks)


def analyzer_prompt(decisions: list[DecisionContext], title: str, body: str, diff: Diff) -> str:
    return (
        f"<decisions>\n{render_decisions(decisions)}\n</decisions>\n\n"
        f"<pull_request>\nTitle: {title}\n\n{body}\n</pull_request>\n\n"
        "<diff>\nNew-side line numbers; '+' marks added lines.\n"
        f"{diff.numbered()}\n</diff>"
    )


def evaluator_prompt(decisions: list[DecisionContext], findings: list[Finding], diff: Diff) -> str:
    items = []
    for i, f in enumerate(findings):
        file = diff.files[f.file]
        lo, hi = max(1, f.start_line - 5), f.end_line + 5
        snippet = "\n".join(
            f"{n:>5} {'+' if n in file.added else ' '} {file.added.get(n, file.context.get(n))}"
            for n in range(lo, hi + 1)
            if n in file.new_lines()
        )
        items.append(
            f"[{i}] {f.decision} — constraint: {f.constraint}\n"
            f"    {f.file}:{f.start_line}-{f.end_line}: {f.explanation}\n{snippet}"
        )
    return (
        f"<decisions>\n{render_decisions(decisions)}\n</decisions>\n\n"
        "<findings>\n" + "\n\n".join(items) + "\n</findings>"
    )


def valid_findings(
    findings: list[Finding], decisions: list[DecisionContext], diff: Diff
) -> list[Finding]:
    """Drop findings that cite a constraint that doesn't exist or lines that aren't in the diff."""
    constraints = {d.key: {c.strip().casefold(): c for c in d.constraints} for d in decisions}
    kept = []
    for f in findings:
        known = constraints.get(f.decision.strip().upper())
        if not known:
            continue
        exact = known.get(f.constraint.strip().casefold())
        if exact is None or not diff.has_lines(f.file, f.start_line, f.end_line):
            continue
        kept.append(
            f.model_copy(update={"decision": f.decision.strip().upper(), "constraint": exact})
        )
    return kept


@dataclass
class MatchResult:
    confident: bool
    drafted: int
    findings: list[Finding]  # confirmed, valid findings


async def still_matches(
    llm: LLMGateway, decisions: list[DecisionContext], title: str, body: str, diff: Diff
) -> MatchResult:
    analysis = await llm.structured(
        task="pr_analyzer",
        tier="strong",
        system=ANALYZER_SYSTEM,
        prompt=analyzer_prompt(decisions, title, body, diff),
        schema=Analysis,
        effort="high",
    )
    candidates = valid_findings(analysis.findings, decisions, diff)
    if not candidates:
        return MatchResult(analysis.confident, len(analysis.findings), [])

    evaluation = await llm.structured(
        task="pr_evaluator",
        tier="strong",
        system=EVALUATOR_SYSTEM,
        prompt=evaluator_prompt(decisions, candidates, diff),
        schema=Evaluation,
        effort="high",
    )
    confirmed = {v.finding for v in evaluation.verdicts if v.confirmed}
    kept = [f for i, f in enumerate(candidates) if i in confirmed]
    return MatchResult(analysis.confident, len(analysis.findings), kept)
