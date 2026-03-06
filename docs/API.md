# API Documentation

Base URL (local):
- `http://localhost:5000`

OpenAPI/Swagger:
- `GET /docs`
- `GET /openapi.json`

Health:
- `GET /healthz`

Response:
```json
{"status":"ok"}
```

## Headers

Write endpoints require:
- `Idempotency-Key: <string>` (required)
- `X-Correlation-ID: <string>` (optional; auto-generated if missing)

If `Idempotency-Key` is missing, API returns:
- `400` with detail: `Idempotency-Key header is required`

## Data Models

### PaymentRequest

```json
{
  "merchant_id": "m_001",
  "amount": 100,
  "currency": "USD",
  "reference_id": "ref-100",
  "reason": "topup"
}
```

Rules:
- `merchant_id`: 1..64 chars
- `amount`: integer `> 0`
- `currency`: exactly 3 chars
- `reference_id`: 1..128 chars
- `reason`: 1..255 chars

### AcceptedResponse

```json
{
  "status": "ACCEPTED",
  "request_id": "uuid",
  "idempotency_key": "idem-1",
  "correlation_id": "corr-123"
}
```

## Endpoints

### 1) Create Credit

- `POST /v1/credits`
- Status: `202 Accepted`

Body: `PaymentRequest`  
Response: `AcceptedResponse`

Example:
```bash
curl -X POST http://localhost:5000/v1/credits \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: idem-1" \
  -H "X-Correlation-ID: corr-1" \
  -d "{\"merchant_id\":\"m_001\",\"amount\":100,\"currency\":\"USD\",\"reference_id\":\"ref-100\",\"reason\":\"topup\"}"
```

### 2) Create Debit

- `POST /v1/debits`
- Status: `202 Accepted`

Body: `PaymentRequest`  
Response: `AcceptedResponse`

Example:
```bash
curl -X POST http://localhost:5000/v1/debits \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: idem-2" \
  -d "{\"merchant_id\":\"m_001\",\"amount\":30,\"currency\":\"USD\",\"reference_id\":\"ref-101\",\"reason\":\"purchase\"}"
```

### 3) Create Refund

- `POST /v1/refunds`
- Status: `202 Accepted`

Body: `PaymentRequest`  
Response: `AcceptedResponse`

Example:
```bash
curl -X POST http://localhost:5000/v1/refunds \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: idem-3" \
  -d "{\"merchant_id\":\"m_001\",\"amount\":30,\"currency\":\"USD\",\"reference_id\":\"ref-102\",\"reason\":\"refund\"}"
```

### 4) Get Merchant Balance

- `GET /v1/merchants/{merchant_id}/balance`
- Status: `200 OK`

Response:
```json
{
  "merchant_id": "m_001",
  "currency": "USD",
  "balance": 70
}
```

If merchant is missing:
- `404` with detail: `merchant_not_found`

### 5) Get Merchant Ledger

- `GET /v1/merchants/{merchant_id}/ledger`
- Query params:
- `limit` (optional, default `50`, min `1`, max `200`)
- `cursor` (optional ISO datetime)
- Status: `200 OK`

Response:
```json
{
  "items": [
    {
      "entry_ref": "uuid",
      "payment_type": "credit",
      "amount": 100,
      "currency": "USD",
      "reference_id": "ref-100",
      "reason": "topup",
      "created_at": "2026-03-06T05:20:00.123456"
    }
  ],
  "next_cursor": "2026-03-06T05:20:00.123456"
}
```

Use `next_cursor` in the next request:
```bash
curl "http://localhost:5000/v1/merchants/m_001/ledger?limit=50&cursor=2026-03-06T05:20:00.123456"
```

## Idempotency Behavior

For write endpoints (`credits`, `debits`, `refunds`):
- same `merchant_id` + same `Idempotency-Key` + same payload: treated as the same request
- same `merchant_id` + same `Idempotency-Key` + different payload: `409` with detail `idempotency_key_payload_mismatch`

