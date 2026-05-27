from __future__ import annotations

import json
from typing import Any

from ..calendar_service import (
    CalendarServiceError,
    build_appointment_window,
    check_calendar_availability,
    create_calendar_booking,
)
from ..config import settings
from ..db import SessionLocal
from ..models import AppointmentRequest, Business, CallLog, CallSession
from .session import RealtimeBridgeSession


REALTIME_TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": "lookup_business",
        "description": "Look up business settings for the called Twilio number.",
        "parameters": {
            "type": "object",
            "properties": {"to_number": {"type": "string"}},
            "required": ["to_number"],
        },
    },
    {
        "type": "function",
        "name": "check_availability",
        "description": "Check whether a requested appointment slot is available.",
        "parameters": {
            "type": "object",
            "properties": {
                "appointment_day": {"type": "string"},
                "appointment_time": {"type": "string"},
            },
            "required": ["appointment_day", "appointment_time"],
        },
    },
    {
        "type": "function",
        "name": "book_appointment",
        "description": "Book an appointment after collecting the appointment day, time, caller name, and callback number.",
        "parameters": {
            "type": "object",
            "properties": {
                "caller_name": {"type": "string"},
                "callback_number": {"type": "string"},
                "appointment_day": {"type": "string"},
                "appointment_time": {"type": "string"},
                "notes": {"type": "string"},
            },
            "required": ["caller_name", "callback_number", "appointment_day", "appointment_time"],
        },
    },
    {
        "type": "function",
        "name": "create_booking",
        "description": "Legacy alias for book_appointment. Prefer book_appointment for new calls.",
        "parameters": {
            "type": "object",
            "properties": {
                "caller_name": {"type": "string"},
                "callback_number": {"type": "string"},
                "appointment_day": {"type": "string"},
                "appointment_time": {"type": "string"},
                "notes": {"type": "string"},
            },
            "required": ["caller_name", "callback_number", "appointment_day", "appointment_time"],
        },
    },
    {
        "type": "function",
        "name": "capture_callback",
        "description": "Capture a callback request when the caller does not book.",
        "parameters": {
            "type": "object",
            "properties": {
                "caller_name": {"type": "string"},
                "callback_number": {"type": "string"},
                "reason": {"type": "string"},
            },
            "required": ["callback_number"],
        },
    },
    {
        "type": "function",
        "name": "log_call_summary",
        "description": "Persist a short call summary after the realtime session ends.",
        "parameters": {
            "type": "object",
            "properties": {"summary": {"type": "string"}},
            "required": ["summary"],
        },
    },
]


def _log_realtime_tool(message: str) -> None:
    print(f"[openai-realtime] {message}", flush=True)


def _normalize_phone_number(value: str | None) -> str:
    if not value:
        return ""
    digits = "".join(char for char in value.strip() if char.isdigit())
    if len(digits) == 11 and digits.startswith("1"):
        return digits[1:]
    return digits


def _resolve_business(db, to_number: str | None) -> Business | None:
    if not to_number:
        return db.query(Business).order_by(Business.id.asc()).first()

    business = db.query(Business).filter(Business.twilio_number == to_number).first()
    if business is not None:
        return business

    normalized = _normalize_phone_number(to_number)
    if not normalized:
        return None
    return (
        db.query(Business)
        .filter(Business.twilio_number_normalized == normalized)
        .order_by(Business.id.asc())
        .first()
    )


def _requested_time(arguments: dict[str, Any]) -> str:
    return " ".join(
        part
        for part in (
            str(arguments.get("appointment_day") or "").strip(),
            str(arguments.get("appointment_time") or "").strip(),
        )
        if part
    )


def _safe_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True)


def _appointment_notes(session: RealtimeBridgeSession, arguments: dict[str, Any]) -> str:
    return _safe_json(
        {
            "source": "openai_realtime",
            "call_sid": session.call_sid,
            "stream_sid": session.stream_sid,
            "notes": str(arguments.get("notes") or "Realtime voice booking").strip(),
        }
    )


def _notes_match_call_sid(notes: str | None, call_sid: str | None) -> bool:
    if not call_sid or not notes:
        return False
    try:
        parsed = json.loads(notes)
    except (TypeError, ValueError):
        return f"call_sid={call_sid}" in str(notes)
    return isinstance(parsed, dict) and parsed.get("call_sid") == call_sid


