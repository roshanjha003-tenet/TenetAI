from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Payment:
    id: str
    amount_cents: int
    idempotency_key: str
    first_attempt_at: datetime
    attempts: int = 1
    status: str = "failed"


@dataclass
class Failure:
    code: str
    hard_decline: bool = False
    history: list[str] = field(default_factory=list)

    @property
    def is_hard_decline(self) -> bool:
        return self.hard_decline
