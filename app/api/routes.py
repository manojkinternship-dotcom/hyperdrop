import asyncio
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from sqlmodel import Session, select

from app.database import get_session, engine
from app.models import (
    Order, Customer, Rider, DeliveryException, CallLeg,
    GatePassToken, Payment, utc_now
)
from app.schemas import (
    ExceptionCreateRequest, ExtractedOutcome, HandoverVerifyRequest,
    VoiceWebhookPayload, PaymentWebhookPayload, SimulateRequest,
    KPIResponse, ExceptionDetailResponse, CallLegResponse
)
from app.core.rate_limiter import rate_limiter
from app.core.kpi_tracker import kpi_tracker
from app.core.state_machine import ExceptionState, transition_state
from app.core.orchestrator import orchestrator
from app.providers.payment import payment_provider
from app.api.websocket import ws_manager

router = APIRouter()

@router.post("/exceptions", status_code=201)
async def create_exception(req: ExceptionCreateRequest, session: Session = Depends(get_session)):
    """Trigger a new delivery exception for an order."""
    if not rate_limiter.allow_request():
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded: Too many exception creation requests. Please retry in a few moments."
        )

    order = session.get(Order, req.order_id)
    if not order:
        raise HTTPException(status_code=404, detail=f"Order {req.order_id} not found.")

    exception = DeliveryException(
        order_id=req.order_id,
        type=req.type,
        state=ExceptionState.CREATED.value,
        started_at=utc_now()
    )
    session.add(exception)
    session.commit()
    session.refresh(exception)

    kpi_tracker.record_exception_created()

    # Broadcast event
    await ws_manager.broadcast({
        "event": "EXCEPTION_CREATED",
        "exception_id": exception.id,
        "order_id": exception.order_id,
        "type": exception.type,
        "timestamp": exception.started_at.isoformat()
    })

    return exception

@router.get("/exceptions/{exception_id}")
async def get_exception(exception_id: int, session: Session = Depends(get_session)):
    """Get state, legs, transcripts, token and payment details for an exception."""
    exc = session.get(DeliveryException, exception_id)
    if not exc:
        raise HTTPException(status_code=404, detail="Exception not found")

    legs = session.exec(select(CallLeg).where(CallLeg.exception_id == exception_id)).all()
    token = session.exec(
        select(GatePassToken).where(
            GatePassToken.order_id == exc.order_id,
            GatePassToken.used == False
        )
    ).first()
    payment = session.exec(select(Payment).where(Payment.order_id == exc.order_id)).first()

    leg_responses = [
        CallLegResponse(
            id=leg.id,
            role=leg.role,
            language=leg.language,
            transcript=leg.transcript,
            status=leg.status
        )
        for leg in legs
    ]

    return ExceptionDetailResponse(
        id=exc.id,
        order_id=exc.order_id,
        type=exc.type,
        state=exc.state,
        started_at=exc.started_at,
        resolved_at=exc.resolved_at,
        outcome=exc.outcome,
        legs=leg_responses,
        token=token.code if token else None,
        payment_status=payment.status if payment else None
    )

@router.post("/webhooks/voice")
async def voice_webhook(payload: VoiceWebhookPayload, session: Session = Depends(get_session)):
    """Handle incoming voice events, real-time transcription and function extraction results."""
    exc = session.get(DeliveryException, payload.exception_id)
    if not exc:
        raise HTTPException(status_code=404, detail="Exception not found")

    if payload.event_type == "transcript_turn" and payload.text:
        await orchestrator.log_call_turn(
            exc.id,
            payload.role,
            payload.role.capitalize(),
            payload.text,
            payload.language or "English",
            payload.latency_ms
        )
    elif payload.event_type == "extraction" and payload.extraction_data:
        order = session.get(Order, exc.order_id)
        validated = orchestrator.validate_extracted_outcome(payload.extraction_data, order.value if order else 0.0)
        exc.outcome = validated.model_dump_json()
        session.add(exc)
        session.commit()
        await transition_state(exc, ExceptionState.RESOLVED, f"Extracted outcome: {validated.outcome}")

    return {"status": "success", "event": payload.event_type}

