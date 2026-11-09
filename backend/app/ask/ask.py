"""Ask: "where are we?", "why?", "what changed?" answered from the agreed record, with sources.

The model sees a bounded context and must cite sources by the ids it was given; code drops any
citation that isn't in the context. The answer never claims more than the record holds.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.context import Budget, build_context
from app.llm.gateway import LLMGateway
from app.models import Space, StateVersion, User

if TYPE_CHECKING:
    from app.agents.scope import Scope


class AnswerOut(BaseModel):
    answer: str = Field(description="A few sentences of plain answer, no preamble")
    cited: list[str] = Field(description="Ids of the sources used, exactly as listed")


ASK_SYSTEM = """\
You answer questions about a team's work from its agreed record: decisions approved by their
owners, linked items, and the history of versions.

Answer in a few plain sentences. Say which decision each claim comes from and who approved it
(for example "D-014, approved by Maya Chen and Arjun Rao"), and when a claim comes from a
decision above another one, say so. For "what changed", walk through the versions in order.
If the record doesn't answer the question, say that instead of guessing. Findings are things
people shared that nobody has agreed to; when you use one, say it's a finding and whose it is.
Cite the ids of the sources you used, exactly as they appear in <sources>."""

SCOPED_SYSTEM = """

You are answering as {handle}, the agent for one {what}. Answer about that {what} first: why it
was made, which decisions it implements and who approved them, what its checks found, and what
has changed since. If a decision changed after the PR linked it, say so plainly."""


@dataclass
class Answer:
    question: str
    answer: str
    version: int
    sources: list[dict[str, Any]] = field(default_factory=list)
    agent: str = ""

    def view(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "answer": self.answer,
            "version": self.version,
            "agent": self.agent,
            "sources": self.sources,
        }


def source_id(src: dict[str, Any]) -> str:
    return src["id"] if src["kind"] == "decision" else f"{src['kind']}:{src['id']}"


async def version_history(session: AsyncSession, space: Space, up_to: int, limit: int = 12) -> str:
    versions = list(
        await session.scalars(
            select(StateVersion)
            .where(StateVersion.space_id == space.id, StateVersion.version <= up_to)
            .order_by(StateVersion.version.desc())
            .limit(limit)
        )
    )[::-1]
    committers = {
        u.id: u.name
        for u in await session.scalars(
            select(User).where(User.id.in_({v.committed_by for v in versions} - {None}))
        )
    }
    return "\n".join(
        f"v{v.version} ({v.created_at:%b %d %H:%M}, {committers.get(v.committed_by, 'system')}): "
        f"{v.summary}"
        for v in versions
    )


async def answer_question(
    session: AsyncSession,
    llm: LLMGateway,
    space: Space,
    question: str,
    *,
    area: str | None = None,
    version: int | None = None,
    scope: "Scope | None" = None,
) -> Answer:
    from app.agents.scope import Scope, scoped_context

    question = question.strip()
    at = version or space.head_version
    budget = Budget(total_tokens=16_000)
    system = ASK_SYSTEM
    if scope is not None and scope.kind != "space":
        context = await scoped_context(session, space, scope, budget)
        what = "pull request" if scope.kind == "pr" else "decision and the PRs implementing it"
        system += SCOPED_SYSTEM.format(handle=scope.handle, what=what)
        at = space.head_version
    else:
        scope = Scope(space.handle, "space")
        context = await build_context(
            session, space, question=question, area_key=area, version=at, budget=budget
        )
    by_id = {source_id(s): s for s in context.sources}
    listing = "\n".join(f"- {sid}: {s.get('title', '')}" for sid, s in by_id.items())
    history = await version_history(session, space, at)
    out = await llm.structured(
        task="ask",
        tier="strong",
        system=system,
        prompt=(
            f"{context.text}\n\n<versions>\n{history}\n</versions>\n\n"
            f"<sources>\n{listing}\n</sources>\n\n<question>\n{question}\n</question>"
        ),
        schema=AnswerOut,
        effort="medium",
    )
    cited = [by_id[c.strip()] for c in out.cited if c.strip() in by_id]
    seen, sources = set(), []
    for s in cited:
        key = source_id(s)
        if key not in seen:
            seen.add(key)
            sources.append(s)
    return Answer(question, out.answer.strip(), at, sources, scope.handle)


def as_markdown(answer: Answer, web_url: str, handle: str) -> str:
    lines = [answer.answer, ""]
    if answer.sources:
        refs = []
        for s in answer.sources:
            if s["kind"] == "decision":
                refs.append(
                    f"[{s['id']} rev {s['revision']}]({web_url}/spaces/{handle}/decisions/"
                    f"{s['id']}) {s['title']}"
                )
            elif s.get("url"):
                refs.append(f"[{s['title']}]({s['url']})")
            else:
                refs.append(s.get("title", s["id"]))
        lines.append("**Sources:** " + " · ".join(refs))
    agent = answer.agent or f"@{handle}"
    lines.append(
        f"<sub>{agent} · @{handle} at v{answer.version} · answered by Tenet from the agreed "
        f"record · ask this agent again any time with `@tenet` here or `{agent}` in Tenet</sub>"
    )
    return "\n".join(lines)
