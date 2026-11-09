from payments import processor, recovery_queue, retry
from payments.models import Failure


def test_failed_payment_goes_to_manual_recovery(payment):
    retry.handle_failure(payment, Failure(code="processor_timeout"))

    assert recovery_queue.queue == [{"payment": "pay_123", "reason": "processor_timeout"}]
    assert processor.charges == []