@router.post("/webhooks/payment")
async def payment_webhook(payload: PaymentWebhookPayload, session: Session = Depends(get_session)):
    """Handle payment gateway webhook. Rider is notified ONLY after confirmation."""
    verified = payment_provider.verify_payment(payload.order_id, payload.transaction_ref)
    if not verified:
        raise HTTPException(status_code=400, detail="Unable to verify payment for order")

    # Find open exception for this order
    exc = session.exec(
        select(DeliveryException).where(
            DeliveryException.order_id == payload.order_id,
            DeliveryException.state == ExceptionState.AWAITING_PAYMENT.value
        )
    ).first()

    if exc:
        await transition_state(exc, ExceptionState.PAYMENT_CONFIRMED, "Payment webhook received and confirmed")

    await ws_manager.broadcast({
        "event": "PAYMENT_CONFIRMED",
        "order_id": payload.order_id,
        "amount": payload.amount,
        "status": "confirmed"
    })

    return {"status": "success", "order_id": payload.order_id, "payment_status": "confirmed"}

@router.post("/handover/{exception_id}/verify")
async def verify_handover(
    exception_id: int,
    req: HandoverVerifyRequest,
    session: Session = Depends(get_session)
):
    """Enforce safety rules: Handover requires rider photo upload or guard token entry."""
    exc = session.get(DeliveryException, exception_id)
    if not exc:
        raise HTTPException(status_code=404, detail="Exception not found")

    order = session.get(Order, exc.order_id)
    verified = False
    method = ""

    if req.token_code:
        is_valid, msg = orchestrator.verify_token(order.id, req.token_code)
        if not is_valid:
            raise HTTPException(status_code=400, detail=f"Token verification failed: {msg}")
        verified = True
        method = f"One-time gate token verified ({req.token_code})"
    elif req.photo_url:
        verified = True
        method = f"Rider photo proof verified ({req.photo_url})"
    else:
        raise HTTPException(
            status_code=400,
            detail="Verification requires either a 6-digit gate token code or a photo proof URL."
        )

    # Check if COD order requires payment confirmation
    if order.is_cod:
        payment = session.exec(select(Payment).where(Payment.order_id == order.id)).first()
        if not payment or payment.status != "confirmed":
            raise HTTPException(
                status_code=400,
                detail="Safety Violation: Handover not permitted for COD order before payment confirmation."
            )

    await transition_state(exc, ExceptionState.HANDOVER_VERIFIED, method)
    await transition_state(exc, ExceptionState.CLOSED, "Delivery completed and verified")

    order.status = "delivered"
    session.add(order)
    session.commit()

    return {"status": "success", "verification_method": method, "order_status": "delivered"}

@router.get("/kpis", response_model=KPIResponse)
async def get_kpis():
    """Returns live KPI statistics."""
    return kpi_tracker.get_kpis()

@router.post("/demo/simulate/{scenario}")
async def simulate_scenario(scenario: str, session: Session = Depends(get_session)):
    """Trigger end-to-end simulation of S1, S2, S3 or NO_ANSWER in mock mode."""
    scenario_upper = scenario.upper().strip()
    valid_scenarios = ["S1", "S2", "S3", "NO_ANSWER"]
    if scenario_upper not in valid_scenarios:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid scenario '{scenario}'. Must be one of {valid_scenarios}"
        )

    # Select or seed a suitable order
    if scenario_upper == "S3":
        # Needs COD order
        order = session.exec(select(Order).where(Order.is_cod == True)).first()
    else:
        order = session.exec(select(Order).where(Order.is_cod == False)).first()

    if not order:
        # Fallback to any order
        order = session.exec(select(Order)).first()

    if not order:
        raise HTTPException(status_code=400, detail="No orders found. Please run seed script first.")

    # Create exception
    exc = DeliveryException(
        order_id=order.id,
        type="customer_unavailable" if scenario_upper != "S1" else "language_barrier",
        state=ExceptionState.CREATED.value,
        started_at=utc_now()
    )
    session.add(exc)
    session.commit()
    session.refresh(exc)
    kpi_tracker.record_exception_created()

    # Launch background task
    if scenario_upper == "S1":
        asyncio.create_task(orchestrator.run_scenario_s1_relay(exc.id))
    elif scenario_upper == "S2":
        asyncio.create_task(orchestrator.run_scenario_s2_busy_customer(exc.id))
    elif scenario_upper == "S3":
        asyncio.create_task(orchestrator.run_scenario_s3_cod(exc.id))
    elif scenario_upper == "NO_ANSWER":
        asyncio.create_task(orchestrator.run_scenario_no_answer(exc.id))

    return {
        "status": "simulation_started",
        "scenario": scenario_upper,
        "exception_id": exc.id,
        "order_id": order.id,
        "item": order.item,
        "is_cod": order.is_cod,
        "cod_amount": order.cod_amount
    }
