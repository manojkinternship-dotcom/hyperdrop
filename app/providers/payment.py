from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from sqlmodel import Session, select
from app.models import Payment, Order
from app.database import engine

class PaymentProvider(ABC):
    @abstractmethod
    def create_payment_link(self, order_id: int, amount: float) -> str:
        """Generate a UPI payment link for the customer."""
        pass

    @abstractmethod
    def verify_payment(self, payment_id: int, transaction_ref: str) -> bool:
        """Confirm payment status."""
        pass

class MockUPIPaymentProvider(PaymentProvider):
    def create_payment_link(self, order_id: int, amount: float) -> str:
        with Session(engine) as session:
            # Check existing payment record
            payment = session.exec(select(Payment).where(Payment.order_id == order_id)).first()
            link = f"https://pay.hyperdrop.in/upi/{order_id}?amt={amount:.2f}&pa=hyperdrop@icici"
            if not payment:
                payment = Payment(
                    order_id=order_id,
                    amount=amount,
                    link=link,
                    status="pending"
                )
                session.add(payment)
            else:
                payment.link = link
                payment.amount = amount
            session.commit()
            return link

    def verify_payment(self, order_id: int, transaction_ref: Optional[str] = None) -> bool:
        with Session(engine) as session:
            payment = session.exec(select(Payment).where(Payment.order_id == order_id)).first()
            if payment:
                payment.status = "confirmed"
                session.add(payment)
                session.commit()
                return True
            return False

payment_provider: PaymentProvider = MockUPIPaymentProvider()
