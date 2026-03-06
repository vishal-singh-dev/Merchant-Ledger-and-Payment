import json
from confluent_kafka import Consumer, Producer
from app.config import settings


def replay() -> None:
    consumer = Consumer(
        {
            "bootstrap.servers": settings.kafka_bootstrap_servers,
            "group.id": "merchant-dlq-replay",
            "enable.auto.commit": False,
            "auto.offset.reset": "earliest",
        }
    )
    producer = Producer({"bootstrap.servers": settings.kafka_bootstrap_servers})
    consumer.subscribe([settings.kafka_dlq_topic])

    while True:
        msg = consumer.poll(1.0)
        if msg is None:
            break
        if msg.error():
            continue
        payload = json.loads(msg.value().decode("utf-8"))
        producer.produce(settings.kafka_topic, key=msg.key(), value=json.dumps(payload).encode("utf-8"), headers=msg.headers())
        producer.flush()
        consumer.commit(message=msg, asynchronous=False)


if __name__ == "__main__":
    replay()
