import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.events import append_event
from app.models import Event
from app.seed import seed

APPEND_ONLY = ("events", "state_versions", "decision_revisions")


@pytest.mark.parametrize("table", APPEND_ONLY)
@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE {table} SET created_at = now()",
        "DELETE FROM {table}",
        "TRUNCATE {table} CASCADE",
    ],
)
async def test_history_tables_reject_changes(
    session: AsyncSession, table: str, statement: str
) -> None:
    await seed(session)
    sql = statement.format(table=table)
    if table == "events":
        sql = sql.replace("created_at", "at")

    with pytest.raises(DBAPIError, match="append-only"):
        async with session.begin_nested():
            await session.execute(text(sql))

    remaining = await session.scalar(text(f"SELECT count(*) FROM {table}"))
    assert remaining > 0


async def test_same_idempotency_key_appends_once(session: AsyncSession) -> None:
    result = await seed(session)
    kwargs = dict(
        space_id=result.space.id,
        type="item.linked",
        target_kind="item",
        target_id="x",
        idempotency_key="webhook:delivery-1",
    )

    first = await append_event(session, **kwargs)
    second = await append_event(session, **kwargs, payload={"retried": True})

    assert first.id == second.id
    count = await session.scalar(
        select(func.count()).select_from(Event).where(Event.idempotency_key == "webhook:delivery-1")
    )
    assert count == 1
