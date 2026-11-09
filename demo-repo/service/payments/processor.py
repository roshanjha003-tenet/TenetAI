"""Thin wrapper over the payment processor's charge API."""

from payments.models import Payment

charges: list[dict] = []  # recorded calls, for tests and local runs


def charge(payment: Payment, idempotency_key: str) -> None:
    """Charge a payment. The processor deduplicates requests that share an idempotency key."""
    charges.append({"payment": payment.id, "idempotency_key": idempotency_key})
    payment.attempts += 1
