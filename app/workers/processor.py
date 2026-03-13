import logging
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.broker.factory import get_broker
from app.config import settings
from app.db.models import IdempotencyKey, LedgerEntry, Merchant, PaymentType, SagaInstance, SagaState
from app.db.session import SessionLocal
from app.domain.exceptions import InsufficientFundsError, MerchantNotFoundError, PoisonMessageError
from app.logging_config import configure_logging
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
        logger.info(
            "processor_idempotent_hit",
            extra={
                "correlation_id": payload.get("correlation_id", headers.get("correlation_id", "")),
                "merchant_id": payload.get("merchant_id", ""),
                "idempotency_key": payload.get("idempotency_key", ""),
            },
        )
        return existing.response_json

    saga = db.execute(
        select(SagaInstance).where(
            SagaInstance.merchant_id == payload["merchant_id"],
            SagaInstance.data_json["idempotency_key"].as_string() == payload["idempotency_key"],
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
    logger.info(
        "processor_payload_applied",
        extra={
            "correlation_id": payload.get("correlation_id", headers.get("correlation_id", "")),
            "merchant_id": payload.get("merchant_id", ""),
            "idempotency_key": payload.get("idempotency_key", ""),
            "status": result.status,
            "balance": result.balance,
        },
    )
    return response


def run_processor() -> None:
    configure_logging(
        settings.log_level,
        settings.log_to_file,
        settings.log_file_path,
        settings.log_file_max_bytes,
        settings.log_file_backup_count,
    )
    broker = get_broker()
    logger.info("processor_started", extra={"correlation_id": ""})
    while True:
        messages = broker.poll(timeout=1.0)
        if messages:
            logger.info("processor_batch_polled", extra={"correlation_id": "", "batch_size": len(messages)})
        for message in messages:
            try:
                logger.info(
                    "processor_message_received",
                    extra={
                        "correlation_id": message.headers.get("correlation_id", ""),
                        "merchant_id": message.value.get("merchant_id", ""),
                        "idempotency_key": message.value.get("idempotency_key", ""),
                    },
                )
                with SessionLocal() as db:
                    _process_payload(db, message.value, message.headers)
                    db.commit()
                broker.ack(message)
                logger.info(
                    "processor_message_acked",
                    extra={
                        "correlation_id": message.headers.get("correlation_id", ""),
                        "merchant_id": message.value.get("merchant_id", ""),
                        "idempotency_key": message.value.get("idempotency_key", ""),
                    },
                )
            except InsufficientFundsError as exc:
                with SessionLocal() as db:
                    saga = db.execute(
                        select(SagaInstance).where(
                            SagaInstance.merchant_id == message.value["merchant_id"],
                            SagaInstance.data_json["idempotency_key"].as_string() == message.value["idempotency_key"],
                        )
                    ).scalar_one_or_none()
                    if saga:
                        saga.state = SagaState.failed
                        saga.error = str(exc)
                        db.commit()
                broker.publish_dlq(message.key, message.value, message.headers, str(exc))
                broker.ack(message)
                logger.warning(
                    "processor_insufficient_funds_dlq",
                    extra={
                        "correlation_id": message.headers.get("correlation_id", ""),
                        "merchant_id": message.value.get("merchant_id", ""),
                        "idempotency_key": message.value.get("idempotency_key", ""),
                        "error": str(exc),
                    },
                )
            except POISON_ERRORS as exc:
                logger.exception(
                    "poison_message",
                    extra={
                        "correlation_id": message.headers.get("correlation_id", ""),
                        "merchant_id": message.value.get("merchant_id", ""),
                        "idempotency_key": message.value.get("idempotency_key", ""),
                        "error": str(exc),
                    },
                )
                broker.publish_dlq(message.key, message.value, message.headers, str(exc))
                broker.ack(message)
            except IntegrityError as exc:
                logger.exception(
                    "processor_integrity_error",
                    extra={
                        "correlation_id": message.headers.get("correlation_id", ""),
                        "merchant_id": message.value.get("merchant_id", ""),
                        "idempotency_key": message.value.get("idempotency_key", ""),
                        "error": str(exc),
                    },
                )
                with SessionLocal() as db:
                    db.rollback()
                broker.ack(message)
            except Exception:
                logger.exception(
                    "processor_transient_failure",
                    extra={
                        "correlation_id": message.headers.get("correlation_id", ""),
                        "merchant_id": message.value.get("merchant_id", ""),
                        "idempotency_key": message.value.get("idempotency_key", ""),
                    },
                )


if __name__ == "__main__":
    run_processor()
