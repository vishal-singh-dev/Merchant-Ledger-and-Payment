from fastapi import FastAPI

from app.api.middleware import CorrelationIdMiddleware
from app.api.routes import router
from app.config import settings
from app.logging_config import configure_logging

configure_logging(
    settings.log_level,
    settings.log_to_file,
    settings.log_file_path,
    settings.log_file_max_bytes,
    settings.log_file_backup_count,
)
app = FastAPI(title="Merchant Ledger & Payments", version="1.0.0")
app.add_middleware(CorrelationIdMiddleware)
app.include_router(router)


@app.get("/healthz")
def healthcheck():
    return {"status": "ok"}
