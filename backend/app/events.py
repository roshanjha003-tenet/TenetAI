import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Event


async def append_event(
    session: AsyncSession,
    *,
    space_id: uuid.UUID,
    type: str,
    target_kind: str,
    target_id: str,
    idempotency_key: str,
    actor_id: uuid.UUID | None = None,
    target_revision: int | None = None,
    payload: dict[str, Any] | None = None,
    caused_by: uuid.UUID | None = None,
    at: datetime | None = None,
) -> Event:
    """Append one event. Replaying the same idempotency key returns the original event."""
    values: dict[str, Any] = {
        "id": uuid.uuid4(),
        "space_id": space_id,
        "type": type,
        "actor_id": actor_id,
        "target_kind": target_kind,
        "target_id": target_id,
        "target_revision": target_revision,
        "payload": payload or {},
        "caused_by": caused_by,
        "idempotency_key": idempotency_key,
    }
    if at is not None:
        values["at"] = at
    stmt = (
        insert(Event)
        .values(**values)
        .on_conflict_do_nothing(index_elements=["space_id", "idempotency_key"])
        .returning(Event.id)
    )
    inserted_id = (await session.execute(stmt)).scalar_one_or_none()
    query = select(Event).where(
        Event.space_id == space_id, Event.idempotency_key == idempotency_key
    )
    if inserted_id is not None:
        query = select(Event).where(Event.id == inserted_id)
    return (await session.execute(query)).scalar_one()


async def list_events(session: AsyncSession, space_id: uuid.UUID) -> list[Event]:
    result = await session.execute(
        select(Event).where(Event.space_id == space_id).order_by(Event.seq)
    )
    return list(result.scalars())
