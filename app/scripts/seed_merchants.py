from app.db.session import SessionLocal
from app.db.models import Merchant, MerchantBalance


def seed() -> None:
    merchants = [
        ("m_001", "USD"),
        ("m_002", "USD"),
        ("m_003", "INR"),
    ]
    with SessionLocal() as db:
        for merchant_id, currency in merchants:
            existing = db.get(Merchant, merchant_id)
            if existing:
                continue
            db.add(Merchant(merchant_id=merchant_id, currency=currency))
            db.add(MerchantBalance(merchant_id=merchant_id, currency=currency, balance=0))
        db.commit()


if __name__ == "__main__":
    seed()
