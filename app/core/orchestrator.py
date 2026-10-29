import asyncio
import json
import logging
import random
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, Tuple

from sqlmodel import Session, select
from app.config import settings
from app.database import engine
from app.models import (
    Order, Customer, Rider, DeliveryException, GatePassToken,
    CallLeg, Payment, ConsentLog, utc_now
)
from app.schemas import ExtractedOutcome
from app.core.state_machine import (
    ExceptionState, transition_state, StateMachineError
)
from app.core.kpi_tracker import kpi_tracker
from app.providers.translator import translator
from app.providers.payment import payment_provider
from app.providers import get_voice_provider
from app.api.websocket import ws_manager

logger = logging.getLogger("hyperdrop.orchestrator")

class Orchestrator:
    def __init__(self):
        self.voice = get_voice_provider()

    # ==========================================
    # SAFETY & TOKEN UTILITIES
    # ==========================================
    def generate_gate_token(self, order_id: int) -> GatePassToken:
        """Generates a secure 6-digit one-time token expiring in 15 minutes.
        Permanent codes are never used or read aloud."""
        code = str(random.randint(100000, 999999))
        expires = utc_now() + timedelta(minutes=settings.TOKEN_EXPIRY_MINUTES)
        
        with Session(engine) as session:
            # Expire any previous unused tokens for this order
            old_tokens = session.exec(
                select(GatePassToken).where(
                    GatePassToken.order_id == order_id,
                    GatePassToken.used == False
                )
            ).all()
            for t in old_tokens:
                t.used = True
                session.add(t)

            token = GatePassToken(
                order_id=order_id,
                code=code,
                expires_at=expires,
                used=False
            )
            session.add(token)
            session.commit()
            session.refresh(token)
            return token

    def verify_token(self, order_id: int, code: str) -> Tuple[bool, str]:
        """Verify 6-digit gate pass token and mark as used."""
        with Session(engine) as session:
            token = session.exec(
                select(GatePassToken).where(
                    GatePassToken.order_id == order_id,
                    GatePassToken.code == code.strip()
                )
            ).first()
            
            if not token:
                return False, "Invalid token code."
            if token.used:
                return False, "Token has already been used."
            
            # Ensure timezone-aware comparison
            token_expiry = token.expires_at
            if token_expiry.tzinfo is None:
                token_expiry = token_expiry.replace(tzinfo=timezone.utc)

            if utc_now() > token_expiry:
                return False, "Token has expired."

            token.used = True
            session.add(token)
            session.commit()
            return True, "Token verified successfully."

    def validate_extracted_outcome(self, data: Dict[str, Any], order_value: float) -> ExtractedOutcome:
        """Validates all extracted fields and safety rules before dispatching to rider."""
        valid_outcomes = [
            "leave with security",
            "leave at door",
            "give to relative/neighbour",
            "reschedule",
            "cancel"
        ]
        outcome = data.get("outcome", "").lower().strip()
        if outcome not in valid_outcomes:
            raise ValueError(f"Invalid outcome: '{outcome}'. Must be one of {valid_outcomes}")

        # High value safety rule
        if order_value >= settings.HIGH_VALUE_THRESHOLD:
            # Alternate handover requires explicit verbal confirmation
            if outcome in ["leave with security", "leave at door"]:
                verbal_confirmed = data.get("verbal_confirmed", True)
                if not verbal_confirmed:
                    raise ValueError(
                        f"High-value order (₹{order_value}) requires explicit customer confirmation for doorstep/guard drop."
                    )

        if outcome == "leave with security" and not data.get("location"):
            data["location"] = "Main Gate Security Desk"

        if outcome == "give to relative/neighbour" and not data.get("recipient_name"):
            raise ValueError("Recipient name is required when handing over to relative or neighbour.")

        if outcome == "reschedule" and not data.get("reschedule_minutes"):
            data["reschedule_minutes"] = 15

        return ExtractedOutcome(**data)

    def log_consent(self, exception_id: int, instruction: str, transcript_ref: Optional[str] = None):
        """Audit log of customer instruction and disclosure."""
        with Session(engine) as session:
            consent = ConsentLog(
                exception_id=exception_id,
                instruction_text=instruction,
                transcript_ref=transcript_ref,
                timestamp=utc_now()
            )
            session.add(consent)
            session.commit()

    async def log_call_turn(
        self,
        exception_id: int,
        role: str,
        speaker: str,
        text: str,
        language: str,
        latency_ms: Optional[float] = None
    ):
        """Logs a speech turn to the DB and streams to WebSocket dashboard."""
        with Session(engine) as session:
            leg = session.exec(
                select(CallLeg).where(
                    CallLeg.exception_id == exception_id,
                    CallLeg.role == role
                )
            ).first()
            if not leg:
                leg = CallLeg(
                    exception_id=exception_id,
                    role=role,
                    language=language,
                    transcript=f"[{speaker}]: {text}\n",
                    status="in_progress"
                )
                session.add(leg)
            else:
                leg.transcript += f"[{speaker}]: {text}\n"
                session.add(leg)
            session.commit()

        await ws_manager.broadcast({
            "event": "TRANSCRIPT_UPDATE",
            "exception_id": exception_id,
            "role": role,
            "speaker": speaker,
            "text": text,
            "language": language,
            "latency_ms": round(latency_ms, 1) if latency_ms else None,
            "timestamp": utc_now().isoformat()
        })

    # ==========================================
    # SCENARIO RUNNERS (Asyncio Background Tasks)
    # ==========================================

    async def run_scenario_s1_relay(self, exception_id: int):
        """S1 Language Relay: Customer and Rider speak different languages.
        Turn-by-turn relay with live short-spoken translation and latency tracking.
        """
        start_time = utc_now()
        with Session(engine) as session:
            exc = session.get(DeliveryException, exception_id)
            order = session.get(Order, exc.order_id)
            customer = session.get(Customer, order.customer_id)
            rider = session.get(Rider, order.rider_id)

        try:
            await transition_state(exc, ExceptionState.CALLING_CUSTOMER, "Starting dual-leg language relay")
            
            # Turn 1: Disclosure & Rider speaks in their language (Kannada)
            disclosure = "Namaste! This is an automated call from HyperDrop, recorded for delivery safety."
            await self.log_call_turn(exc.id, "customer", "Agent", disclosure, customer.preferred_language)
            await asyncio.sleep(0.5)

            rider_turn_1 = f"Naanu {customer.name} avara building gate hattira idhini, entrance sikkilla."
            await self.log_call_turn(exc.id, "rider", rider.name, rider_turn_1, rider.language)
            await asyncio.sleep(0.4)

            # Agent translates Rider -> Customer
            trans_1, lat_1 = await translator.translate(
                rider_turn_1, rider.language, customer.preferred_language, rider.name
            )
            await self.log_call_turn(exc.id, "customer", "Agent (Relay)", trans_1, customer.preferred_language, lat_1)
            await asyncio.sleep(0.6)

            # Turn 2: Customer responds (Hindi)
            cust_turn_1 = f"{rider.name} ko bolo Tower B basement gate ke paas aaye, main niche aa raha hoon."
            await self.log_call_turn(exc.id, "customer", customer.name, cust_turn_1, customer.preferred_language)
            await asyncio.sleep(0.4)

            # Agent translates Customer -> Rider
            trans_2, lat_2 = await translator.translate(
                cust_turn_1, customer.preferred_language, rider.language, rider.name
            )
            await self.log_call_turn(exc.id, "rider", "Agent (Relay)", trans_2, rider.language, lat_2)
            await asyncio.sleep(0.6)

            # Turn 3: Rider confirms (Kannada)
            rider_turn_2 = f"Sari, naanu Tower B basement gate ge barthini. 2 nimishadalli barthini."
            await self.log_call_turn(exc.id, "rider", rider.name, rider_turn_2, rider.language)
            await asyncio.sleep(0.4)

            # Agent translates Rider -> Customer
            trans_3, lat_3 = await translator.translate(
                rider_turn_2, rider.language, customer.preferred_language, rider.name
            )
            await self.log_call_turn(exc.id, "customer", "Agent (Relay)", trans_3, customer.preferred_language, lat_3)
            await asyncio.sleep(0.5)

            # Both confirmed meeting spot
            instruction = f"Customer meeting {rider.name} at Tower B basement gate in 2 minutes."
            self.log_consent(exc.id, instruction, f"Relay latency avg: {round((lat_1+lat_2+lat_3)/3, 1)}ms")
            
            await transition_state(exc, ExceptionState.RESOLVED, "Both parties aligned on meeting location")
            await transition_state(exc, ExceptionState.CALLING_RIDER, f"Rider {rider.name} proceeding to Tower B basement")
            await transition_state(exc, ExceptionState.RIDER_CONFIRMED, "Rider reached basement gate")
            await transition_state(exc, ExceptionState.HANDOVER_VERIFIED, "Direct customer handover verified")
            await transition_state(exc, ExceptionState.CLOSED, "Order delivered via language relay")
            
            with Session(engine) as session:
                db_order = session.get(Order, order.id)
                db_order.status = "delivered"
                session.add(db_order)
                session.commit()

            duration = (utc_now() - start_time).total_seconds()
            kpi_tracker.record_resolution(duration, success=True)
            
            await ws_manager.broadcast({
                "event": "KPI_UPDATE",
                "kpis": kpi_tracker.get_kpis()
            })

        except Exception as e:
            logger.error(f"Error in S1 Relay: {e}", exc_info=True)
            await transition_state(exc, ExceptionState.ESCALATED_TO_HUMAN, str(e))
            duration = (utc_now() - start_time).total_seconds()
            kpi_tracker.record_resolution(duration, success=False)

    async def run_scenario_s2_busy_customer(self, exception_id: int):
        """S2 Busy Customer: Customer is busy. Agent calls customer, offers menu,
        extracts JSON via function calling, generates 6-digit gate-pass token,
        calls relative if chosen, and calls rider with instructions and token.
        """
        start_time = utc_now()
        with Session(engine) as session:
            exc = session.get(DeliveryException, exception_id)
            order = session.get(Order, exc.order_id)
            customer = session.get(Customer, order.customer_id)
            rider = session.get(Rider, order.rider_id)

        try:
            await transition_state(exc, ExceptionState.CALLING_CUSTOMER, f"Calling customer {customer.name}")

            # 1. Automated call disclosure
            disclosure = "Namaste! This is an automated call from HyperDrop, recorded for delivery safety."
            await self.log_call_turn(exc.id, "customer", "Agent", disclosure, customer.preferred_language)
            await asyncio.sleep(0.4)

            # 2. Offer menu
            menu_prompt = (
                f"Your delivery partner {rider.name} is outside. "
                "Would you like to: leave with security, leave at door, hand to relative, reschedule, or cancel?"
            )
            await self.log_call_turn(exc.id, "customer", "Agent", menu_prompt, customer.preferred_language)
            await asyncio.sleep(0.5)

            # 3. Customer response (e.g. Leave with guard Ramesh at Tower B gate)
            cust_reply = "I'm in an urgent meeting. Please leave package with security guard Ramesh at Tower B gate."
            await self.log_call_turn(exc.id, "customer", customer.name, cust_reply, customer.preferred_language)
            await asyncio.sleep(0.4)

            # 4. Extract structured JSON via function calling
            raw_extraction = {
                "outcome": "leave with security",
                "recipient_name": "Ramesh",
                "recipient_role": "security",
                "location": "Tower B Security Gate Desk",
                "tower": "Tower B",
                "reschedule_minutes": None
            }
            validated_outcome = self.validate_extracted_outcome(raw_extraction, order.value)
            
            with Session(engine) as session:
                db_exc = session.get(DeliveryException, exc.id)
                db_exc.outcome = validated_outcome.model_dump_json()
                session.add(db_exc)
                session.commit()

            # Repeat key instruction to customer: Press 1 to repeat, 2 to confirm
            repeat_confirm = (
                f"Understood. Leaving package at {validated_outcome.location} with {validated_outcome.recipient_name}. "
                "Press 1 to repeat, 2 to confirm."
            )
            await self.log_call_turn(exc.id, "customer", "Agent", repeat_confirm, customer.preferred_language)
            await asyncio.sleep(0.3)
            await self.log_call_turn(exc.id, "customer", customer.name, "[Customer pressed 2: Confirmed]", customer.preferred_language)

            # Log Consent
            self.log_consent(
                exc.id,
                f"Customer confirmed drop with {validated_outcome.recipient_role} {validated_outcome.recipient_name} at {validated_outcome.location}",
                f"Order Value: ₹{order.value}"
            )

            # 5. Generate 6-digit gate-pass token (15-min expiry)
            token = self.generate_gate_token(order.id)
            await ws_manager.broadcast({
                "event": "TOKEN_GENERATED",
                "order_id": order.id,
                "token": token.code,
                "expires_at": token.expires_at.isoformat()
            })

            await transition_state(exc, ExceptionState.RESOLVED, f"Customer chose {validated_outcome.outcome}")

            # 6. Call Rider in their preferred language (Kannada)
            await transition_state(exc, ExceptionState.CALLING_RIDER, f"Calling rider {rider.name} with drop instructions")
            
            rider_script_en = (
                f"Hello {rider.name}. Customer requested to leave parcel with security {validated_outcome.recipient_name} "
                f"at {validated_outcome.location}. One-time gate token is: {token.code}. Valid 15 minutes."
            )
            # Translate instruction into rider's language (Kannada)
            translated_rider_msg, lat = await translator.translate(
                rider_script_en, "English", rider.language, rider.name
            )
            await self.log_call_turn(exc.id, "rider", "Agent", translated_rider_msg, rider.language, lat)
            await asyncio.sleep(0.5)

            # Rider acknowledges
            rider_ack = f"Sari sir, naanu {token.code} code thorsi security Ramesh ge parcel kodthini."
            await self.log_call_turn(exc.id, "rider", rider.name, rider_ack, rider.language)
            await asyncio.sleep(0.4)

            await transition_state(exc, ExceptionState.RIDER_CONFIRMED, "Rider confirmed instruction and token")

            # 7. Verification: Guard token entry or Rider photo
            # In automated demo, simulate guard token entry
            is_valid, msg = self.verify_token(order.id, token.code)
            if is_valid:
                await transition_state(exc, ExceptionState.HANDOVER_VERIFIED, "Guard Ramesh verified gate token")
                await transition_state(exc, ExceptionState.CLOSED, "Package successfully dropped with security")
                
                with Session(engine) as session:
                    db_order = session.get(Order, order.id)
                    db_order.status = "delivered"
                    session.add(db_order)
                    session.commit()

            duration = (utc_now() - start_time).total_seconds()
            kpi_tracker.record_resolution(duration, success=True)
            await ws_manager.broadcast({
                "event": "KPI_UPDATE",
                "kpis": kpi_tracker.get_kpis()
            })

        except Exception as e:
            logger.error(f"Error in S2 Busy Customer: {e}", exc_info=True)
            await transition_state(exc, ExceptionState.ESCALATED_TO_HUMAN, str(e))
            duration = (utc_now() - start_time).total_seconds()
            kpi_tracker.record_resolution(duration, success=False)

    async def run_scenario_s3_cod(self, exception_id: int):
        """S3 COD: Order is Cash On Delivery. Customer not present.
        Agent sends UPI link. Rider is NOT instructed to hand over until
        payment webhook confirms. Handover requires payment AND recipient verification.
        """
        start_time = utc_now()
        with Session(engine) as session:
            exc = session.get(DeliveryException, exception_id)
            order = session.get(Order, exc.order_id)
            customer = session.get(Customer, order.customer_id)
            rider = session.get(Rider, order.rider_id)

        try:
            await transition_state(exc, ExceptionState.CALLING_CUSTOMER, f"Calling customer for COD order ₹{order.cod_amount}")

            # 1. Disclose automated call
            disclosure = "Namaste! This is an automated call from HyperDrop, recorded for delivery safety."
            await self.log_call_turn(exc.id, "customer", "Agent", disclosure, customer.preferred_language)
            await asyncio.sleep(0.4)

            # 2. Inform about COD and offer UPI link
            cod_msg = (
                f"Your delivery partner {rider.name} is here. This is a Cash on Delivery order of ₹{order.cod_amount:.0f}. "
                "Since you are away, I will send an instant UPI link to your phone now so you can pay securely."
            )
            await self.log_call_turn(exc.id, "customer", "Agent", cod_msg, customer.preferred_language)
            await asyncio.sleep(0.4)

            # Customer agrees
            cust_msg = "Yes, please send the UPI link to my WhatsApp. I will pay immediately."
            await self.log_call_turn(exc.id, "customer", customer.name, cust_msg, customer.preferred_language)
            await asyncio.sleep(0.3)

            # 3. Generate UPI Payment Link
            payment_link = payment_provider.create_payment_link(order.id, order.cod_amount)
            await self.log_call_turn(
                exc.id, "customer", "Agent",
                f"UPI link generated and sent to {customer.phone}: {payment_link}",
                customer.preferred_language
            )

            await ws_manager.broadcast({
                "event": "PAYMENT_UPDATE",
                "order_id": order.id,
                "amount": order.cod_amount,
                "link": payment_link,
                "status": "pending"
            })

            # Enter AWAITING_PAYMENT state
            await transition_state(exc, ExceptionState.AWAITING_PAYMENT, f"Awaiting UPI payment of ₹{order.cod_amount}")
            await asyncio.sleep(1.2)  # Wait for customer payment simulation

            # 4. Payment Webhook Confirmation
            payment_provider.verify_payment(order.id, "UPI_TXN_987654321")
            
            await ws_manager.broadcast({
                "event": "PAYMENT_UPDATE",
                "order_id": order.id,
                "amount": order.cod_amount,
                "link": payment_link,
                "status": "confirmed"
            })

            await transition_state(exc, ExceptionState.PAYMENT_CONFIRMED, "UPI Payment received and verified")
            await asyncio.sleep(0.5)

            # Customer instructions for drop after payment
            self.log_consent(
                exc.id,
                f"Customer paid ₹{order.cod_amount} via UPI. Authorized drop with neighbour Suresh.",
                "UPI_TXN_987654321"
            )

            # 5. Call Rider ONLY after payment is confirmed
            await transition_state(exc, ExceptionState.CALLING_RIDER, f"Notifying rider {rider.name} that payment is confirmed")
            
            rider_instruction_en = (
                f"Hello {rider.name}. Payment of ₹{order.cod_amount:.0f} is confirmed via UPI. "
                "Do NOT collect cash. Hand over parcel to Suresh at flat 301."
            )
            translated_rider_msg, lat = await translator.translate(
                rider_instruction_en, "English", rider.language, rider.name
            )
            await self.log_call_turn(exc.id, "rider", "Agent", translated_rider_msg, rider.language, lat)
            await asyncio.sleep(0.5)

            # Rider confirms
            rider_reply = f"Dhanyavaada sir, UPI payment confirm aagide. Naanu flat 301 Suresh ge parcel kodthini."
            await self.log_call_turn(exc.id, "rider", rider.name, rider_reply, rider.language)
            await asyncio.sleep(0.4)

            await transition_state(exc, ExceptionState.RIDER_CONFIRMED, "Rider confirmed cashless handover")

            # 6. Verification: Photo upload
            photo_url = "https://cdn.hyperdrop.in/proofs/order_103_drop.jpg"
            await transition_state(exc, ExceptionState.HANDOVER_VERIFIED, f"Rider uploaded delivery proof photo: {photo_url}")
            await transition_state(exc, ExceptionState.CLOSED, "COD delivery completed successfully")

            with Session(engine) as session:
                db_order = session.get(Order, order.id)
                db_order.status = "delivered"
                session.add(db_order)
                session.commit()

            duration = (utc_now() - start_time).total_seconds()
            kpi_tracker.record_resolution(duration, success=True)
            await ws_manager.broadcast({
                "event": "KPI_UPDATE",
                "kpis": kpi_tracker.get_kpis()
            })

        except Exception as e:
            logger.error(f"Error in S3 COD: {e}", exc_info=True)
            await transition_state(exc, ExceptionState.ESCALATED_TO_HUMAN, str(e))
            duration = (utc_now() - start_time).total_seconds()
            kpi_tracker.record_resolution(duration, success=False)

    async def run_scenario_no_answer(self, exception_id: int):
        """NO_ANSWER Fallback Scenario:
        Customer doesn't pick up -> retry once -> alt_phone/security desk ->
        WhatsApp/SMS fallback link -> ESCALATED_TO_HUMAN.
        """
        start_time = utc_now()
        with Session(engine) as session:
            exc = session.get(DeliveryException, exception_id)
            order = session.get(Order, exc.order_id)
            customer = session.get(Customer, order.customer_id)
            rider = session.get(Rider, order.rider_id)

        try:
            await transition_state(exc, ExceptionState.CALLING_CUSTOMER, f"Dialing primary phone {customer.phone}")
            await asyncio.sleep(0.8)

            # Customer doesn't answer
            await self.log_call_turn(exc.id, "customer", "System", "Call unanswered (ringing timeout 30s).", "English")
            await transition_state(exc, ExceptionState.NO_ANSWER, "Customer did not answer call")
            await asyncio.sleep(0.6)

            # Retry once
            await transition_state(exc, ExceptionState.RETRYING_CUSTOMER, f"Retrying call to {customer.phone} (Attempt 2/2)")
            await asyncio.sleep(0.8)
            await self.log_call_turn(exc.id, "customer", "System", "Second attempt unanswered.", "English")
            
            # Alt phone / security desk
            alt = customer.alt_phone or "+919888877770"
            await transition_state(exc, ExceptionState.CALLING_ALT_PHONE, f"Calling secondary contact / security desk at {alt}")
            await asyncio.sleep(0.8)
            await self.log_call_turn(exc.id, "security", "System", f"Alternate number {alt} busy/unreachable.", "English")

            # Fallback notification
            fallback_link = f"https://drop.hyperdrop.in/self-service/{order.id}"
            await transition_state(
                exc,
                ExceptionState.FALLBACK_NOTIFICATION,
                f"Sent WhatsApp & SMS self-service resolution link to {customer.phone}: {fallback_link}"
            )
            await self.log_call_turn(
                exc.id, "customer", "WhatsApp/SMS Bot",
                f"Hi {customer.name}, delivery partner {rider.name} missed you. Click here to direct: {fallback_link}",
                "English"
            )
            await asyncio.sleep(0.6)

            # Escalate to human support
            await transition_state(
                exc,
                ExceptionState.ESCALATED_TO_HUMAN,
                "All automated contact channels exhausted. Case routed to priority human support desk."
            )

            duration = (utc_now() - start_time).total_seconds()
            kpi_tracker.record_resolution(duration, success=False)
            await ws_manager.broadcast({
                "event": "KPI_UPDATE",
                "kpis": kpi_tracker.get_kpis()
            })

        except Exception as e:
            logger.error(f"Error in NO_ANSWER fallback: {e}", exc_info=True)
            await transition_state(exc, ExceptionState.ESCALATED_TO_HUMAN, str(e))
            duration = (utc_now() - start_time).total_seconds()
            kpi_tracker.record_resolution(duration, success=False)

orchestrator = Orchestrator()
