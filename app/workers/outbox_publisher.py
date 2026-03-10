import logging
import time
from datetime import datetime

from sqlalchemy import select

from app.broker.factory import get_broker
from app.config import settings
from app.db.models import OutboxEvent, OutboxStatus
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)


def run_outbox_publisher() -> None:
    broker = get_broker()
    logger.info("outbox_publisher_started", extra={"correlation_id": ""})
    while True:
        with SessionLocal() as db:
            events = db.execute(
                select(OutboxEvent)
                .where(OutboxEvent.status == OutboxStatus.pending)
                .with_for_update(skip_locked=True)
                .limit(settings.outbox_batch_size)
            ).scalars().all()

            if events:
                logger.info(
                    "outbox_batch_fetched",
                    extra={"correlation_id": "", "batch_size": len(events)},
                )

            for event in events:
                try:
                    logger.info(
                        "outbox_publish_attempt",
                        extra={
                            "correlation_id": event.headers.get("correlation_id", ""),
                            "event_id": str(event.id),
                            "aggregate_id": event.aggregate_id,
                            "event_type": event.event_type,
                        },
                    )
                    broker.publish(key=event.aggregate_id, value=event.payload, headers=event.headers)
                    event.status = OutboxStatus.sent
                    event.sent_at = datetime.utcnow()
                    logger.info(
                        "outbox_sent",
                        extra={"correlation_id": event.headers.get("correlation_id", ""), "event_id": str(event.id)},
                    )
                except Exception as exc:
                    logger.exception(
                        "outbox_send_failed",
                        extra={
                            "correlation_id": event.headers.get("correlation_id", ""),
                            "event_id": str(event.id),
                            "error": str(exc),
                        },
                    )
                    event.status = OutboxStatus.failed
            db.commit()
        time.sleep(settings.outbox_poll_seconds)


if __name__ == "__main__":
    run_outbox_publisher()
