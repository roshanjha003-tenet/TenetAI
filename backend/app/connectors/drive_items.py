"""Google Docs in Tenet: attach privately, share deliberately, keep shared copies in sync.

- Attaching a Doc to a private session stores its text in session_attachments (RLS, owner only).
  Your own AI can read it; nobody else and no agent can.
- Tagging the space in a message that carries attachments shares them: each becomes a space item
  (a source the master agent uses as evidence) and is cited on the finding or proposal.
- Shared Docs re-sync with the permissions of the person who shared them. If that person loses
  access, the item keeps its last copy and the sync reports it.
"""

import asyncio
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from starlette.datastructures import State

from app.connectors.google_drive import (
    DriveError,
    GoogleDrive,
    NotConnected,
    access_token_for,
    file_id_from,
)
from app.events import append_event
from app.models import Item, PrivateSession, SessionAttachment, Space, User

log = logging.getLogger(__name__)
EXCERPT_CHARS = 6_000  # what a shared Doc contributes to the space's evidence


def attachment_view(a: SessionAttachment) -> dict[str, Any]:
    return {
        "id": str(a.id),
        "kind": a.kind,
        "title": a.title,
        "url": a.url,
        "chars": len(a.text),
        "shared_item_id": str(a.shared_item_id) if a.shared_item_id else None,
        "created_at": a.created_at.isoformat(),
    }


def require_drive(state: State) -> GoogleDrive:
    if state.drive is None:
        raise DriveError("Google Drive isn't configured on this server (GOOGLE_CLIENT_ID/SECRET)")
    return state.drive


async def attach(
    state: State, user: User, session_id: uuid.UUID, url_or_id: str
) -> dict[str, Any] | None:
    from app.sessions import as_user

    drive = require_drive(state)
    file_id = file_id_from(url_or_id)
    if file_id is None:
        raise DriveError("that doesn't look like a Google Doc link")
    async with as_user(state.sessionmaker, user.id) as s:
        if await s.get(PrivateSession, session_id) is None:
            return None
    token = await access_token_for(drive, state.sessionmaker, user.id)
    doc = await drive.get_doc(token, file_id)
    async with as_user(state.sessionmaker, user.id) as s:
        row = SessionAttachment(
            session_id=session_id,
            owner_id=user.id,
            kind="gdoc",
            source_id=doc.id,
            url=doc.url,
            title=doc.title,
            text=doc.text,
            content_hash=doc.content_hash,
        )
        s.add(row)
        await s.flush()
        return attachment_view(row)


async def session_attachments(
    state: State, user: User, session_id: uuid.UUID, ids: list[uuid.UUID] | None = None
) -> list[dict[str, Any]]:
    """Attachments the caller owns in this session, with their text (for their own use)."""
    from app.sessions import as_user

    async with as_user(state.sessionmaker, user.id) as s:
        query = select(SessionAttachment).where(SessionAttachment.session_id == session_id)
        if ids is not None:
            if not ids:
                return []
            query = query.where(SessionAttachment.id.in_(ids))
        rows = list(await s.scalars(query.order_by(SessionAttachment.created_at)))
        return [
            {
                **attachment_view(a),
                "source_id": a.source_id,
                "text": a.text,
                "content_hash": a.content_hash,
            }
            for a in rows
        ]


async def share_attachments(
    state: State,
    user: User,
    space_id: uuid.UUID,
    attachments: list[dict[str, Any]],
    caused_by: uuid.UUID | None,
) -> list[dict[str, Any]]:
    """Make the chosen attachments space items. Returns evidence entries for the share."""
    from app.sessions import as_agent, as_user

    if not attachments:
        return []
    evidence, shared = [], {}
    async with as_agent(state.sessionmaker) as s:
        space = await s.get(Space, space_id)
        for a in attachments:
            item = await s.scalar(
                select(Item).where(Item.space_id == space.id, Item.source_id == a["source_id"])
            )
            if item is None:
                item = Item(
                    space_id=space.id,
                    kind="gdoc",
                    url=a["url"],
                    title=a["title"],
                    excerpt=a["text"][:EXCERPT_CHARS],
                    content_hash=a["content_hash"],
                    added_by=user.id,
                    source_id=a["source_id"],
                    synced_at=datetime.now(UTC),
                )
                s.add(item)
                await s.flush()
                await append_event(
                    s,
                    space_id=space.id,
                    type="item.linked",
                    actor_id=user.id,
                    target_kind="item",
                    target_id=str(item.id),
                    caused_by=caused_by,
                    payload={
                        "kind": "gdoc",
                        "title": item.title,
                        "url": item.url,
                        "via": "private session",
                    },
                    idempotency_key=f"item:{item.id}:linked",
                )
            shared[uuid.UUID(a["id"])] = item.id
            evidence.append(
                {"kind": "gdoc", "id": str(item.id), "title": item.title, "url": item.url}
            )
    async with as_user(state.sessionmaker, user.id) as s:
        for attachment_id, item_id in shared.items():
            row = await s.get(SessionAttachment, attachment_id)
            if row is not None:
                row.shared_item_id = item_id
    return evidence


