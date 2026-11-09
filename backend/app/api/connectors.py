"""Connect your own Google account, browse your Docs, and keep shared Docs in sync."""

import uuid
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.spaces import get_space
from app.api.views import item_view
from app.auth import current_user
from app.authz import require
from app.connectors.drive_items import link_doc, sync_item, sync_space
from app.connectors.google_drive import (
    DriveError,
    NotConnected,
    access_token_for,
    save_tokens,
)
from app.db import get_session
from app.identity import audit
from app.models import ConnectorToken, Item, User
from app.tenancy import org_context, user_org

router = APIRouter()


def drive_or_503(request: Request):
    drive = request.app.state.drive
    if drive is None:
        raise HTTPException(503, "Google Drive isn't configured (GOOGLE_CLIENT_ID/SECRET)")
    return drive


@router.get("/connect/google")
async def google_status(request: Request, user: User = Depends(current_user)) -> dict[str, Any]:
    from app.sessions import as_user

    if request.app.state.drive is None:
        return {"configured": False, "connected": False, "email": None}
    async with as_user(request.app.state.sessionmaker, user.id) as s:
        token = await s.get(ConnectorToken, (user.id, "google"))
    return {
        "configured": True,
        "connected": token is not None,
        "email": token.account_email if token else None,
    }


@router.post("/connect/google/start")
async def google_start(request: Request, user: User = Depends(current_user)) -> dict[str, str]:
    """Returns Google's consent URL; the browser goes there and comes back to the callback."""
    drive = drive_or_503(request)
    return {"url": drive.consent_url(drive.sign_state(user.id))}


@router.get("/connect/google/callback", include_in_schema=False)
async def google_callback(
    request: Request, code: str | None = None, state: str = "", error: str | None = None
) -> RedirectResponse:
    drive = drive_or_503(request)
    back = f"{request.app.state.settings.web_url}/settings/connections"
    if error or not code:
        return RedirectResponse(f"{back}?{urlencode({'google': 'error', 'reason': error or ''})}")
    try:
        user_id = drive.verify_state(state)
        tokens = await drive.exchange(code)
    except DriveError as exc:
        return RedirectResponse(f"{back}?{urlencode({'google': 'error', 'reason': str(exc)})}")
    async with request.app.state.sessionmaker() as session:
        org = await user_org(session, user_id)
    with org_context(org):
        await save_tokens(request.app.state.sessionmaker, user_id, tokens, drive.box)
        async with request.app.state.sessionmaker() as session, session.begin():
            await audit(
                session,
                "connector.connected",
                request=request,
                org_id=org,
                subject=tokens.email,
                details={"provider": "google"},
            )
    return RedirectResponse(f"{back}?google=connected")


@router.delete("/connect/google")
async def google_disconnect(request: Request, user: User = Depends(current_user)) -> dict:
    from app.sessions import as_user

    async with as_user(request.app.state.sessionmaker, user.id) as s:
        await s.execute(
            delete(ConnectorToken).where(
                ConnectorToken.owner_id == user.id, ConnectorToken.provider == "google"
            )
        )
        await audit(
            s, "connector.disconnected", request=request, actor=user, details={"provider": "google"}
        )
    return {"connected": False}


@router.get("/connect/google/docs")
async def google_docs(
    request: Request, q: str = "", user: User = Depends(current_user)
) -> list[dict[str, str]]:
    """Your recent Google Docs (read with your own permissions), for the attach picker."""
    drive = drive_or_503(request)
    try:
        token = await access_token_for(drive, request.app.state.sessionmaker, user.id)
        return await drive.list_docs(token, q)
    except NotConnected as exc:
        raise HTTPException(409, str(exc)) from exc
    except DriveError as exc:
        raise HTTPException(502, str(exc)) from exc


class DocIn(BaseModel):
    url: str
    title: str = ""


@router.post("/spaces/{handle}/docs", status_code=201)
async def add_doc_source(
    handle: str,
    body: DocIn,
    request: Request,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Add a Google Doc to the space's sources, read and kept in sync with your permissions."""
    space = await get_space(session, handle, user)
    await require(session, user, "item.add", space)
    await session.commit()
    drive_or_503(request)
    try:
        item = await link_doc(request.app.state, user, space, body.url, body.title)
    except NotConnected as exc:
        raise HTTPException(409, str(exc)) from exc
    except DriveError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {**item_view(item), "synced_at": item.synced_at.isoformat()}


@router.post("/spaces/{handle}/sync")
async def sync_docs(
    handle: str,
    request: Request,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    space = await get_space(session, handle, user)
    await session.commit()
    drive_or_503(request)
    return await sync_space(request.app.state, space.id)


@router.post("/spaces/{handle}/items/{item_id}/sync")
async def sync_one(
    handle: str,
    item_id: uuid.UUID,
    request: Request,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    space = await get_space(session, handle, user)
    item = await session.get(Item, item_id)
    if item is None or item.space_id != space.id:
        raise HTTPException(404, "no such item")
    await session.commit()
    drive_or_503(request)
    return await sync_item(request.app.state, item_id)
