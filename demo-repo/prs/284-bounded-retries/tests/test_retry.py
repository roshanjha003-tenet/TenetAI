from datetime import timedelta

from payments import clock, flags, processor, recovery_queue, retry
from payments.models import Failure


def test_transient_failure_is_retried_with_the_same_key(payment):
    flags.enable("checkout_rollout")

    retry.handle_failure(payment, Failure(code="processor_timeout"))
    retry.handle_failure(payment, Failure(code="processor_timeout"))

    assert [c["idempotency_key"] for c in processor.charges] == ["idem_pay_123", "idem_pay_123"]


def test_stops_after_three_attempts(payment):
    flags.enable("checkout_rollout")
    payment.attempts = 3

    retry.handle_failure(payment, Failure(code="processor_timeout"))

    assert processor.charges == []
    assert recovery_queue.queue == [{"payment": "pay_123", "reason": "retry_budget_exhausted"}]


def test_stops_after_24_hours(payment):
    flags.enable("checkout_rollout")
    payment.first_attempt_at = clock.now() - timedelta(hours=25)

    retry.handle_failure(payment, Failure(code="processor_timeout"))

    assert processor.charges == []


def test_hard_decline_stays_on_manual_recovery(payment):
    flags.enable("checkout_rollout")

    retry.handle_failure(payment, Failure(code="insufficient_funds", hard_decline=True))

    assert processor.charges == []
    assert recovery_queue.queue == [{"payment": "pay_123", "reason": "insufficient_funds"}]


def test_no_retries_with_rollout_flag_off(payment):
    retry.handle_failure(payment, Failure(code="processor_timeout"))

    assert processor.charges == []
    assert recovery_queue.queue == [{"payment": "pay_123", "reason": "processor_timeout"}]
