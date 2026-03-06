import pytest

from app.domain.exceptions import PoisonMessageError
from app.workers.processor import _process_payload


class _ExistingIdem:
    request_hash = "old_hash"
    response_json = {"status": "completed"}


class _Result:
    def __init__(self, obj):
        self.obj = obj

    def scalar_one_or_none(self):
        return self.obj


class FakeDb:
    def get(self, model, merchant_id):
        class M:
            merchant_id = "m_001"
            currency = "USD"

        return M()

    def execute(self, *args, **kwargs):
        return _Result(_ExistingIdem())


def test_idempotency_hash_mismatch_raises_poison():
    payload = {
        "merchant_id": "m_001",
        "idempotency_key": "idem-1",
        "request_hash": "new_hash",
        "payment_type": "credit",
        "amount": 10,
        "currency": "USD",
    }
    with pytest.raises(PoisonMessageError):
        _process_payload(FakeDb(), payload, {})
