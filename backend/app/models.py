from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
from .db import Base


class CallLog(Base):
    __tablename__ = "call_logs"

    id = Column(Integer, primary_key=True, index=True)
    call_sid = Column(String(128), index=True, nullable=True)
    from_number = Column(String(64), nullable=True)
    to_number = Column(String(64), nullable=True)
    speech_input = Column(Text, nullable=True)
    ai_response = Column(Text, nullable=True)
    call_status = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class AppointmentRequest(Base):
    __tablename__ = "appointment_requests"

    id = Column(Integer, primary_key=True, index=True)
    caller_name = Column(String(255), nullable=True)
    caller_phone = Column(String(64), nullable=True)
    requested_time = Column(String(255), nullable=True)
    notes = Column(Text, nullable=True)
    confirmed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
