from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime

class ExceptionCreateRequest(BaseModel):
    order_id: int
    type: str = "customer_unavailable"  # customer_unavailable, cod_pending, language_barrier, gate_access

class ExtractedOutcome(BaseModel):
    outcome: str = Field(..., description="leave with security | leave at door | give to relative/neighbour | reschedule | cancel")
    recipient_name: Optional[str] = None
    recipient_role: Optional[str] = None  # security, neighbour, relative, customer
    location: Optional[str] = None  # e.g. "Main gate security desk", "Door step flat 402"
    tower: Optional[str] = None     # e.g. "Tower B", "Wing 2"
    reschedule_minutes: Optional[int] = None

class HandoverVerifyRequest(BaseModel):
    token_code: Optional[str] = None
    photo_url: Optional[str] = None
    verified_by: str = "rider"  # rider or guard

class VoiceWebhookPayload(BaseModel):
    call_id: Optional[str] = None
    exception_id: int
    role: str = "customer"  # customer, rider, security, relative
    event_type: str = "transcript_turn"  # call_started, transcript_turn, call_completed, extraction
    text: Optional[str] = None
    language: Optional[str] = "English"
    latency_ms: Optional[float] = None
    extraction_data: Optional[Dict[str, Any]] = None

class PaymentWebhookPayload(BaseModel):
    order_id: int
    payment_id: Optional[int] = None
    amount: float
    status: str = "confirmed"  # confirmed, failed
    transaction_ref: Optional[str] = None

class SimulateRequest(BaseModel):
    scenario: str = "S2"  # S1, S2, S3, NO_ANSWER
    order_id: Optional[int] = None

class KPIResponse(BaseModel):
    avg_resolution_seconds: float
    avg_translation_latency_ms: float
    success_rate: float
    cost_per_exception: float
    total_exceptions: int
    resolved_exceptions: int

class CallLegResponse(BaseModel):
    id: int
    role: str
    language: str
    transcript: str
    status: str

class ExceptionDetailResponse(BaseModel):
    id: int
    order_id: int
    type: str
    state: str
    started_at: datetime
    resolved_at: Optional[datetime] = None
    outcome: Optional[str] = None
    legs: List[CallLegResponse] = []
    token: Optional[str] = None
    payment_status: Optional[str] = None
