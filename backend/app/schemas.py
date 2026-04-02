from datetime import datetime
from pydantic import BaseModel


class CallLogOut(BaseModel):
    id: int
    business_id: int | None = None
    call_sid: str | None = None
    from_number: str | None = None
    to_number: str | None = None
    speech_input: str | None = None
    ai_response: str | None = None
    call_status: str | None = None
    detected_intent: str | None = None
    intent_data: str | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class AppointmentCreate(BaseModel):
    business_id: int | None = None
    caller_name: str | None = None
    caller_phone: str | None = None
    requested_time: str | None = None
    notes: str | None = None


class AppointmentOut(BaseModel):
    id: int
    business_id: int | None = None
    caller_name: str | None = None
    caller_phone: str | None = None
    requested_time: str | None = None
    notes: str | None = None
    confirmed: bool
    calendar_event_id: str | None = None
    calendar_event_link: str | None = None
    scheduled_start: datetime | None = None
    scheduled_end: datetime | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class BusinessCreate(BaseModel):
    name: str
    twilio_number: str
    forwarding_number: str | None = None
    greeting: str | None = None
    business_hours: str | None = None
    booking_enabled: bool = True
    knowledge_text: str | None = None


class BusinessOut(BusinessCreate):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True
