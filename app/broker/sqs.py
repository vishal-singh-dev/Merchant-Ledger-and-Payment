import json
import boto3

from app.broker.base import BrokerConsumer, BrokerMessage, BrokerPublisher
from app.config import settings


class SqsFifoBroker(BrokerPublisher, BrokerConsumer):
    def __init__(self) -> None:
        self.client = boto3.client("sqs", region_name=settings.aws_region, endpoint_url=settings.localstack_endpoint_url)

    def publish(self, key: str, value: dict, headers: dict) -> None:
        self.client.send_message(
            QueueUrl=settings.sqs_queue_url,
            MessageBody=json.dumps(value),
            MessageGroupId=key,
            MessageDeduplicationId=headers["idempotency_key"],
            MessageAttributes={
                k: {"DataType": "String", "StringValue": str(v)} for k, v in headers.items()
            },
        )

    def publish_dlq(self, key: str, value: dict, headers: dict, error: str) -> None:
        attrs = {k: {"DataType": "String", "StringValue": str(v)} for k, v in headers.items()}
        attrs["error"] = {"DataType": "String", "StringValue": error}
        self.client.send_message(
            QueueUrl=settings.sqs_dlq_url,
            MessageBody=json.dumps(value),
            MessageGroupId=key,
            MessageDeduplicationId=f"{headers['idempotency_key']}-dlq",
            MessageAttributes=attrs,
        )

    def poll(self, timeout: float = 1.0) -> list[BrokerMessage]:
        response = self.client.receive_message(
            QueueUrl=settings.sqs_queue_url,
            MaxNumberOfMessages=10,
            WaitTimeSeconds=int(timeout),
            MessageAttributeNames=["All"],
        )
        messages = []
        for m in response.get("Messages", []):
            attrs = m.get("MessageAttributes", {})
            headers = {k: v.get("StringValue", "") for k, v in attrs.items()}
            body = json.loads(m["Body"])
            key = body.get("merchant_id", "")
            messages.append(BrokerMessage(key=key, value=body, headers=headers, raw=m))
        return messages

    def ack(self, message: BrokerMessage) -> None:
        self.client.delete_message(QueueUrl=settings.sqs_queue_url, ReceiptHandle=message.raw["ReceiptHandle"])