async def link_doc(state: State, user: User, space: Space, url: str, title: str = "") -> Item:
    """Pull a Google Doc into a space's sources, read with the caller's own permissions."""
    from app.sessions import as_agent

    drive = require_drive(state)
    file_id = file_id_from(url)
    if file_id is None:
        raise DriveError("that doesn't look like a Google Doc link")
    token = await access_token_for(drive, state.sessionmaker, user.id)
    doc = await drive.get_doc(token, file_id)
    async with as_agent(state.sessionmaker) as s:
        item = Item(
            space_id=space.id,
            kind="gdoc",
            url=doc.url,
            title=title.strip() or doc.title,
            excerpt=doc.text[:EXCERPT_CHARS],
            content_hash=doc.content_hash,
            added_by=user.id,
            source_id=doc.id,
            synced_at=datetime.now(UTC),
        )
        s.add(item)
        await s.flush()
        await append_event(
            s,
            space_id=space.id,
            type="item.linked",
            actor_id=user.id,
            target_kind="item",
            target_id=str(item.id),
            payload={"kind": "gdoc", "title": item.title, "url": item.url},
            idempotency_key=f"item:{item.id}:linked",
        )
        return item


async def sync_item(state: State, item_id: uuid.UUID) -> dict[str, Any]:
    """Re-read a shared Doc as the person who shared it; record a new copy only if it changed."""
    from app.sessions import as_agent

    drive = require_drive(state)
    async with as_agent(state.sessionmaker) as s:
        item = await s.get(Item, item_id)
        if item is None or item.kind != "gdoc" or not item.source_id:
            return {"item": str(item_id), "status": "not a Google Doc"}
        source_id, owner, space_id = item.source_id, item.added_by, item.space_id
    try:
        token = await access_token_for(drive, state.sessionmaker, owner)
        doc = await drive.get_doc(token, source_id)
    except DriveError as exc:
        return {"item": str(item_id), "status": "unavailable", "reason": str(exc)}
    async with as_agent(state.sessionmaker) as s:
        item = await s.get(Item, item_id)
        item.synced_at = datetime.now(UTC)
        if doc.content_hash == item.content_hash:
            return {"item": str(item_id), "status": "unchanged"}
        previous = item.content_hash
        item.excerpt, item.content_hash, item.title = (
            doc.text[:EXCERPT_CHARS],
            doc.content_hash,
            doc.title,
        )
        await append_event(
            s,
            space_id=space_id,
            type="item.synced",
            actor_id=None,
            target_kind="item",
            target_id=str(item.id),
            payload={
                "title": doc.title,
                "modified": doc.modified,
                "from_hash": previous[:12],
                "to_hash": doc.content_hash[:12],
            },
            idempotency_key=f"item:{item.id}:synced:{doc.content_hash}",
        )
    return {"item": str(item_id), "status": "updated", "title": doc.title}


async def sync_space(state: State, space_id: uuid.UUID) -> list[dict[str, Any]]:
    from app.sessions import as_agent

    async with as_agent(state.sessionmaker) as s:
        ids = list(
            await s.scalars(select(Item.id).where(Item.space_id == space_id, Item.kind == "gdoc"))
        )
    return [await sync_item(state, i) for i in ids]


async def sync_forever(state: State, minutes: int) -> None:
    """Background loop: keep every shared Doc in every space current, one org at a time."""
    while True:
        await asyncio.sleep(minutes * 60)
        try:
            await sync_all(state)
        except Exception:
            log.exception("Drive sync failed")


async def sync_all(state: State) -> None:
    from app.sessions import as_agent
    from app.tenancy import all_orgs, org_context

    async with state.sessionmaker() as s:
        orgs = await all_orgs(s)
    for org in orgs:
        with org_context(org):
            async with as_agent(state.sessionmaker) as s:
                ids = list(await s.scalars(select(Item.id).where(Item.kind == "gdoc")))
            for item_id in ids:
                await sync_item(state, item_id)


__all__ = ["NotConnected", "DriveError"]
