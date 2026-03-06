import boto3
from app.config import settings


def replay() -> None:
    sqs = boto3.client("sqs", region_name=settings.aws_region, endpoint_url=settings.localstack_endpoint_url)
    while True:
        resp = sqs.receive_message(
            QueueUrl=settings.sqs_dlq_url,
            MaxNumberOfMessages=10,
            WaitTimeSeconds=1,
            MessageAttributeNames=["All"],
        )
        messages = resp.get("Messages", [])
        if not messages:
            break

        for msg in messages:
            attrs = msg.get("MessageAttributes", {})
            merchant_id = attrs.get("merchant_id", {}).get("StringValue", "unknown")
            idem_key = attrs.get("idempotency_key", {}).get("StringValue", msg["MessageId"])
            sqs.send_message(
                QueueUrl=settings.sqs_queue_url,
                MessageBody=msg["Body"],
                MessageGroupId=merchant_id,
                MessageDeduplicationId=f"replay-{idem_key}",
                MessageAttributes=attrs,
            )
            sqs.delete_message(QueueUrl=settings.sqs_dlq_url, ReceiptHandle=msg["ReceiptHandle"])


if __name__ == "__main__":
    replay()
