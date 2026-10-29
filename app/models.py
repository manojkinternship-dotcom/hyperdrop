from datetime import datetime, timezone
from typing import Optional
from sqlmodel import SQLModel, Field

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class Customer(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    phone: str
    alt_phone: Optional[str] = None
    preferred_language: str = "Hindi"  # English, Hindi, Hinglish, Kannada, Tamil, Telugu
    saved_preferences: Optional[str] = None

class Rider(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    phone: str
    language: str = "Kannada"

class Order(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    item: str
    value: float
    is_cod: bool = False
    cod_amount: float = 0.0
    address: str
    customer_id: int = Field(foreign_key="customer.id")
    rider_id: int = Field(foreign_key="rider.id")
    status: str = "out_for_delivery"  # pending, out_for_delivery, delivered, cancelled, exception

class DeliveryException(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    order_id: int = Field(foreign_key="order.id")
    type: str  # customer_unavailable, cod_pending, language_barrier, gate_access
    state: str = "CREATED"
    started_at: datetime = Field(default_factory=utc_now)
    resolved_at: Optional[datetime] = None
    outcome: Optional[str] = None  # JSON string with structured outcome details

class GatePassToken(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    order_id: int = Field(foreign_key="order.id")
    code: str  # 6-digit numeric token
    expires_at: datetime
    used: bool = False

class CallLeg(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    exception_id: int = Field(foreign_key="deliveryexception.id")
    role: str  # customer, rider, security, relative
    language: str
    transcript: str = ""
    recording_url: Optional[str] = None
    status: str = "in_progress"  # in_progress, completed, failed

class Payment(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    order_id: int = Field(foreign_key="order.id")
    amount: float
    link: str
    status: str = "pending"  # pending, completed, failed

class ConsentLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    exception_id: int = Field(foreign_key="deliveryexception.id")
    instruction_text: str
    transcript_ref: Optional[str] = None
    timestamp: datetime = Field(default_factory=utc_now)