def _find_existing_appointment(
    db,
    *,
    call_sid: str | None,
    caller_phone: str | None,
    requested_time: str | None,
) -> AppointmentRequest | None:
    if not call_sid or not caller_phone or not requested_time:
        return None
    candidates = (
        db.query(AppointmentRequest)
        .filter(
            AppointmentRequest.caller_phone == caller_phone,
            AppointmentRequest.requested_time == requested_time,
        )
        .order_by(AppointmentRequest.id.asc())
        .all()
    )
    for appointment in candidates:
        if _notes_match_call_sid(appointment.notes, call_sid):
            return appointment
    return None


def _appointment_result(
    appointment: AppointmentRequest,
    *,
    calendar_status: str,
    duplicate: bool = False,
) -> dict[str, Any]:
    return {
        "status": "ok",
        "appointment_request_id": appointment.id,
        "business_id": appointment.business_id,
        "calendar_status": calendar_status,
        "calendar_event_id": appointment.calendar_event_id,
        "calendar_event_link": appointment.calendar_event_link,
        "confirmed": bool(appointment.confirmed),
        "duplicate": duplicate,
        "message": (
            "Existing appointment request reused."
            if duplicate
            else (
                "Appointment booked on the calendar."
                if appointment.confirmed
                else "Appointment request saved; the office will confirm it."
            )
        ),
    }


def _append_transcript(transcript_json: str | None, role: str, text: str) -> str:
    try:
        transcript = json.loads(transcript_json or "[]")
    except (TypeError, ValueError):
        transcript = []
    if not isinstance(transcript, list):
        transcript = []
    transcript.append({"role": role, "text": text})
    return json.dumps(transcript[-20:])


