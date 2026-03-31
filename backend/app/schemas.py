from datetime import datetime
from pydantic import BaseModel


class CallLogOut(BaseModel):
    id: int
    call_sid: str | None = None
    from_number: str | None = None
    to_number: str | None = None
    speech_input: str | None = None
    ai_response: str | None = None
    call_status: str | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class AppointmentCreate(BaseModel):
    caller_name: str | None = None
    caller_phone: str | None = None
    requested_time: str | None = None
    notes: str | None = None


class AppointmentOut(BaseModel):
    id: int
    caller_name: str | None = None
    caller_phone: str | None = None
    requested_time: str | None = None
    notes: str | None = None
    confirmed: bool
    created_at: datetime

    class Config:
        from_attributes = True
