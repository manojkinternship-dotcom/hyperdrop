from enum import Enum
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
import logging
from app.models import DeliveryException
from app.api.websocket import ws_manager

logger = logging.getLogger("hyperdrop.state_machine")

class ExceptionState(str, Enum):
    CREATED = "CREATED"
    CALLING_CUSTOMER = "CALLING_CUSTOMER"
    RESOLVED = "RESOLVED"
    NO_ANSWER = "NO_ANSWER"
    RETRYING_CUSTOMER = "RETRYING_CUSTOMER"
    CALLING_ALT_PHONE = "CALLING_ALT_PHONE"
    FALLBACK_NOTIFICATION = "FALLBACK_NOTIFICATION"
    ESCALATED_TO_HUMAN = "ESCALATED_TO_HUMAN"
    AWAITING_PAYMENT = "AWAITING_PAYMENT"
    PAYMENT_CONFIRMED = "PAYMENT_CONFIRMED"
    CALLING_RIDER = "CALLING_RIDER"
    RIDER_CONFIRMED = "RIDER_CONFIRMED"
    HANDOVER_VERIFIED = "HANDOVER_VERIFIED"
    CLOSED = "CLOSED"

# Valid state transitions
VALID_TRANSITIONS: Dict[ExceptionState, List[ExceptionState]] = {
    ExceptionState.CREATED: [ExceptionState.CALLING_CUSTOMER],
    ExceptionState.CALLING_CUSTOMER: [
        ExceptionState.RESOLVED,
        ExceptionState.NO_ANSWER,
        ExceptionState.AWAITING_PAYMENT,
        ExceptionState.CALLING_RIDER,
    ],
    ExceptionState.NO_ANSWER: [
        ExceptionState.RETRYING_CUSTOMER,
        ExceptionState.CALLING_ALT_PHONE,
        ExceptionState.FALLBACK_NOTIFICATION,
        ExceptionState.ESCALATED_TO_HUMAN
    ],
    ExceptionState.RETRYING_CUSTOMER: [
        ExceptionState.RESOLVED,
        ExceptionState.CALLING_ALT_PHONE,
        ExceptionState.FALLBACK_NOTIFICATION,
        ExceptionState.ESCALATED_TO_HUMAN
    ],
    ExceptionState.CALLING_ALT_PHONE: [
        ExceptionState.RESOLVED,
        ExceptionState.FALLBACK_NOTIFICATION,
        ExceptionState.ESCALATED_TO_HUMAN
    ],
    ExceptionState.FALLBACK_NOTIFICATION: [
        ExceptionState.ESCALATED_TO_HUMAN,
        ExceptionState.RESOLVED
    ],
    ExceptionState.RESOLVED: [
        ExceptionState.AWAITING_PAYMENT,
        ExceptionState.CALLING_RIDER,
        ExceptionState.CLOSED
    ],
    ExceptionState.AWAITING_PAYMENT: [
        ExceptionState.PAYMENT_CONFIRMED,
        ExceptionState.ESCALATED_TO_HUMAN
    ],
    ExceptionState.PAYMENT_CONFIRMED: [
        ExceptionState.CALLING_RIDER,
        ExceptionState.RIDER_CONFIRMED,
        ExceptionState.HANDOVER_VERIFIED
    ],
    ExceptionState.CALLING_RIDER: [
        ExceptionState.RIDER_CONFIRMED,
        ExceptionState.HANDOVER_VERIFIED,
        ExceptionState.ESCALATED_TO_HUMAN
    ],
    ExceptionState.RIDER_CONFIRMED: [
        ExceptionState.HANDOVER_VERIFIED,
        ExceptionState.CLOSED
    ],
    ExceptionState.HANDOVER_VERIFIED: [
        ExceptionState.CLOSED
    ],
    ExceptionState.CLOSED: [],
    ExceptionState.ESCALATED_TO_HUMAN: []
}

class StateMachineError(Exception):
    pass

async def transition_state(
    exception: DeliveryException,
    new_state: ExceptionState,
    details: Optional[str] = None
) -> DeliveryException:
    current = ExceptionState(exception.state)
    
    # Allow idempotency if already in the same state
    if current == new_state:
        return exception

    allowed = VALID_TRANSITIONS.get(current, [])
    if new_state not in allowed:
        error_msg = f"Invalid state transition: Cannot transition from {current} to {new_state}"
        logger.error(error_msg)
        raise StateMachineError(error_msg)

    old_state = exception.state
    exception.state = new_state.value
    now = datetime.now(timezone.utc)
    
    if new_state in [ExceptionState.CLOSED, ExceptionState.ESCALATED_TO_HUMAN]:
        exception.resolved_at = now

    logger.info(f"[State Machine] Exception {exception.id}: {old_state} -> {new_state.value} ({details or 'No details'})")
    
    # Push live event over WebSocket
    await ws_manager.broadcast({
        "event": "STATE_CHANGE",
        "exception_id": exception.id,
        "order_id": exception.order_id,
        "old_state": old_state,
        "new_state": new_state.value,
        "timestamp": now.isoformat(),
        "details": details
    })
    
    return exception
