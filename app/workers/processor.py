import logging
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.broker.factory import get_broker
from app.db.models import IdempotencyKey, LedgerEntry, Merchant, PaymentType, SagaInstance, SagaState
from app.db.session import SessionLocal
from app.domain.exceptions import InsufficientFundsError, MerchantNotFoundError, PoisonMessageError
from app.saga.service import SagaOrchestrator

logger = logging.getLogger(__name__)


POISON_ERRORS = (PoisonMessageError, MerchantNotFoundError)


def _process_payload(db, payload: dict, headers: dict):
    required = ["merchant_id", "idempotency_key", "request_hash", "payment_type", "amount", "currency"]
    if any(k not in payload for k in required):
        raise PoisonMessageError("invalid_schema")

    merchant = db.get(Merchant, payload["merchant_id"])
    if not merchant:
        raise MerchantNotFoundError("unknown_merchant")

    existing = db.execute(
        select(IdempotencyKey).where(
            IdempotencyKey.merchant_id == payload["merchant_id"],
            IdempotencyKey.idem_key == payload["idempotency_key"],
        )
    ).scalar_one_or_none()

    if existing:
        if existing.request_hash != payload["request_hash"]:
            raise PoisonMessageError("idempotency_hash_mismatch")
        return existing.response_json

    saga = db.execute(
        select(SagaInstance).where(
            SagaInstance.merchant_id == payload["merchant_id"],
            SagaInstance.data_json["idempotency_key"].astext == payload["idempotency_key"],
        )
    ).scalar_one_or_none()

    if not saga:
        saga = SagaInstance(merchant_id=payload["merchant_id"], step="Validate", data_json=payload)
        db.add(saga)
        db.flush()

    orchestrator = SagaOrchestrator(db)
    result = orchestrator.execute(saga, payload)

    ledger = LedgerEntry(
        merchant_id=payload["merchant_id"],
        entry_ref=payload["idempotency_key"],
        payment_type=PaymentType(payload["payment_type"]),
        amount=payload["amount"],
        currency=payload["currency"],
        reference_id=payload.get("reference_id", payload["idempotency_key"]),
        reason=payload.get("reason", "n/a"),
        correlation_id=payload.get("correlation_id", ""),
        created_at=datetime.utcnow(),
    )
    db.add(ledger)

    response = {"status": result.status, "balance": result.balance}
    idem = IdempotencyKey(
        merchant_id=payload["merchant_id"],
        idem_key=payload["idempotency_key"],
        request_hash=payload["request_hash"],
        status=result.status,
        response_json=response,
    )
    db.add(idem)
    return response


def run_processor() -> None:
    broker = get_broker()
    while True:
        messages = broker.poll(timeout=1.0)
        for message in messages:
            try:
                with SessionLocal() as db:
                    _process_payload(db, message.value, message.headers)
                    db.commit()
                broker.ack(message)
            except InsufficientFundsError as exc:
                with SessionLocal() as db:
                    saga = db.execute(
                        select(SagaInstance).where(
                            SagaInstance.merchant_id == message.value["merchant_id"],
                            SagaInstance.data_json["idempotency_key"].astext == message.value["idempotency_key"],
                        )
                    ).scalar_one_or_none()
                    if saga:
                        saga.state = SagaState.failed
                        saga.error = str(exc)
                        db.commit()
                broker.publish_dlq(message.key, message.value, message.headers, str(exc))
                broker.ack(message)
            except POISON_ERRORS as exc:
                logger.exception("poison_message", extra={"correlation_id": message.headers.get("correlation_id", "")})
                broker.publish_dlq(message.key, message.value, message.headers, str(exc))
                broker.ack(message)
            except IntegrityError:
                with SessionLocal() as db:
                    db.rollback()
                broker.ack(message)
            except Exception:
                logger.exception("processor_transient_failure", extra={"correlation_id": message.headers.get("correlation_id", "")})


if __name__ == "__main__":
    run_processor()
