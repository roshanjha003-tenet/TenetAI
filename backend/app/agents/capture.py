"""The master agent's first steps on tagged text: route it, draft it (Capture), check conflicts.

Models propose; everything they return is checked here before it becomes a proposal.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.llm.gateway import LLMGateway

MAX_CONSTRAINT_CHARS = 200


class Route(BaseModel):
    kind: Literal["decision", "status", "question", "finding"]
    reason: str


ROUTER_SYSTEM = """\
Someone tagged their team's shared space in a message. Classify what they are sharing:
- decision: proposing a choice the team should agree on (a policy, an approach, a rule)
- status: reporting progress or where something stands
- question: asking the space something ("where are we", "why", "what changed")
- finding: something they found or concluded and want the team to see and react to (results,
  observations, a direction they're exploring) without asking anyone to approve it yet"""


async def route(llm: LLMGateway, tagged_text: str) -> Route:
    return await llm.structured(
        task="router",
        tier="cheap",
        system=ROUTER_SYSTEM,
        prompt=tagged_text,
        schema=Route,
        effort="low",
        max_tokens=1024,
    )


class Draft(BaseModel):
    title: str = Field(description="Short name for the decision, under 90 characters")
    statement: str = Field(description="One or two sentences: what is decided")
    constraints: list[str] = Field(
        description="Short must / must-not lines that code and work can be checked against"
    )
    parents: list[str] = Field(description="Keys of agreed decisions this builds on, e.g. D-013")
    area: str = Field(description="Key of the area this decision belongs to")


CAPTURE_SYSTEM = """\
You turn a shared proposal into a structured decision draft for the team to review.

Write constraints as short, checkable must / must-not lines, each under 200 characters,
covering only what the proposal and its evidence actually say. Name as parents only agreed
decisions this one builds on, using their keys exactly as listed. Choose the area whose owner
should approve it, using an area key exactly as listed. Do not invent numbers or rules the
proposal doesn't contain."""


class CaptureError(Exception):
    pass


async def capture(
    llm: LLMGateway,
    tagged_text: str,
    context: str,
    area_keys: list[str],
    decisions: dict[str, Any],
) -> tuple[Draft, list[str]]:
    """Returns the validated draft and notes about anything code had to drop."""
    draft = await llm.structured(
        task="capture",
        tier="strong",
        system=CAPTURE_SYSTEM,
        prompt=f"{context}\n\n<shared_text>\n{tagged_text}\n</shared_text>",
        schema=Draft,
        effort="medium",
    )
    notes: list[str] = []
    if draft.area not in area_keys:
        raise CaptureError(f"draft names an unknown area '{draft.area}'")
    active = {k for k, d in decisions.items() if d.get("status") != "abandoned"}
    parents = []
    for p in (p.strip().upper() for p in draft.parents):
        if p in active and p not in parents:
            parents.append(p)
        elif p not in active:
            notes.append(f"dropped parent {p}: not an agreed decision")
    constraints = []
    for c in (c.strip() for c in draft.constraints):
        if not c:
            continue
        if len(c) > MAX_CONSTRAINT_CHARS:
            notes.append(f"dropped a constraint over {MAX_CONSTRAINT_CHARS} characters")
            continue
        constraints.append(c)
    if not draft.statement.strip() or not draft.title.strip():
        raise CaptureError("draft is missing a title or statement")
    clean = draft.model_copy(
        update={
            "parents": parents,
            "constraints": constraints,
            "title": draft.title.strip()[:300],
            "statement": draft.statement.strip(),
        }
    )
    return clean, notes


class Conflict(BaseModel):
    decision: str = Field(description="Key of the agreed decision the draft contradicts")
    constraint: str = Field(description="That decision's constraint, copied exactly")
    explanation: str


class ConflictReport(BaseModel):
    conflicts: list[Conflict]


CONFLICT_SYSTEM = """\
You check a draft decision against decisions the team already agreed, before it goes to review.

Report a conflict only when the draft, as written, would contradict one listed constraint of an
agreed decision. Copy that constraint exactly. A draft that narrows or builds on a decision
without contradicting it is not a conflict."""


async def check_conflicts(llm: LLMGateway, draft: Draft, against: dict[str, Any]) -> list[Conflict]:
    """Conflicts with the area's decisions and the spine, validated against what exists."""
    if not against:
        return []
    listing = "\n\n".join(
        f"{k}: {d['title']}\n" + "\n".join(f"  - {c}" for c in d["constraints"])
        for k, d in sorted(against.items())
    )
    draft_text = f"{draft.title}\nStatement: {draft.statement}\nConstraints:\n" + "\n".join(
        f"  - {c}" for c in draft.constraints
    )
    report = await llm.structured(
        task="conflict_check",
        tier="strong",
        system=CONFLICT_SYSTEM,
        prompt=f"<agreed>\n{listing}\n</agreed>\n\n<draft>\n{draft_text}\n</draft>",
        schema=ConflictReport,
        effort="medium",
    )
    valid = []
    for c in report.conflicts:
        d = against.get(c.decision.strip().upper())
        if d is None:
            continue
        exact = {x.casefold(): x for x in d["constraints"]}.get(c.constraint.strip().casefold())
        if exact is None:
            continue
        valid.append(
            c.model_copy(update={"decision": c.decision.strip().upper(), "constraint": exact})
        )
    return valid
