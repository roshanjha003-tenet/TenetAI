import logging
from typing import TYPE_CHECKING, Protocol

from starlette.datastructures import State

if TYPE_CHECKING:
    from app.review import Notice

log = logging.getLogger(__name__)


class Notifier(Protocol):
    async def notify(self, state: State, notice: "Notice") -> None: ...


async def dispatch(state: State, notices: list["Notice"]) -> None:
    """Send notices after the transaction that produced them has committed. Never raises."""
    notifier = getattr(state, "notifier", None)
    if notifier is None:
        return
    for notice in notices:
        try:
            await notifier.notify(state, notice)
        except Exception:
            log.exception("notification %s for %s failed", notice.kind, notice.proposal_id)
