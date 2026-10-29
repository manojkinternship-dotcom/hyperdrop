import pytest
from unittest.mock import patch
from sqlmodel import Session
from app.models import Customer, Rider, Order, DeliveryException
from app.core.state_machine import ExceptionState
from tests.conftest import test_engine

def test_api_endpoints_flow(client):
    # 1. Seed order
    with Session(test_engine) as session:
        c = Customer(name="Rahul", phone="+919800011122")
        r = Rider(name="Kiran", phone="+919800033344")
        session.add_all([c, r])
        session.commit()
        session.refresh(c)
        session.refresh(r)

        order = Order(
            item="Fitness Band",
            value=1500.0,
            is_cod=False,
            address="Koramangala 4th Block",
            customer_id=c.id,
            rider_id=r.id,
            status="out_for_delivery"
        )
        session.add(order)
        session.commit()
        session.refresh(order)
        order_id = order.id

    # 2. POST /exceptions
    res = client.post("/exceptions", json={"order_id": order_id, "type": "customer_unavailable"})
    assert res.status_code == 201
    exc_data = res.json()
    exc_id = exc_data["id"]
    assert exc_data["state"] == "CREATED"

    # 3. GET /exceptions/{id}
    res = client.get(f"/exceptions/{exc_id}")
    assert res.status_code == 200
    assert res.json()["id"] == exc_id

    # 4. GET /kpis
    res = client.get("/kpis")
    assert res.status_code == 200
    kpis = res.json()
    assert "avg_resolution_seconds" in kpis
    assert "cost_per_exception" in kpis

    # 5. POST /demo/simulate/S1 and S2 with instant sleep
    with patch("asyncio.sleep", return_value=None):
        res = client.post("/demo/simulate/S1")
        assert res.status_code == 200
        assert res.json()["status"] == "simulation_started"

        res = client.post("/demo/simulate/S2")
        assert res.status_code == 200
        assert res.json()["status"] == "simulation_started"
