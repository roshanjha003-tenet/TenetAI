"""LLM gateway: the only place model calls happen.

Every call names a task, a tier (cheap or strong) and a Pydantic schema; the response is parsed
into that schema or the call fails. Callers still validate the result against the database
(references exist, lines exist) before using it: models propose, code checks.

Tests use RecordedGateway, which replays fixture responses and never touches the network.
"""

import json
import logging
from collections import defaultdict, deque
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Literal, Protocol, TypeVar

from anthropic import APIConnectionError, APIStatusError, AsyncAnthropic
from pydantic import BaseModel, ValidationError

from app.config import Settings

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)
Tier = Literal["cheap", "strong"]
Effort = Literal["low", "medium", "high", "xhigh", "max"]


class LLMError(Exception):
    """The model call failed, was refused, or returned output that doesn't fit the schema."""


# Where a gateway reports (model, usage) for each call made in this task; see app.llm.metering.
USAGE: ContextVar[list[tuple[str, Any]] | None] = ContextVar("llm_usage", default=None)


class LLMGateway(Protocol):
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
    ) -> T: ...


class AnthropicGateway:
    def __init__(self, settings: Settings, client: AsyncAnthropic | None = None) -> None:
        self.models = {"cheap": settings.llm_model_cheap, "strong": settings.llm_model_strong}
        self.client = client or AsyncAnthropic(api_key=settings.anthropic_api_key)

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
        model = self.models[tier]
        kwargs: dict[str, Any] = dict(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
            output_format=schema,
            output_config={"effort": effort},
        )
        try:
            if tier == "strong":
                # If a safety classifier declines, the API re-runs the request on a fallback model.
                response = await self.client.beta.messages.parse(
                    **kwargs, betas=["server-side-fallback-2026-07-01"], fallbacks="default"
                )
            else:
                response = await self.client.messages.parse(**kwargs)
        except (APIStatusError, APIConnectionError) as exc:
            raise LLMError(f"{task}: {exc}") from exc
        except ValidationError as exc:
            raise LLMError(f"{task}: output did not match {schema.__name__}") from exc

        if response.stop_reason == "refusal":
            raise LLMError(f"{task}: model declined")
        if response.stop_reason == "max_tokens":
            raise LLMError(f"{task}: output cut off at max_tokens")
        if response.parsed_output is None:
            raise LLMError(f"{task}: no structured output")
        log.info("llm task=%s model=%s usage=%s", task, response.model, response.usage)
        sink = USAGE.get()
        if sink is not None:
            sink.append((response.model, response.usage))
        return response.parsed_output


class RecordedGateway:
    """Replays recorded responses per task, in order. Records every request it receives."""

    def __init__(self, responses: dict[str, list[dict[str, Any] | Exception]] | None = None):
        self.responses: dict[str, deque[dict[str, Any] | Exception]] = defaultdict(deque)
        self.calls: list[dict[str, Any]] = []
        for task, items in (responses or {}).items():
            self.responses[task].extend(items)

    @classmethod
    def from_files(cls, directory: Path, mapping: dict[str, list[str]]) -> "RecordedGateway":
        """mapping: task -> fixture file names (JSON) under directory, replayed in order."""
        return cls(
            {
                task: [json.loads((directory / name).read_text()) for name in names]
                for task, names in mapping.items()
            }
        )

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
        self.calls.append({"task": task, "tier": tier, "system": system, "prompt": prompt})
        if not self.responses[task]:
            raise LLMError(f"{task}: no recorded response left")
        item = self.responses[task].popleft()
        if isinstance(item, Exception):
            raise item
        try:
            return schema.model_validate(item)
        except ValidationError as exc:
            raise LLMError(f"{task}: recorded output did not match {schema.__name__}") from exc


def make_gateway(settings: Settings) -> LLMGateway | None:
    if not settings.anthropic_api_key:
        log.warning("ANTHROPIC_API_KEY is not set; model-backed features will report 'unsure'")
        return None
    return AnthropicGateway(settings)
