from datetime import timedelta

from payments import clock, flags, processor, recovery_queue, retry
from payments.models import Failure


def test_transient_failure_is_retried(payment):
    flags.enable("checkout_rollout")

    retry.handle_failure(payment, Failure(code="processor_timeout"))

    assert len(processor.charges) == 1
    assert processor.charges[0]["payment"] == "pay_123"


def test_stops_after_three_attempts(payment):
    flags.enable("checkout_rollout")
    payment.attempts = 3

    retry.handle_failure(payment, Failure(code="processor_timeout"))

    assert processor.charges == []


def test_stops_after_24_hours(payment):
    flags.enable("checkout_rollout")
    payment.first_attempt_at = clock.now() - timedelta(hours=25)

    retry.handle_failure(payment, Failure(code="processor_timeout"))

    assert processor.charges == []


def test_hard_decline_stays_on_manual_recovery(payment):
    flags.enable("checkout_rollout")

    retry.handle_failure(payment, Failure(code="insufficient_funds", hard_decline=True))

    assert recovery_queue.queue == [{"payment": "pay_123", "reason": "insufficient_funds"}]
