from datetime import datetime
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import desc, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import correlation_id_header, idempotency_key_header
from app.db.models import LedgerEntry, Merchant, MerchantBalance, OutboxEvent, OutboxStatus, PaymentIntent, PaymentType, SagaInstance, SagaState
from app.db.session import get_db
from app.domain.schemas import (
    AcceptedResponse,
    BalanceResponse,
    IdempotencyKeyResponse,
    LedgerEntryResponse,
    LedgerPageResponse,
    MerchantRegisterRequest,
    MerchantRegisterResponse,
    PaymentRequest,
)
from app.domain.utils import stable_request_hash

router = APIRouter(prefix="/v1")


def _raise_unexpected(exc: Exception) -> None:
    raise HTTPException(status_code=500, detail=str(exc))


def _map_integrity_error(exc: IntegrityError) -> HTTPException:
    constraint_name = getattr(getattr(exc.orig, "diag", None), "constraint_name", "")
    if constraint_name == "payment_intents_merchant_id_fkey":
        return HTTPException(status_code=404, detail="merchant_not_found")
    error_detail = str(exc.orig) if getattr(exc, "orig", None) else str(exc)
    return HTTPException(status_code=409, detail=error_detail)


@router.get("/idempotency-key", response_model=IdempotencyKeyResponse)
def generate_idempotency_key() -> IdempotencyKeyResponse:
    try:
        return IdempotencyKeyResponse(idempotency_key=str(uuid.uuid4()))
    except HTTPException:
        raise
    except Exception as exc:
        _raise_unexpected(exc)


@router.post("/merchants", response_model=MerchantRegisterResponse, status_code=201)
def register_merchant(payload: MerchantRegisterRequest, db: Session = Depends(get_db)) -> MerchantRegisterResponse:
    try:
        merchant = Merchant(merchant_id=payload.merchant_id, currency=payload.currency.upper())
        balance = MerchantBalance(merchant_id=payload.merchant_id, currency=payload.currency.upper(), balance=0)
        db.add(merchant)
        db.add(balance)
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            constraint_name = getattr(getattr(exc.orig, "diag", None), "constraint_name", "")
            if constraint_name == "merchants_pkey":
                raise HTTPException(status_code=409, detail="merchant_already_exists")
            error_detail = str(exc.orig) if getattr(exc, "orig", None) else str(exc)
            raise HTTPException(status_code=409, detail=error_detail)
        return MerchantRegisterResponse(merchant_id=merchant.merchant_id, currency=merchant.currency, balance=balance.balance)
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        _raise_unexpected(exc)


def _enqueue(
    payment_type: PaymentType,
    payload: PaymentRequest,
    idempotency_key: str,
    correlation_id: str,
    db: Session,
) -> AcceptedResponse:
    try:
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
        except IntegrityError as exc:
            db.rollback()
            existing = db.execute(
                select(PaymentIntent).where(
                    PaymentIntent.merchant_id == payload.merchant_id,
                    PaymentIntent.idempotency_key == idempotency_key,
                )
            ).scalar_one_or_none()
            if existing:
                if existing.request_hash != request_hash:
                    raise HTTPException(status_code=409, detail="idempotency_key_payload_mismatch")
                intent = existing
            else:
                raise _map_integrity_error(exc)

        return AcceptedResponse(
            status="ACCEPTED",
            request_id=str(intent.id),
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
        )
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        _raise_unexpected(exc)


@router.post("/credits", response_model=AcceptedResponse, status_code=202)
def create_credit(
    payload: PaymentRequest,
    request: Request,
    idempotency_key: str = Depends(idempotency_key_header),
    correlation_id: str = Depends(correlation_id_header),
    db: Session = Depends(get_db),
):
    try:
        return _enqueue(PaymentType.credit, payload, idempotency_key, correlation_id, db)
    except HTTPException:
        raise
    except Exception as exc:
        _raise_unexpected(exc)


@router.post("/debits", response_model=AcceptedResponse, status_code=202)
def create_debit(
    payload: PaymentRequest,
    request: Request,
    idempotency_key: str = Depends(idempotency_key_header),
    correlation_id: str = Depends(correlation_id_header),
    db: Session = Depends(get_db),
):
    try:
        return _enqueue(PaymentType.debit, payload, idempotency_key, correlation_id, db)
    except HTTPException:
        raise
    except Exception as exc:
        _raise_unexpected(exc)


@router.post("/refunds", response_model=AcceptedResponse, status_code=202)
def create_refund(
    payload: PaymentRequest,
    request: Request,
    idempotency_key: str = Depends(idempotency_key_header),
    correlation_id: str = Depends(correlation_id_header),
    db: Session = Depends(get_db),
):
    try:
        return _enqueue(PaymentType.refund, payload, idempotency_key, correlation_id, db)
    except HTTPException:
        raise
    except Exception as exc:
        _raise_unexpected(exc)


@router.get("/merchants/{merchant_id}/balance", response_model=BalanceResponse)
def get_balance(merchant_id: str, db: Session = Depends(get_db)):
    try:
        balance = db.get(MerchantBalance, merchant_id)
        if not balance:
            raise HTTPException(status_code=404, detail="merchant_not_found")
        return BalanceResponse(merchant_id=merchant_id, currency=balance.currency, balance=balance.balance)
    except HTTPException:
        raise
    except Exception as exc:
        _raise_unexpected(exc)


@router.get("/merchants/{merchant_id}/ledger", response_model=LedgerPageResponse)
def get_ledger(
    merchant_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = None,
    db: Session = Depends(get_db),
):
    try:
        q = select(LedgerEntry).where(LedgerEntry.merchant_id == merchant_id)
        if cursor:
            try:
                cursor_dt = datetime.fromisoformat(cursor)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=f"invalid_cursor: {exc}")
            q = q.where(LedgerEntry.created_at < cursor_dt)
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
    except HTTPException:
        raise
    except Exception as exc:
        _raise_unexpected(exc)
