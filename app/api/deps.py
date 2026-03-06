from fastapi import Header, HTTPException, Request


def idempotency_key_header(idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")) -> str:
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="Idempotency-Key header is required")
    return idempotency_key


def correlation_id_header(request: Request) -> str:
    correlation_id = request.headers.get("X-Correlation-ID")
    if correlation_id:
        return correlation_id
    return request.state.correlation_id
