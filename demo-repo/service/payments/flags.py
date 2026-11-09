"""Rollout flags. The redesigned checkout ships behind `checkout_rollout` (D-013)."""

_enabled: set[str] = set()


def enabled(name: str) -> bool:
    return name in _enabled


def enable(name: str) -> None:
    _enabled.add(name)


def reset() -> None:
    _enabled.clear()
