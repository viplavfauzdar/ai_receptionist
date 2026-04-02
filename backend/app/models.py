from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from .db import Base


class Business(Base):
    __tablename__ = "businesses"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    twilio_number = Column(String(64), index=True, nullable=False)
    twilio_number_normalized = Column(String(32), index=True, nullable=True)
    forwarding_number = Column(String(64), nullable=True)
    greeting = Column(Text, nullable=True)
    business_hours = Column(String(255), nullable=True)
    booking_enabled = Column(Boolean, default=True)
    knowledge_text = Column(Text, nullable=True)
    google_calendar_connected = Column(Boolean, default=False)
    google_account_email = Column(String(255), nullable=True)
    google_calendar_id = Column(String(255), nullable=True)
    google_token_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class CallLog(Base):
    __tablename__ = "call_logs"

    id = Column(Integer, primary_key=True, index=True)
    business_id = Column(Integer, ForeignKey("businesses.id"), nullable=True)
    call_sid = Column(String(128), index=True, nullable=True)
    from_number = Column(String(64), nullable=True)
    to_number = Column(String(64), nullable=True)
    speech_input = Column(Text, nullable=True)
    ai_response = Column(Text, nullable=True)
    call_status = Column(String(64), nullable=True)
    detected_intent = Column(String(64), nullable=True)
    intent_data = Column(Text, nullable=True)
    protection_reason = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class CallSession(Base):
    __tablename__ = "call_sessions"

    id = Column(Integer, primary_key=True, index=True)
    call_sid = Column(String(128), index=True, nullable=False)
    from_number = Column(String(64), nullable=True)
    to_number = Column(String(64), nullable=True)
    current_intent = Column(String(64), nullable=True)
    current_state = Column(String(64), nullable=True)
    slot_data_json = Column(Text, nullable=True)
    transcript_json = Column(Text, nullable=True)
    turn_count = Column(Integer, default=0)
    llm_call_count = Column(Integer, default=0)
    last_protection_reason = Column(String(64), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AppointmentRequest(Base):
    __tablename__ = "appointment_requests"

    id = Column(Integer, primary_key=True, index=True)
    business_id = Column(Integer, ForeignKey("businesses.id"), nullable=True)
    caller_name = Column(String(255), nullable=True)
    caller_phone = Column(String(64), nullable=True)
    requested_time = Column(String(255), nullable=True)
    notes = Column(Text, nullable=True)
    confirmed = Column(Boolean, default=False)
    calendar_event_id = Column(String(255), nullable=True)
    calendar_event_link = Column(Text, nullable=True)
    scheduled_start = Column(DateTime, nullable=True)
    scheduled_end = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
