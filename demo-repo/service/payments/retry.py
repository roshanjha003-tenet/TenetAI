"""What happens when a checkout payment fails."""

from payments import recovery_queue
from payments.models import Failure, Payment


def handle_failure(payment: Payment, failure: Failure) -> None:
    """Failed payments stay on the manual recovery path (D-012)."""
    recovery_queue.add(payment, reason=failure.code)
