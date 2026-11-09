"""Slack notifications: proposal created, your turn to review, state updated (and pushbacks,
rejections, blocked proposals). Approving from Slack is stubbed for the demo: messages link to
the web app, where approval happens.
"""

import logging
from collections.abc import Callable
from typing import Any

import httpx
from starlette.datastructures import State

from app.config import Settings
from app.models import Finding, Proposal, Space, User
from app.review import STAGES, Notice, stage_owner

log = logging.getLogger(__name__)


class SlackError(Exception):
    pass


def mention(user: User | None) -> str:
    if user is None:
        return "someone"
    return f"<@{user.slack_user_id}>" if user.slack_user_id else f"*{user.name}*"


def section(text: str) -> dict[str, Any]:
    return {"type": "section", "text": {"type": "mrkdwn", "text": text}}


def context(text: str) -> dict[str, Any]:
    return {"type": "context", "elements": [{"type": "mrkdwn", "text": text}]}


def button(label: str, url: str) -> dict[str, Any]:
    return {
        "type": "actions",
        "elements": [{"type": "button", "text": {"type": "plain_text", "text": label}, "url": url}],
    }


class SlackNotifier:
    def __init__(
        self,
        token: str,
        channel: str,
        web_url: str,
        api_url: str = "https://slack.com/api",
        http: Callable[[], httpx.AsyncClient] | None = None,
    ) -> None:
        self.token, self.channel, self.web_url = token, channel, web_url.rstrip("/")
        self.api_url = api_url.rstrip("/")
        self.http = http or (lambda: httpx.AsyncClient(timeout=10))

    async def post(self, channel: str, text: str, blocks: list[dict[str, Any]]) -> None:
        async with self.http() as client:
            response = await client.post(
                f"{self.api_url}/chat.postMessage",
                headers={"Authorization": f"Bearer {self.token}"},
                json={"channel": channel, "text": text, "blocks": blocks, "unfurl_links": False},
            )
        body = response.json()
        if not body.get("ok"):
            raise SlackError(body.get("error", f"HTTP {response.status_code}"))

    async def notify(self, state: State, notice: Notice) -> None:
        from app.sessions import as_agent

        if notice.finding_id is not None:
            messages = await self.render_finding(state, notice)
            for channel, text, blocks in messages:
                await self.post(channel, text, blocks)
            return
        async with as_agent(state.sessionmaker) as session:
            proposal = await session.get(Proposal, notice.proposal_id)
            space = await session.get(Space, proposal.space_id)
            proposer = await session.get(User, proposal.proposer_id)
            owners = [await stage_owner(session, space, s) for s in STAGES]
            recipients = [await session.get(User, uid) for uid in notice.user_ids]
            messages = self.render(notice, space, proposal, proposer, owners, recipients)
        for channel, text, blocks in messages:
            await self.post(channel, text, blocks)

    async def render_finding(
        self, state: State, notice: Notice
    ) -> list[tuple[str, str, list[dict[str, Any]]]]:
        from app.sessions import as_agent

        async with as_agent(state.sessionmaker) as session:
            finding = await session.get(Finding, notice.finding_id)
            space = await session.get(Space, finding.space_id)
            author = await session.get(User, finding.author_id)
            recipients = [await session.get(User, uid) for uid in notice.user_ids]
        tag = f"*@{space.handle}*"
        link = f"{self.web_url}/spaces/{space.handle}/findings/{finding.id}"
        excerpt = finding.text if len(finding.text) <= 600 else finding.text[:600] + "…"
        if notice.kind == "finding_shared":
            return [
                (
                    self.channel,
                    f"{author.name} shared a finding in @{space.handle}",
                    [
                        section(f"{tag} · {mention(author)} shared a finding\n> {excerpt}"),
                        context("Not agreed yet · reply with agree, concern or question"),
                        button("Reply", link),
                    ],
                )
            ]
        stance, by = notice.data.get("stance", ""), notice.data.get("by", "Someone")
        out = []
        for user in recipients:
            out.append(
                (
                    user.slack_user_id or self.channel,
                    f"{by} replied ({stance}) to your finding",
                    [
                        section(
                            f"{mention(user)}, *{by}* replied *{stance}* to your finding in {tag}"
                            + (f"\n> {notice.data.get('text')}" if notice.data.get("text") else "")
                        ),
                        button("Open finding", link),
                    ],
                )
            )
        return out

    def render(
        self,
        notice: Notice,
        space: Space,
        proposal: Proposal,
        proposer: User,
        owners: list[User],
        recipients: list[User],
    ) -> list[tuple[str, str, list[dict[str, Any]]]]:
        name = (
            f"{proposal.decision_key} · {proposal.title}"
            if proposal.decision_key
            else proposal.title
        )
        link = f"{self.web_url}/spaces/{space.handle}/proposals/{proposal.id}"
        tag = f"*@{space.handle}*"
        chain = " → ".join(f"{s.name}: {o.name}" for s, o in zip(STAGES, owners, strict=True))

        if notice.kind == "proposal_created":
            constraints = "\n".join(f"• {c}" for c in proposal.content.get("constraints", []))
            text = f"{proposer.name} proposed {name} in @{space.handle}"
            blocks = [section(f"{tag} · {mention(proposer)} proposed *{name}* — review pending")]
            if constraints:
                blocks.append(section(constraints))
            parents = ", ".join(proposal.content.get("parents", []))
            blocks += [
                context(f"Review: {chain}" + (f" · builds on {parents}" if parents else "")),
                button("Open proposal", link),
            ]
            return [(self.channel, text, blocks)]

        if notice.kind == "review_requested":
            stage = notice.data.get("stage", "review")
            out = []
            for user in recipients:
                text = f"Your turn to review {name} ({stage})"
                blocks = [
                    section(f"{mention(user)}, your turn: *{stage}* review of *{name}* in {tag}"),
                    context(f"Proposed by {proposer.name} · {chain}"),
                    button("Review", link),
                ]
                out.append((user.slack_user_id or self.channel, text, blocks))
            return out

        if notice.kind == "state_updated":
            version = notice.data.get("version")
            approvers = ", ".join(o.name for o in owners)
            text = f"v{version} is the agreed state of @{space.handle}: {name}"
            return [
                (
                    self.channel,
                    text,
                    [
                        section(f"{tag} · *v{version}* is the agreed state: *{name}*"),
                        context(f"Approved by {approvers}"),
                        button("See what changed", f"{self.web_url}/spaces/{space.handle}/state"),
                    ],
                )
            ]

        if notice.kind == "pushback_raised":
            by, reason = notice.data.get("by", "Someone"), notice.data.get("reason", "")
            return [
                (
                    self.channel,
                    f"{by} pushed back on {name}",
                    [
                        section(f"{tag} · *{by}* pushed back on *{name}*\n> {reason}"),
                        context(f"{', '.join(mention(u) for u in recipients)} to resolve"),
                        button("Open proposal", link),
                    ],
                )
            ]

        if notice.kind == "rejected":
            return [
                (
                    self.channel,
                    f"{name} was rejected",
                    [
                        section(
                            f"{tag} · *{name}* was rejected\n> {notice.data.get('reason', '')}"
                        ),
                        button("Open proposal", link),
                    ],
                )
            ]

        if notice.kind == "blocked":
            clash = ", ".join(notice.data.get("conflicts_with", []))
            return [
                (
                    self.channel,
                    f"{name} is blocked by {clash}",
                    [
                        section(
                            f"{tag} · *{name}* conflicts with {clash} and went back to its owner"
                        ),
                        context(", ".join(mention(u) for u in recipients)),
                        button("Open proposal", link),
                    ],
                )
            ]
        return []


def make_notifier(settings: Settings) -> SlackNotifier | None:
    if not settings.slack_bot_token:
        return None
    return SlackNotifier(settings.slack_bot_token, settings.slack_channel, settings.web_url)
