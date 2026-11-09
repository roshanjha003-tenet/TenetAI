from datetime import timedelta

import pytest

from payments import clock, flags, processor, recovery_queue
from payments.models import Payment


@pytest.fixture(autouse=True)
def clean_state():
    flags.reset()
    processor.charges.clear()
    recovery_queue.queue.clear()
    yield


@pytest.fixture
def payment() -> Payment:
    return Payment(
        id="pay_123",
        amount_cents=4999,
        idempotency_key="idem_pay_123",
        first_attempt_at=clock.now() - timedelta(minutes=5),
    )
