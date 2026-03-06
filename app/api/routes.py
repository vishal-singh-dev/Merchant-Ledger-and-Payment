from datetime import datetime
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import desc, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import correlation_id_header, idempotency_key_header
from app.db.models import LedgerEntry, MerchantBalance, OutboxEvent, OutboxStatus, PaymentIntent, PaymentType, SagaInstance, SagaState
from app.db.session import get_db
from app.domain.schemas import AcceptedResponse, BalanceResponse, LedgerEntryResponse, LedgerPageResponse, PaymentRequest
from app.domain.utils import stable_request_hash

router = APIRouter(prefix="/v1")


def _enqueue(
    payment_type: PaymentType,
    payload: PaymentRequest,
    idempotency_key: str,
    correlation_id: str,
    db: Session,
) -> AcceptedResponse:
    body = payload.model_dump()
    request_hash = stable_request_hash({**body, "payment_type": payment_type.value})

    intent = PaymentIntent(
        merchant_id=payload.merchant_id,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        payment_type=payment_type,
        amount=payload.amount,
        currency=payload.currency.upper(),
        reference_id=payload.reference_id,
        reason=payload.reason,
        correlation_id=correlation_id,
    )

    message_payload = {
        "merchant_id": payload.merchant_id,
        "payment_type": payment_type.value,
        "amount": payload.amount,
        "currency": payload.currency.upper(),
        "reference_id": payload.reference_id,
        "reason": payload.reason,
        "idempotency_key": idempotency_key,
        "request_hash": request_hash,
        "correlation_id": correlation_id,
        "created_at": datetime.utcnow().isoformat(),
    }

    saga = SagaInstance(merchant_id=payload.merchant_id, state=SagaState.pending, step="Validate", data_json=message_payload)

    outbox = OutboxEvent(
        aggregate_id=payload.merchant_id,
        idempotency_key=idempotency_key,
        event_type="PaymentRequested",
        payload=message_payload,
        headers={
            "merchant_id": payload.merchant_id,
            "idempotency_key": idempotency_key,
            "correlation_id": correlation_id,
        },
        status=OutboxStatus.pending,
    )

    db.add(intent)
    db.add(saga)
    db.add(outbox)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.execute(
            select(PaymentIntent).where(
                PaymentIntent.merchant_id == payload.merchant_id,
                PaymentIntent.idempotency_key == idempotency_key,
            )
        ).scalar_one_or_none()
        if not existing:
            raise HTTPException(status_code=409, detail="idempotency_conflict")
        if existing.request_hash != request_hash:
            raise HTTPException(status_code=409, detail="idempotency_key_payload_mismatch")

    return AcceptedResponse(
        status="ACCEPTED",
        request_id=str(intent.id),
        idempotency_key=idempotency_key,
        correlation_id=correlation_id,
    )


@router.post("/credits", response_model=AcceptedResponse, status_code=202)
def create_credit(
    payload: PaymentRequest,
    request: Request,
    idempotency_key: str = Depends(idempotency_key_header),
    correlation_id: str = Depends(correlation_id_header),
    db: Session = Depends(get_db),
):
    return _enqueue(PaymentType.credit, payload, idempotency_key, correlation_id, db)


@router.post("/debits", response_model=AcceptedResponse, status_code=202)
def create_debit(
    payload: PaymentRequest,
    request: Request,
    idempotency_key: str = Depends(idempotency_key_header),
    correlation_id: str = Depends(correlation_id_header),
    db: Session = Depends(get_db),
):
    return _enqueue(PaymentType.debit, payload, idempotency_key, correlation_id, db)


@router.post("/refunds", response_model=AcceptedResponse, status_code=202)
def create_refund(
    payload: PaymentRequest,
    request: Request,
    idempotency_key: str = Depends(idempotency_key_header),
    correlation_id: str = Depends(correlation_id_header),
    db: Session = Depends(get_db),
):
    return _enqueue(PaymentType.refund, payload, idempotency_key, correlation_id, db)


@router.get("/merchants/{merchant_id}/balance", response_model=BalanceResponse)
def get_balance(merchant_id: str, db: Session = Depends(get_db)):
    balance = db.get(MerchantBalance, merchant_id)
    if not balance:
        raise HTTPException(status_code=404, detail="merchant_not_found")
    return BalanceResponse(merchant_id=merchant_id, currency=balance.currency, balance=balance.balance)


@router.get("/merchants/{merchant_id}/ledger", response_model=LedgerPageResponse)
def get_ledger(
    merchant_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = None,
    db: Session = Depends(get_db),
):
    q = select(LedgerEntry).where(LedgerEntry.merchant_id == merchant_id)
    if cursor:
        q = q.where(LedgerEntry.created_at < datetime.fromisoformat(cursor))
    q = q.order_by(desc(LedgerEntry.created_at)).limit(limit)

    items = db.execute(q).scalars().all()
    response_items = [
        LedgerEntryResponse(
            entry_ref=i.entry_ref,
            payment_type=i.payment_type.value,
            amount=i.amount,
            currency=i.currency,
            reference_id=i.reference_id,
            reason=i.reason,
            created_at=i.created_at,
        )
        for i in items
    ]
    next_cursor = items[-1].created_at.isoformat() if len(items) == limit else None
    return LedgerPageResponse(items=response_items, next_cursor=next_cursor)
