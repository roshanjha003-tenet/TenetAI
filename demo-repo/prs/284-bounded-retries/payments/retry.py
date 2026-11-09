"""What happens when a checkout payment fails."""

from datetime import timedelta

from payments import clock, flags, processor, recovery_queue
from payments.models import Failure, Payment

MAX_AUTOMATIC_ATTEMPTS = 3
RETRY_WINDOW = timedelta(hours=24)


def handle_failure(payment: Payment, failure: Failure) -> None:
    """Retry transient failures within bounds (D-014); everything else stays on manual recovery."""
    if not flags.enabled("checkout_rollout") or failure.is_hard_decline:
        recovery_queue.add(payment, reason=failure.code)
        return
    if not within_retry_budget(payment):
        recovery_queue.add(payment, reason="retry_budget_exhausted")
        return
    retry(payment)


def within_retry_budget(payment: Payment) -> bool:
    return (
        payment.attempts < MAX_AUTOMATIC_ATTEMPTS
        and clock.now() - payment.first_attempt_at < RETRY_WINDOW
    )


def retry(payment: Payment) -> None:
    # Every attempt reuses the payment's idempotency key, so the processor can't charge twice.
    processor.charge(payment, idempotency_key=payment.idempotency_key)
