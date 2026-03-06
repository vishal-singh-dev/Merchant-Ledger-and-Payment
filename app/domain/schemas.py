from datetime import datetime
from pydantic import BaseModel, Field


class PaymentRequest(BaseModel):
    merchant_id: str = Field(min_length=1, max_length=64)
    amount: int = Field(gt=0)
    currency: str = Field(min_length=3, max_length=3)
    reference_id: str = Field(min_length=1, max_length=128)
    reason: str = Field(min_length=1, max_length=255)


class AcceptedResponse(BaseModel):
    status: str
    request_id: str
    idempotency_key: str
    correlation_id: str


class BalanceResponse(BaseModel):
    merchant_id: str
    currency: str
    balance: int


class LedgerEntryResponse(BaseModel):
    entry_ref: str
    payment_type: str
    amount: int
    currency: str
    reference_id: str
    reason: str
    created_at: datetime


class LedgerPageResponse(BaseModel):
    items: list[LedgerEntryResponse]
    next_cursor: str | None = None
