from app.broker.kafka import KafkaBroker
from app.broker.sqs import SqsFifoBroker
from app.config import settings


def get_broker():
    if settings.broker_type.lower() == "sqs":
        return SqsFifoBroker()
    return KafkaBroker()
