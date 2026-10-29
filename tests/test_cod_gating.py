import pytest
from sqlmodel import Session
from app.models import Customer, Rider, Order, DeliveryException, Payment
from app.core.state_machine import ExceptionState
from tests.conftest import test_engine

def test_cod_order_blocks_handover_without_payment(client):
    with Session(test_engine) as session:
        c = Customer(name="Priya", phone="+919876543210")
        r = Rider(name="Raju", phone="+919900011222")
        session.add_all([c, r])
        session.commit()
        session.refresh(c)
        session.refresh(r)

        # Cash on delivery order
        order = Order(
            item="COD Earphones",
            value=1200.0,
            is_cod=True,
            cod_amount=1200.0,
            address="Tower A",
            customer_id=c.id,
            rider_id=r.id,
            status="out_for_delivery"
        )
        session.add(order)
        session.commit()
        session.refresh(order)

        exc = DeliveryException(
            order_id=order.id,
            type="cod_pending",
            state=ExceptionState.AWAITING_PAYMENT.value
        )
        session.add(exc)
        session.commit()
        session.refresh(exc)

    # Attempt handover verification before payment is confirmed
    res = client.post(
        f"/handover/{exc.id}/verify",
        json={"photo_url": "https://proof.hyperdrop.in/photo1.jpg"}
    )
    assert res.status_code == 400
    assert "Handover not permitted for COD order before payment" in res.json()["detail"]

def test_cod_order_allows_handover_after_payment_confirmed(client):
    with Session(test_engine) as session:
        c = Customer(name="Sneha", phone="+919844455566")
        r = Rider(name="Muthu", phone="+919944433221")
        session.add_all([c, r])
        session.commit()
        session.refresh(c)
        session.refresh(r)

        order = Order(
            item="COD Pro",
            value=800.0,
            is_cod=True,
            cod_amount=800.0,
            address="Tower C",
            customer_id=c.id,
            rider_id=r.id,
            status="out_for_delivery"
        )
        session.add(order)
        session.commit()
        session.refresh(order)

        exc = DeliveryException(
            order_id=order.id,
            type="cod_pending",
            state=ExceptionState.PAYMENT_CONFIRMED.value
        )
        payment = Payment(
            order_id=order.id,
            amount=800.0,
            link="https://pay.hyperdrop.in/upi/800",
            status="confirmed"
        )
        session.add_all([exc, payment])
        session.commit()
        session.refresh(exc)

    # Now verify handover
    res = client.post(
        f"/handover/{exc.id}/verify",
        json={"photo_url": "https://proof.hyperdrop.in/photo2.jpg"}
    )
    assert res.status_code == 200
    assert res.json()["order_status"] == "delivered"