def persist_realtime_call_log(
    session: RealtimeBridgeSession,
    *,
    event_name: str,
    business_id: int | None = None,
    speech_input: str | None = None,
    ai_response: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    db = SessionLocal()
    try:
        if business_id is None:
            business = _resolve_business(db, session.to_number)
            business_id = business.id if business is not None else None
        db.add(
            CallLog(
                business_id=business_id,
                call_sid=session.call_sid,
                from_number=session.from_number,
                to_number=session.to_number,
                speech_input=speech_input,
                ai_response=ai_response,
                call_status=event_name,
                detected_intent="OPENAI_REALTIME",
                intent_data=_safe_json(
                    {
                        "event": event_name,
                        "stream_sid": session.stream_sid,
                        **(payload or {}),
                    }
                ),
            )
        )
        db.commit()
    except Exception as exc:
        _log_realtime_tool(f"event=realtime_call_log_failed reason=unexpected_error error={exc}")
    finally:
        db.close()


def persist_realtime_call_start(session: RealtimeBridgeSession) -> None:
    db = SessionLocal()
    try:
        business = _resolve_business(db, session.to_number)
        business_id = business.id if business is not None else None
        call_sid = session.call_sid or session.stream_sid
        row = db.query(CallSession).filter(CallSession.call_sid == call_sid).first()
        slot_data = {
            "source": "openai_realtime",
            "stream_sid": session.stream_sid,
            "business_id": business_id,
        }
        if row is None:
            row = CallSession(
                call_sid=call_sid,
                from_number=session.from_number,
                to_number=session.to_number,
                current_intent="OPENAI_REALTIME",
                current_state="STARTED",
                slot_data_json=_safe_json(slot_data),
                transcript_json="[]",
                is_active=True,
            )
            db.add(row)
        else:
            row.from_number = session.from_number
            row.to_number = session.to_number
            row.current_intent = "OPENAI_REALTIME"
            row.current_state = "STARTED"
            row.slot_data_json = _safe_json(slot_data)
            row.is_active = True
        db.add(
            CallLog(
                business_id=business_id,
                call_sid=session.call_sid,
                from_number=session.from_number,
                to_number=session.to_number,
                call_status="realtime_call_started",
                detected_intent="OPENAI_REALTIME",
                intent_data=_safe_json({"event": "call_started", "stream_sid": session.stream_sid}),
            )
        )
        db.commit()
    except Exception as exc:
        _log_realtime_tool(f"event=realtime_call_start_persist_failed reason=unexpected_error error={exc}")
    finally:
        db.close()


def persist_realtime_transcript(session: RealtimeBridgeSession, *, role: str, text: str) -> None:
    if not text:
        return
    db = SessionLocal()
    try:
        call_sid = session.call_sid or session.stream_sid
        row = db.query(CallSession).filter(CallSession.call_sid == call_sid).first()
        if row is not None:
            row.transcript_json = _append_transcript(row.transcript_json, role, text)
            row.current_state = "IN_PROGRESS"
        business = _resolve_business(db, session.to_number)
        db.add(
            CallLog(
                business_id=business.id if business is not None else None,
                call_sid=session.call_sid,
                from_number=session.from_number,
                to_number=session.to_number,
                speech_input=text if role == "user" else None,
                ai_response=text if role == "assistant" else None,
                call_status=f"realtime_{role}_transcript",
                detected_intent="OPENAI_REALTIME",
                intent_data=_safe_json({"event": f"{role}_transcript", "stream_sid": session.stream_sid}),
            )
        )
        db.commit()
    except Exception as exc:
        _log_realtime_tool(f"event=realtime_transcript_persist_failed reason=unexpected_error error={exc}")
    finally:
        db.close()


def persist_realtime_call_end(session: RealtimeBridgeSession) -> None:
    if session.call_end_logged:
        return
    if not session.call_sid and session.stream_sid == "pending-realtime":
        return
    session.call_end_logged = True
    db = SessionLocal()
    try:
        call_sid = session.call_sid or session.stream_sid
        row = db.query(CallSession).filter(CallSession.call_sid == call_sid).first()
        if row is not None:
            row.current_state = "ENDED"
            row.is_active = False
        business = _resolve_business(db, session.to_number)
        db.add(
            CallLog(
                business_id=business.id if business is not None else None,
                call_sid=session.call_sid,
                from_number=session.from_number,
                to_number=session.to_number,
                call_status="realtime_call_ended",
                detected_intent="OPENAI_REALTIME",
                intent_data=_safe_json(
                    {
                        "event": "call_ended",
                        "stream_sid": session.stream_sid,
                        "twilio_media_chunks": session.twilio_media_chunks,
                        "openai_audio_deltas": session.openai_audio_deltas,
                    }
                ),
            )
        )
        db.commit()
    except Exception as exc:
        _log_realtime_tool(f"event=realtime_call_end_persist_failed reason=unexpected_error error={exc}")
    finally:
        db.close()


async def lookup_business(session: RealtimeBridgeSession, arguments: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "stub",
        "to_number": arguments.get("to_number") or session.to_number,
        "message": "Business lookup is wired as a Realtime tool boundary.",
    }


async def check_availability(session: RealtimeBridgeSession, arguments: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "stub",
        "available": None,
        "message": "Calendar availability will call existing backend logic in a later patch.",
    }


async def book_appointment(session: RealtimeBridgeSession, arguments: dict[str, Any]) -> dict[str, Any]:
    _log_realtime_tool(
        "event=appointment_create_attempt "
        f"stream_sid={session.stream_sid} call_sid={session.call_sid} "
        f"appointment_day={arguments.get('appointment_day')} appointment_time={arguments.get('appointment_time')}"
    )
    required_fields = ("appointment_day", "appointment_time", "caller_name", "callback_number")
    missing_fields = [field for field in required_fields if not str(arguments.get(field) or "").strip()]
    if missing_fields:
        return {
            "status": "missing_fields",
            "missing_fields": missing_fields,
            "message": "Please collect the missing booking details before booking.",
        }
    persist_realtime_call_log(
        session,
        event_name="realtime_appointment_create_attempted",
        payload={
            "appointment_day": str(arguments.get("appointment_day") or ""),
            "appointment_time": str(arguments.get("appointment_time") or ""),
        },
    )

    db = SessionLocal()
    try:
        business = _resolve_business(db, session.to_number)
        business_token_json = (
            business.google_token_json
            if business is not None and business.google_calendar_connected and business.google_token_json
            else None
        )
        business_calendar_id = (
            business.google_calendar_id
            if business is not None and business.google_calendar_connected and business.google_calendar_id
            else None
        )
        appointment = AppointmentRequest(
            business_id=business.id if business is not None else None,
            caller_name=str(arguments.get("caller_name") or "").strip(),
            caller_phone=str(arguments.get("callback_number") or "").strip() or session.from_number,
            requested_time=_requested_time(arguments),
            notes=_appointment_notes(session, arguments),
        )
        existing_appointment = _find_existing_appointment(
            db,
            call_sid=session.call_sid,
            caller_phone=appointment.caller_phone,
            requested_time=appointment.requested_time,
        )
        if existing_appointment is not None:
            _log_realtime_tool(
                "event=appointment_create_skipped "
                f"stream_sid={session.stream_sid} call_sid={session.call_sid} "
                f"reason=duplicate appointment_request_id={existing_appointment.id}"
            )
            persist_realtime_call_log(
                session,
                event_name="realtime_appointment_duplicate",
                business_id=existing_appointment.business_id,
                payload={
                    "appointment_request_id": existing_appointment.id,
                    "requested_time": existing_appointment.requested_time,
                },
            )
            return _appointment_result(
                existing_appointment,
                calendar_status="existing" if existing_appointment.calendar_event_id else "existing_without_calendar",
                duplicate=True,
            )

        calendar_status = "disabled"
        if settings.google_calendar_enabled:
            if business is not None and business.google_calendar_connected and not business_token_json:
                calendar_status = "missing_business_token"
                _log_realtime_tool(
                    "event=google_calendar_event_failed "
                    f"stream_sid={session.stream_sid} business_id={business.id} reason=missing_calendar_token"
                )
            else:
                try:
                    requested_start, requested_end = build_appointment_window(
                        appointment_day=str(arguments["appointment_day"]),
                        appointment_time=str(arguments["appointment_time"]),
                        timezone_str=settings.google_timezone,
                        duration_minutes=settings.appointment_duration_minutes,
                    )
                    availability = check_calendar_availability(
                        start=requested_start,
                        end=requested_end,
                        token_json=business_token_json,
                        calendar_id=business_calendar_id,
                        timezone_str=settings.google_timezone,
                    )
                    if not availability.available:
                        raise CalendarServiceError("Requested appointment window overlaps an existing calendar event.")
                    calendar_booking = create_calendar_booking(
                        caller_name=appointment.caller_name,
                        callback_number=appointment.caller_phone or "",
                        appointment_day=str(arguments["appointment_day"]),
                        appointment_time=str(arguments["appointment_time"]),
                        notes=appointment.notes or "",
                        token_json=business_token_json,
                        calendar_id=business_calendar_id,
                        timezone_str=settings.google_timezone,
                    )
                    appointment.calendar_event_id = calendar_booking.event_id
                    appointment.calendar_event_link = calendar_booking.html_link
                    appointment.scheduled_start = calendar_booking.scheduled_start
                    appointment.scheduled_end = calendar_booking.scheduled_end
                    appointment.confirmed = True
                    calendar_status = "created"
                    _log_realtime_tool(
                        "event=google_calendar_event_created "
                        f"stream_sid={session.stream_sid} business_id={appointment.business_id} "
                        f"calendar_id={business_calendar_id or settings.google_calendar_id} "
                        f"event_id={calendar_booking.event_id}"
                    )
                except CalendarServiceError as exc:
                    calendar_status = "failed"
                    _log_realtime_tool(
                        "event=google_calendar_event_failed "
                        f"stream_sid={session.stream_sid} business_id={appointment.business_id} "
                        f"reason=calendar_service_error error={exc}"
                    )
                except Exception as exc:
                    calendar_status = "failed"
                    _log_realtime_tool(
                        "event=google_calendar_event_failed "
                        f"stream_sid={session.stream_sid} business_id={appointment.business_id} "
                        f"reason=unexpected_error error={exc}"
                    )

        db.add(appointment)
        db.commit()
        db.refresh(appointment)
        persist_realtime_call_log(
            session,
            event_name="realtime_appointment_created",
            business_id=appointment.business_id,
            payload={
                "appointment_request_id": appointment.id,
                "requested_time": appointment.requested_time,
                "calendar_status": calendar_status,
                "calendar_event_id": appointment.calendar_event_id,
            },
        )
        return _appointment_result(appointment, calendar_status=calendar_status)
    finally:
        db.close()


async def create_booking(session: RealtimeBridgeSession, arguments: dict[str, Any]) -> dict[str, Any]:
    return await book_appointment(session, arguments)


async def capture_callback(session: RealtimeBridgeSession, arguments: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "stub",
        "message": "Callback capture will call existing appointment request logic in a later patch.",
    }


async def log_call_summary(session: RealtimeBridgeSession, arguments: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "stub",
        "call_sid": session.call_sid,
        "summary": arguments.get("summary", ""),
    }


REALTIME_TOOL_HANDLERS = {
    "lookup_business": lookup_business,
    "check_availability": check_availability,
    "book_appointment": book_appointment,
    "create_booking": create_booking,
    "capture_callback": capture_callback,
    "log_call_summary": log_call_summary,
}
