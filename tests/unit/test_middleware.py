from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.middleware import CorrelationIdMiddleware


def test_correlation_id_middleware_sets_header():
    app = FastAPI()
    app.add_middleware(CorrelationIdMiddleware)

    @app.get("/ping")
    def ping():
        return {"ok": True}

    client = TestClient(app)
    resp = client.get("/ping", headers={"X-Correlation-ID": "corr-123"})
    assert resp.status_code == 200
    assert resp.headers["X-Correlation-ID"] == "corr-123"
