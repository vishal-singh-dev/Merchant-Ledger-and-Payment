from fastapi import FastAPI

from app.api.middleware import CorrelationIdMiddleware
from app.api.routes import router
from app.config import settings
from app.logging_config import configure_logging

configure_logging(settings.log_level)
app = FastAPI(title="Merchant Ledger & Payments", version="1.0.0")
app.add_middleware(CorrelationIdMiddleware)
app.include_router(router)


@app.get("/healthz")
def healthcheck():
    return {"status": "ok"}
