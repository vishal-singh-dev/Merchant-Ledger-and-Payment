import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.mark.integration
def test_healthcheck():
    client = TestClient(app)
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.integration
def test_generate_idempotency_key():
    client = TestClient(app)
    resp = client.get("/v1/idempotency-key")
    assert resp.status_code == 200
    body = resp.json()
    assert "idempotency_key" in body
    assert isinstance(body["idempotency_key"], str)
    assert len(body["idempotency_key"]) > 0


@pytest.mark.integration
def test_get_ledger_invalid_cursor_returns_400():
    client = TestClient(app)
    resp = client.get("/v1/merchants/m_001/ledger?cursor=invalid-datetime")
    assert resp.status_code == 400
    assert "invalid_cursor" in resp.json()["detail"]
