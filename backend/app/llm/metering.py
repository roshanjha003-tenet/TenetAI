"""Metering and the per-org spending cap, wrapped around any gateway.

Before a call: if the org has spent its monthly cap, refuse with LLMError, so every feature fails
the way it already does when the model is unavailable (the PR check goes neutral, Ask says it
can't answer). After a call: record tokens and estimated cost for the org.
"""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, insert, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.llm.gateway import USAGE, Effort, LLMError, LLMGateway, T, Tier
from app.models import Org, UsageRecord
from app.tenancy import current_org

# USD per million tokens (input, output), Anthropic first-party rates.
PRICES = {
    "claude-opus-5-5": (Decimal("4.00"), Decimal("20.00")),
    "claude-haiku-5-5": (Decimal("0.10"), Decimal("0.50")),
}


def cost_of(model: str, input_tokens: int, output_tokens: int) -> Decimal:
    price_in, price_out = next(
        (p for name, p in PRICES.items() if model.startswith(name)), PRICES["claude-opus-5-5"]
    )
    return (price_in * input_tokens + price_out * output_tokens) / Decimal(1_000_000)


def month_start() -> datetime:
    return datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)


class MeteredGateway:
    def __init__(self, inner: LLMGateway, sessions: async_sessionmaker) -> None:
        self.inner = inner
        self.sessions = sessions

    async def structured(
        self,
        *,
        task: str,
        tier: Tier,
        system: str,
        prompt: str,
        schema: type[T],
        effort: Effort = "medium",
        max_tokens: int = 16000,
    ) -> T:
        org = current_org.get()
        if org is not None and await self.over_cap():
            raise LLMError(f"{task}: this org's monthly model spending cap is reached")
        sink: list[tuple[str, Any]] = []
        token = USAGE.set(sink)
        try:
            result = await self.inner.structured(
                task=task,
                tier=tier,
                system=system,
                prompt=prompt,
                schema=schema,
                effort=effort,
                max_tokens=max_tokens,
            )
        finally:
            USAGE.reset(token)
        await self.record(task, tier, sink)
        return result

    async def over_cap(self) -> bool:
        async with self.sessions() as s, s.begin():
            cap = await s.scalar(select(Org.monthly_cap_usd))
            if cap is None:
                return False
            spent = await s.scalar(
                select(func.coalesce(func.sum(UsageRecord.cost_usd), 0)).where(
                    UsageRecord.at >= month_start()
                )
            )
            return Decimal(spent) >= Decimal(cap)

    async def record(self, task: str, tier: Tier, calls: list[tuple[str, Any]]) -> None:
        rows = []
        for model, usage in calls or [(f"recorded-{tier}", None)]:
            tokens_in = sum(
                getattr(usage, f, 0) or 0
                for f in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")
            )
            tokens_out = getattr(usage, "output_tokens", 0) or 0
            rows.append(
                dict(
                    org_id=current_org.get(),
                    task=task[:60],
                    model=model[:60],
                    input_tokens=tokens_in,
                    output_tokens=tokens_out,
                    cost_usd=cost_of(model, tokens_in, tokens_out),
                )
            )
        # Plain INSERT: a call with no org can't be read back, so no RETURNING.
        async with self.sessions() as s, s.begin():
            await s.execute(insert(UsageRecord), rows)

    def __getattr__(self, name: str) -> Any:  # tests reach through to RecordedGateway.calls
        return getattr(self.inner, name)
