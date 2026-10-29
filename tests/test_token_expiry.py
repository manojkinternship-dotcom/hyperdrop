import pytest
from datetime import timedelta, timezone
from sqlmodel import Session
from app.models import GatePassToken, utc_now
from app.core.orchestrator import orchestrator
from tests.conftest import test_engine

def test_generate_and_verify_valid_token():
    token = orchestrator.generate_gate_token(order_id=101)
    
    assert len(token.code) == 6
    assert token.code.isdigit()
    assert token.used is False
    
    # Verify with correct code
    success, msg = orchestrator.verify_token(order_id=101, code=token.code)
    assert success is True
    assert "successfully" in msg

    # Re-verify should fail (single-use token)
    second_try, fail_msg = orchestrator.verify_token(order_id=101, code=token.code)
    assert second_try is False
    assert "already been used" in fail_msg

def test_token_expiry():
    with Session(test_engine) as session:
        # Create an expired token (expired 5 minutes ago)
        expired_token = GatePassToken(
            order_id=102,
            code="123456",
            expires_at=utc_now() - timedelta(minutes=5),
            used=False
        )
        session.add(expired_token)
        session.commit()

    success, msg = orchestrator.verify_token(order_id=102, code="123456")
    assert success is False
    assert "expired" in msg

def test_invalid_token_code():
    orchestrator.generate_gate_token(order_id=103)
    success, msg = orchestrator.verify_token(order_id=103, code="000000")
    assert success is False
    assert "Invalid token" in msg
