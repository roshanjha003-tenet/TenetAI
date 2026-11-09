"""Manual recovery queue: support reviews and recovers these payments by hand."""

from payments.models import Payment

queue: list[dict] = []


def add(payment: Payment, reason: str) -> None:
    queue.append({"payment": payment.id, "reason": reason})
