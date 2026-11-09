"""GitHub App webhook: verified, idempotent, processed after the response is sent."""

import json
import logging
import uuid
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from starlette.datastructures import State

from app.github.signature import verify
from app.models import Repo, Space, WebhookDelivery
from app.prcheck.check import PRInfo, check_run_payload, run_pr_check
from app.tenancy import org_context, repo_org

log = logging.getLogger(__name__)
router = APIRouter()

PR_ACTIONS = {"opened", "edited", "reopened", "synchronize", "ready_for_review"}


async def record_delivery(state: State, source: str, delivery_id: str, event: str) -> bool:
    """True the first time a delivery id is seen."""
    async with state.sessionmaker() as session, session.begin():
        inserted = await session.scalar(
            insert(WebhookDelivery)
            .values(source=source, delivery_id=delivery_id, event=event)
            .on_conflict_do_nothing()
            .returning(WebhookDelivery.delivery_id)
        )
    return inserted is not None


@router.post("/webhooks/github", status_code=202)
async def github_webhook(request: Request, background: BackgroundTasks) -> dict[str, str]:
    state = request.app.state
    secret = state.settings.github_webhook_secret
    if not secret:
        raise HTTPException(503, "GITHUB_WEBHOOK_SECRET is not configured")
    body = await request.body()
    if not verify(secret, body, request.headers.get("X-Hub-Signature-256")):
        raise HTTPException(401, "invalid signature")
    delivery = request.headers.get("X-GitHub-Delivery")
    event = request.headers.get("X-GitHub-Event", "")
    if not delivery:
        raise HTTPException(400, "missing X-GitHub-Delivery")
    if not await record_delivery(state, "github", delivery, event):
        return {"status": "duplicate"}

    payload = json.loads(body)
    if event == "pull_request" and payload.get("action") in PR_ACTIONS:
        background.add_task(handle_pull_request, state, payload)
    elif event == "issue_comment" and payload.get("action") == "created":
        from app.ask.pr_comments import handle_issue_comment

        background.add_task(handle_issue_comment, state, payload)
    return {"status": "accepted"}


async def for_repo_org(state: State, payload: dict[str, Any]) -> uuid.UUID | None:
    """The org whose space this repo belongs to: the webhook acts for that org only."""
    async with state.sessionmaker() as session:
        return await repo_org(session, (payload.get("repository") or {}).get("full_name", ""))


async def handle_pull_request(state: State, payload: dict[str, Any]) -> None:
    org = await for_repo_org(state, payload)
    if org is None:
        log.info("ignoring PR on %s: repo is not linked to a space", payload["repository"])
        return
    with org_context(org):
        await check_pull_request(state, payload)


async def check_pull_request(state: State, payload: dict[str, Any]) -> None:
    pr = payload["pull_request"]
    repo_name = payload["repository"]["full_name"]
    installation_id = (payload.get("installation") or {}).get("id")
    info = PRInfo(
        repo=repo_name,
        number=pr["number"],
        head_sha=pr["head"]["sha"],
        title=pr.get("title") or "",
        body=pr.get("body") or "",
        author=(pr.get("user") or {}).get("login", ""),
        url=pr.get("html_url", ""),
    )
    github = state.github
    async with state.sessionmaker() as session, session.begin():
        repo = await session.scalar(select(Repo).where(Repo.full_name == repo_name))
        if repo is None:
            log.info("ignoring PR on %s: repo is not linked to a space", repo_name)
            return
        if installation_id and repo.installation_id != installation_id:
            repo.installation_id = installation_id
        space = await session.get(Space, repo.space_id)

        diff_text = None
        if github is not None and installation_id:
            try:
                diff_text = await github.get_pull_diff(installation_id, repo_name, info.number)
            except Exception:
                log.exception("could not fetch diff for %s#%s", repo_name, info.number)
        check = await run_pr_check(session, space, info, diff_text, state.llm)
        details = f"{state.settings.web_url}/spaces/{space.handle}/prs/{info.number}"
        payload_out = check_run_payload(check, details)

    if github is None or not installation_id:
        log.info("GitHub App not configured; check %s not posted", check.result)
        return
    try:
        await github.create_check_run(installation_id, repo_name, payload_out)
    except Exception:
        log.exception("could not post check run for %s#%s", repo_name, info.number)
