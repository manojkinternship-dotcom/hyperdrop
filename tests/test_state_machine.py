import pytest
import asyncio
from app.models import DeliveryException
from app.core.state_machine import (
    ExceptionState, transition_state, StateMachineError
)

@pytest.mark.asyncio
async def test_valid_state_transitions():
    exc = DeliveryException(id=1, order_id=1, type="customer_unavailable", state=ExceptionState.CREATED.value)
    
    # CREATED -> CALLING_CUSTOMER
    await transition_state(exc, ExceptionState.CALLING_CUSTOMER)
    assert exc.state == ExceptionState.CALLING_CUSTOMER.value

    # CALLING_CUSTOMER -> RESOLVED
    await transition_state(exc, ExceptionState.RESOLVED)
    assert exc.state == ExceptionState.RESOLVED.value

    # RESOLVED -> CALLING_RIDER
    await transition_state(exc, ExceptionState.CALLING_RIDER)
    assert exc.state == ExceptionState.CALLING_RIDER.value

    # CALLING_RIDER -> RIDER_CONFIRMED
    await transition_state(exc, ExceptionState.RIDER_CONFIRMED)
    assert exc.state == ExceptionState.RIDER_CONFIRMED.value

    # RIDER_CONFIRMED -> HANDOVER_VERIFIED
    await transition_state(exc, ExceptionState.HANDOVER_VERIFIED)
    assert exc.state == ExceptionState.HANDOVER_VERIFIED.value

    # HANDOVER_VERIFIED -> CLOSED
    await transition_state(exc, ExceptionState.CLOSED)
    assert exc.state == ExceptionState.CLOSED.value
    assert exc.resolved_at is not None

@pytest.mark.asyncio
async def test_invalid_state_transition_raises_error():
    exc = DeliveryException(id=2, order_id=1, type="customer_unavailable", state=ExceptionState.CREATED.value)
    
    # Cannot jump directly from CREATED to CLOSED
    with pytest.raises(StateMachineError):
        await transition_state(exc, ExceptionState.CLOSED)

@pytest.mark.asyncio
async def test_no_answer_escalation_path():
    exc = DeliveryException(id=3, order_id=1, type="customer_unavailable", state=ExceptionState.CREATED.value)
    
    await transition_state(exc, ExceptionState.CALLING_CUSTOMER)
    await transition_state(exc, ExceptionState.NO_ANSWER)
    await transition_state(exc, ExceptionState.RETRYING_CUSTOMER)
    await transition_state(exc, ExceptionState.CALLING_ALT_PHONE)
    await transition_state(exc, ExceptionState.FALLBACK_NOTIFICATION)
    await transition_state(exc, ExceptionState.ESCALATED_TO_HUMAN)
    
    assert exc.state == ExceptionState.ESCALATED_TO_HUMAN.value
    assert exc.resolved_at is not None
