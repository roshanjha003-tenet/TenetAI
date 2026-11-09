"""@tenet in a PR comment: answer from the agreed record and reply on the PR."""

import logging
import re
from typing import Any

from sqlalchemy import select
from starlette.datastructures import State

from app.agents.scope import Scope, UnknownAgent, resolve, scoped_in
from app.ask.ask import answer_question, as_markdown
from app.llm.gateway import LLMError
from app.models import Repo, Space
from app.sessions import as_agent
from app.tenancy import org_context

log = logging.getLogger(__name__)
MENTION = re.compile(r"(?<![\w@])@tenet\b[:,]?\s*", re.IGNORECASE)


def question_from(body: str) -> str | None:
    match = MENTION.search(body or "")
    if not match:
        return None
    return body[match.end() :].strip() or "Where are we?"


async def handle_issue_comment(state: State, payload: dict[str, Any]) -> None:
    from app.api.github import for_repo_org

    org = await for_repo_org(state, payload)
    if org is None:
        return
    with org_context(org):
        await answer_comment(state, payload)


async def answer_comment(state: State, payload: dict[str, Any]) -> None:
    issue, comment = payload.get("issue") or {}, payload.get("comment") or {}
    if "pull_request" not in issue or (comment.get("user") or {}).get("type") == "Bot":
        return
    question = question_from(comment.get("body", ""))
    installation_id = (payload.get("installation") or {}).get("id")
    if question is None or state.github is None or not installation_id:
        return
    repo_name = payload["repository"]["full_name"]
    async with as_agent(state.sessionmaker) as session:
        repo = await session.scalar(select(Repo).where(Repo.full_name == repo_name))
        if repo is None:
            return
        space = await session.get(Space, repo.space_id)
        # The PR's own agent answers, unless the comment names another one (@space/D-014).
        scope = scoped_in(comment.get("body", ""), space.handle) or Scope(
            space.handle, "pr", pr_number=issue["number"]
        )
        try:
            await resolve(session, space, scope)
        except UnknownAgent:
            scope = None  # Tenet hasn't checked this PR yet: the space's agent answers
        if state.llm is None:
            body = "Tenet can't answer yet: the model gateway isn't configured."
        else:
            try:
                answer = await answer_question(session, state.llm, space, question, scope=scope)
                body = as_markdown(answer, state.settings.web_url, space.handle)
            except LLMError:
                log.exception("ask failed for %s#%s", repo_name, issue.get("number"))
                body = "Tenet couldn't answer that just now."
    await state.github.create_comment(installation_id, repo_name, issue["number"], body)
