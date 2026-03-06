from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "merchant-ledger"
    env: str = "dev"
    log_level: str = "INFO"

    database_url: str = "postgresql+psycopg://ledger:ledger@localhost:5432/ledger"

    broker_type: str = "kafka"
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_topic: str = "merchant-events"
    kafka_dlq_topic: str = "merchant-events-dlq"
    kafka_group_id: str = "merchant-processor"

    aws_region: str = "us-east-1"
    localstack_endpoint_url: str = "http://localhost:4566"
    sqs_queue_url: str = "http://localhost:4566/000000000000/merchant-events.fifo"
    sqs_dlq_url: str = "http://localhost:4566/000000000000/merchant-events-dlq"

    outbox_poll_seconds: float = 1.0
    outbox_batch_size: int = 50

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
