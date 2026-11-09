"""Private sessions API. Every query runs under row-level security as the token's user."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.spaces import get_space
from app.auth import current_user
from app.connectors.drive_items import attach
from app.connectors.google_drive import DriveError, NotConnected
from app.db import get_session
from app.models import User
from app.notify import dispatch
from app.sessions import create_session, list_sessions, post_message, read_session

router = APIRouter()


class SessionIn(BaseModel):
    title: str = "New session"


class MessageIn(BaseModel):
    text: str
    # finding | decision | status | question; omitted -> the router decides
    action: str | None = None
    # Docs attached to this session to share along with the tagged text
    attachment_ids: list[uuid.UUID] = Field(default_factory=list)


class AttachIn(BaseModel):
    url: str  # a Google Doc link or file id


@router.get("/sessions")
async def my_sessions(request: Request, user: User = Depends(current_user)) -> list[dict]:
    return await list_sessions(request.app.state, user)


@router.post("/spaces/{handle}/sessions", status_code=201)
async def new_session(
    handle: str,
    body: SessionIn,
    request: Request,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    space = await get_space(session, handle, user)
    await session.commit()
    return await create_session(request.app.state, user, space, body.title)


@router.get("/sessions/{session_id}")
async def get_session_(
    session_id: uuid.UUID, request: Request, user: User = Depends(current_user)
) -> dict[str, Any]:
    found = await read_session(request.app.state, user, session_id)
    if found is None:
        raise HTTPException(404, "no such session")
    return found


@router.post("/sessions/{session_id}/messages", status_code=201)
async def send(
    session_id: uuid.UUID, body: MessageIn, request: Request, user: User = Depends(current_user)
) -> dict[str, Any]:
    if body.action not in (None, "finding", "decision", "status", "question"):
        raise HTTPException(422, "action must be finding, decision, status or question")
    result, notices = await post_message(
        request.app.state, user, session_id, body.text, body.action, body.attachment_ids or None
    )
    if result is None:
        raise HTTPException(404, "no such session")
    await dispatch(request.app.state, notices)
    return result


@router.post("/sessions/{session_id}/attachments", status_code=201)
async def attach_doc(
    session_id: uuid.UUID, body: AttachIn, request: Request, user: User = Depends(current_user)
) -> dict[str, Any]:
    """Attach a Google Doc privately. Nothing is shared until you tag the space with it."""
    try:
        attached = await attach(request.app.state, user, session_id, body.url)
    except NotConnected as exc:
        raise HTTPException(409, str(exc)) from exc
    except DriveError as exc:
        raise HTTPException(422, str(exc)) from exc
    if attached is None:
        raise HTTPException(404, "no such session")
    return attached
