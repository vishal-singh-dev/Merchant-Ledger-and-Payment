import json
from confluent_kafka import Consumer, Producer

from app.broker.base import BrokerConsumer, BrokerMessage, BrokerPublisher
from app.config import settings


class KafkaBroker(BrokerPublisher, BrokerConsumer):
    def __init__(self) -> None:
        self.producer = Producer({"bootstrap.servers": settings.kafka_bootstrap_servers})
        self.consumer = Consumer(
            {
                "bootstrap.servers": settings.kafka_bootstrap_servers,
                "group.id": settings.kafka_group_id,
                "enable.auto.commit": False,
                "auto.offset.reset": "earliest",
            }
        )
        self.consumer.subscribe([settings.kafka_topic])

    def publish(self, key: str, value: dict, headers: dict) -> None:
        self.producer.produce(
            topic=settings.kafka_topic,
            key=key.encode("utf-8"),
            value=json.dumps(value).encode("utf-8"),
            headers={k: str(v) for k, v in headers.items()},
        )
        self.producer.flush(3)

    def publish_dlq(self, key: str, value: dict, headers: dict, error: str) -> None:
        dlq_headers = {**headers, "error": error}
        self.producer.produce(
            topic=settings.kafka_dlq_topic,
            key=key.encode("utf-8"),
            value=json.dumps(value).encode("utf-8"),
            headers=dlq_headers,
        )
        self.producer.flush(3)

    def poll(self, timeout: float = 1.0) -> list[BrokerMessage]:
        msg = self.consumer.poll(timeout)
        if msg is None:
            return []
        if msg.error():
            return []
        headers = {k: v.decode("utf-8") if isinstance(v, bytes) else v for k, v in (msg.headers() or [])}
        return [
            BrokerMessage(
                key=msg.key().decode("utf-8"),
                value=json.loads(msg.value().decode("utf-8")),
                headers=headers,
                raw=msg,
            )
        ]

    def ack(self, message: BrokerMessage) -> None:
        self.consumer.commit(message=message.raw, asynchronous=False)
