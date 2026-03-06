from app.domain.utils import stable_request_hash


def test_stable_request_hash_is_order_independent():
    a = {"merchant_id": "m_001", "amount": 100, "currency": "USD"}
    b = {"currency": "USD", "amount": 100, "merchant_id": "m_001"}
    assert stable_request_hash(a) == stable_request_hash(b)
