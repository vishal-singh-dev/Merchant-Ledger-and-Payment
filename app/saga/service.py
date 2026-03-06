import logging
from dataclasses import dataclass
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Merchant, MerchantBalance, PaymentType, SagaInstance, SagaState
from app.domain.exceptions import InsufficientFundsError, MerchantNotFoundError

logger = logging.getLogger(__name__)


@dataclass
class SagaResult:
    status: str
    balance: int | None = None


class SagaOrchestrator:
    def __init__(self, db: Session):
        self.db = db

    def execute(self, saga: SagaInstance, payload: dict) -> SagaResult:
        merchant = self.db.get(Merchant, payload["merchant_id"])
        if not merchant:
            saga.state = SagaState.failed
            saga.error = "unknown_merchant"
            raise MerchantNotFoundError("unknown merchant")

        if merchant.currency != payload["currency"]:
            saga.state = SagaState.failed
            saga.error = "currency_mismatch"
            raise MerchantNotFoundError("currency mismatch")

        balance = self.db.execute(
            select(MerchantBalance).where(MerchantBalance.merchant_id == merchant.merchant_id).with_for_update()
        ).scalar_one_or_none()

        if not balance:
            balance = MerchantBalance(merchant_id=merchant.merchant_id, currency=merchant.currency, balance=0)
            self.db.add(balance)
            self.db.flush()

        payment_type = payload["payment_type"]
        amount = payload["amount"]

        if payment_type == PaymentType.debit.value and balance.balance < amount:
            saga.state = SagaState.failed
            saga.error = "insufficient_funds"
            raise InsufficientFundsError("insufficient funds")

        if payment_type == PaymentType.debit.value:
            balance.balance -= amount
        else:
            balance.balance += amount

        saga.state = SagaState.completed
        saga.step = "Completed"
        logger.info("saga_completed", extra={"correlation_id": payload["correlation_id"], "merchant_id": merchant.merchant_id})
        return SagaResult(status="COMPLETED", balance=balance.balance)
