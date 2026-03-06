import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.mark.integration
def test_healthcheck():
    client = TestClient(app)
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
