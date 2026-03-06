# Merchant Ledger & Payments Service

Production-style sample service implementing append-only ledger, idempotent processing, outbox pattern, saga orchestration, and broker abstraction for Kafka or SQS FIFO.

## Features

- FastAPI endpoints for `credit`, `debit`, `refund`
- Append-only `ledger_entries` + `merchant_balance` read model
- Idempotency protection with DB unique constraints
- Outbox publisher with `FOR UPDATE SKIP LOCKED`
- Single-writer ordering by merchant key
  - Kafka topic key = `merchant_id`
  - SQS FIFO `MessageGroupId = merchant_id`
- DLQ support and poison-message routing
- Saga state persistence + compensation marker strategy (`FAILED` + reconcile path)
- Structured logs with correlation IDs

## Repo Layout

- `app/api`: HTTP layer
- `app/workers`: outbox publisher and processor
- `app/domain`: schemas and domain exceptions
- `app/db`: SQLAlchemy models/session
- `app/broker`: Kafka/SQS implementations
- `app/saga`: saga orchestration logic

## Local Run (Docker Compose)

1. Copy env file: `cp .env.example .env`
2. Start infra and services: `docker compose up --build`
3. Run seed once in API container shell or local env:
   - `python -m app.scripts.seed_merchants`

## Reproducible Python Setup (uv)

1. Install deps from lockfile: `uv sync --all-groups`
2. Run commands in env: `uv run -m pytest -q`

## Switch Broker

- Kafka (default): `BROKER_TYPE=kafka`
- SQS FIFO: `BROKER_TYPE=sqs`

## API

- `POST /v1/credits`
- `POST /v1/debits`
- `POST /v1/refunds`
- `GET /v1/merchants/{merchant_id}/balance`
- `GET /v1/merchants/{merchant_id}/ledger?limit=50&cursor=...`

Detailed endpoint docs:
- `docs/API.md`

Required header on writes:
- `Idempotency-Key: <key>`

### Curl Demo

```bash
# credit 100
curl -X POST http://localhost:8000/v1/credits \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: idem-1' \
  -H 'X-Correlation-ID: corr-demo-1' \
  -d '{"merchant_id":"m_001","amount":100,"currency":"USD","reference_id":"ref-100","reason":"topup"}'

# debit 30
curl -X POST http://localhost:8000/v1/debits \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: idem-2' \
  -d '{"merchant_id":"m_001","amount":30,"currency":"USD","reference_id":"ref-101","reason":"purchase"}'

# refund 30
curl -X POST http://localhost:8000/v1/refunds \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: idem-3' \
  -d '{"merchant_id":"m_001","amount":30,"currency":"USD","reference_id":"ref-102","reason":"refund"}'

# read balance + ledger
curl http://localhost:8000/v1/merchants/m_001/balance
curl http://localhost:8000/v1/merchants/m_001/ledger
```

### At-Least-Once / Duplicate Demo

- Re-publish the same event to broker with same `idempotency_key`.
- Processor returns prior idempotent response; ledger is not double-appended (`UNIQUE(merchant_id, entry_ref)`).

### Poison Demo

- Send a message with same `idempotency_key` and different amount/request hash.
- Processor detects hash mismatch and routes message to DLQ.

## DLQ Replay Tools

- Kafka replay: `python -m app.scripts.replay_kafka_dlq`
- SQS replay: `python -m app.scripts.replay_sqs_dlq`

## Tests

- All tests: `make test`
- Unit only: `make test-unit`
- Integration only: `make test-integration`

Integration tests are marked `integration` and intended to run with docker/testcontainers.
