"""initial schema

Revision ID: 20260306_000001
Revises:
Create Date: 2026-03-06 00:00:01
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260306_000001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    payment_type = sa.Enum("credit", "debit", "refund", "adjustment", name="paymenttype")
    outbox_status = sa.Enum("pending", "sent", "failed", name="outboxstatus")
    saga_state = sa.Enum("pending", "completed", "failed", name="sagastate")
    payment_type.create(op.get_bind(), checkfirst=True)
    outbox_status.create(op.get_bind(), checkfirst=True)
    saga_state.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "merchants",
        sa.Column("merchant_id", sa.String(length=64), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("merchant_id"),
    )

    op.create_table(
        "payment_intents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("merchant_id", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("payment_type", payment_type, nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("reference_id", sa.String(length=128), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=False),
        sa.Column("correlation_id", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["merchant_id"], ["merchants.merchant_id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("merchant_id", "idempotency_key", name="uq_payment_intent_idem"),
    )

    op.create_table(
        "outbox_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("aggregate_id", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("headers", sa.JSON(), nullable=False),
        sa.Column("status", outbox_status, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "idempotency_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("merchant_id", sa.String(length=64), nullable=False),
        sa.Column("idem_key", sa.String(length=128), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("response_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("merchant_id", "idem_key", name="uq_idem_merchant_key"),
    )

    op.create_table(
        "ledger_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("merchant_id", sa.String(length=64), nullable=False),
        sa.Column("entry_ref", sa.String(length=128), nullable=False),
        sa.Column("payment_type", payment_type, nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("reference_id", sa.String(length=128), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=False),
        sa.Column("correlation_id", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("merchant_id", "entry_ref", name="uq_ledger_merchant_ref"),
    )
    op.create_index("ix_ledger_merchant_created_desc", "ledger_entries", ["merchant_id", "created_at"], unique=False)

    op.create_table(
        "merchant_balance",
        sa.Column("merchant_id", sa.String(length=64), nullable=False),
        sa.Column("balance", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("merchant_id"),
    )

    op.create_table(
        "saga_instances",
        sa.Column("saga_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("merchant_id", sa.String(length=64), nullable=False),
        sa.Column("state", saga_state, nullable=False),
        sa.Column("step", sa.String(length=64), nullable=False),
        sa.Column("data_json", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("saga_id"),
    )


def downgrade() -> None:
    op.drop_table("saga_instances")
    op.drop_table("merchant_balance")
    op.drop_index("ix_ledger_merchant_created_desc", table_name="ledger_entries")
    op.drop_table("ledger_entries")
    op.drop_table("idempotency_keys")
    op.drop_table("outbox_events")
    op.drop_table("payment_intents")
    op.drop_table("merchants")

    sa.Enum(name="sagastate").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="outboxstatus").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="paymenttype").drop(op.get_bind(), checkfirst=True)
