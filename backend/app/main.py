import json
from datetime import datetime, timedelta

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from sqlalchemy.orm import Session
from twilio.request_validator import RequestValidator
from twilio.twiml.voice_response import Gather, VoiceResponse

from .ai import (
    BusinessContext,
    SessionContext,
    detect_and_respond,
    format_phone_number_for_speech,
)
from .calendar_service import (
    CalendarServiceError,
    build_appointment_window,
    check_calendar_availability,
    create_calendar_booking,
)
from .config import settings
from .db import Base, ensure_sqlite_compatibility, engine, get_db
from .models import AppointmentRequest, Business, CallLog, CallSession
from .schemas import AppointmentCreate, AppointmentOut, BusinessCreate, BusinessOut, CallLogOut

Base.metadata.create_all(bind=engine)
ensure_sqlite_compatibility()

app = FastAPI(title="AI Receptionist MVP", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {
        "name": "AI Receptionist MVP",
        "status": "ok",
        "health": "/health",
    }


@app.get("/health")
def health():
    return {"status": "ok", "mode": "multi-tenant"}


def _normalize_phone_number(value: str | None) -> str:
    if not value:
        return ""
    digits = "".join(char for char in value.strip() if char.isdigit())
    if len(digits) == 11 and digits.startswith("1"):
        return digits[1:]
    return digits


def _normalize_business_numbers(
    *,
    twilio_number: str | None,
    forwarding_number: str | None,
) -> dict[str, str | None]:
    normalized_twilio = _normalize_phone_number(twilio_number)
    return {
        "twilio_number": twilio_number.strip() if twilio_number else "",
        "twilio_number_normalized": normalized_twilio or None,
        "forwarding_number": forwarding_number.strip() if forwarding_number else None,
    }


def _log_voice(message: str) -> None:
    print(f"[voice] {message}", flush=True)


def _resolve_business(db: Session, to_number: str | None) -> Business | None:
    if not to_number:
        _log_voice("business_lookup skipped reason=missing_to_number")
        return None

    business = db.query(Business).filter(Business.twilio_number == to_number).first()
    if business:
        normalized_target = _normalize_phone_number(to_number)
        if normalized_target and business.twilio_number_normalized != normalized_target:
            business.twilio_number_normalized = normalized_target
        _log_voice(
            f"business_lookup matched mode=exact to_number={to_number} business_id={business.id} business_name={business.name}"
        )
        return business

    normalized_target = _normalize_phone_number(to_number)
    if not normalized_target:
        _log_voice(f"business_lookup skipped reason=empty_normalized_to_number raw_to_number={to_number}")
        return None

    business = (
        db.query(Business)
        .filter(Business.twilio_number_normalized == normalized_target)
        .order_by(Business.id.asc())
        .first()
    )
    if business:
        _log_voice(
            "business_lookup matched "
            f"mode=normalized to_number={to_number} normalized_to_number={normalized_target} "
            f"business_id={business.id} business_name={business.name} stored_twilio_number={business.twilio_number}"
        )
        return business
    _log_voice(f"business_lookup missed to_number={to_number} normalized_to_number={normalized_target}")
    return None


def _build_business_context(business: Business | None) -> BusinessContext:
    if business is None:
        return BusinessContext()

    return BusinessContext(
        id=business.id,
        name=business.name or settings.business_name,
        twilio_number=business.twilio_number,
        forwarding_number=business.forwarding_number,
        greeting=business.greeting or settings.business_greeting,
        business_hours=business.business_hours or settings.business_hours,
        booking_enabled=business.booking_enabled,
        knowledge_text=business.knowledge_text or "",
    )


def _get_display_business(db: Session) -> BusinessContext:
    business = db.query(Business).order_by(Business.created_at.desc()).first()
    return _build_business_context(business)


def _load_json_dict(value: str | None) -> dict[str, str]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {str(key): str(item) for key, item in parsed.items() if item is not None}


def _load_json_list(value: str | None) -> list[dict[str, str]]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    cleaned: list[dict[str, str]] = []
    for item in parsed:
        if isinstance(item, dict):
            cleaned.append({str(key): str(val) for key, val in item.items() if val is not None})
    return cleaned


def _get_or_create_session(
    db: Session,
    call_sid: str | None,
    from_number: str | None,
    to_number: str | None,
) -> tuple[CallSession | None, bool]:
    if not call_sid:
        return None, False

    session = db.query(CallSession).filter(CallSession.call_sid == call_sid).first()
    if session:
        session.from_number = from_number
        session.to_number = to_number
        return session, False

    session = CallSession(
        call_sid=call_sid,
        from_number=from_number,
        to_number=to_number,
        current_intent="GENERAL_QUESTION",
        current_state="NEW",
        slot_data_json="{}",
        transcript_json="[]",
        turn_count=0,
        llm_call_count=0,
        is_active=True,
    )
    db.add(session)
    db.flush()
    return session, True


def _build_session_context(session: CallSession | None) -> SessionContext:
    if session is None:
        return SessionContext()

    return SessionContext(
        call_sid=session.call_sid,
        current_intent=session.current_intent or "GENERAL_QUESTION",
        current_state=session.current_state or "NEW",
        slot_data=_load_json_dict(session.slot_data_json),
        transcript=_load_json_list(session.transcript_json),
    )


def _append_transcript(transcript: list[dict[str, str]], role: str, text: str) -> list[dict[str, str]]:
    updated = list(transcript)
    updated.append({"role": role, "text": text})
    return updated[-20:]


def _merge_session_slots(current_slots: dict[str, str], new_fields: dict[str, str]) -> dict[str, str]:
    merged = dict(current_slots)
    for key, value in new_fields.items():
        if value:
            merged[key] = value
    return merged


def _should_create_request(result_intent: str, result_state: str, slot_data: dict[str, str]) -> bool:
    if slot_data.get("request_saved") == "true":
        return False
    if result_intent == "BOOK_APPOINTMENT" and result_state == "BOOKING_COMPLETE":
        return all(slot_data.get(key) for key in ("appointment_day", "appointment_time", "callback_number", "caller_name"))
    if result_intent == "CALLBACK_REQUEST" and result_state == "CALLBACK_READY":
        return all(slot_data.get(key) for key in ("callback_number", "caller_name"))
    return False


def _build_speech_safe_response(result_intent: str, result_state: str, response: str, slot_data: dict[str, str]) -> str:
    callback_number = slot_data.get("callback_number")
    if not callback_number:
        return response

    spoken_number = format_phone_number_for_speech(callback_number)
    if result_intent == "CALLBACK_REQUEST" and result_state == "CALLBACK_READY":
        return f"Thanks. We can follow up at {spoken_number}."
    if result_intent == "BOOK_APPOINTMENT" and result_state == "BOOKING_COMPLETE":
        return f"Thanks. I have your day, time, and callback number as {spoken_number}. We will follow up shortly."
    return response


def _build_requested_time(slot_data: dict[str, str]) -> str | None:
    return (
        " ".join(
            part
            for part in (
                slot_data.get("appointment_day"),
                slot_data.get("appointment_time"),
            )
            if part
        )
        or None
    )


def _build_terminal_voice_response(message: str) -> Response:
    response = VoiceResponse()
    response.say(message)
    response.hangup()
    return Response(content=str(response), media_type="application/xml")


def _record_protection_log(
    db: Session,
    *,
    reason: str,
    call_sid: str | None,
    from_number: str | None,
    to_number: str | None,
    call_status: str | None,
    ai_response: str,
    business_id: int | None = None,
    speech_input: str | None = None,
    session: CallSession | None = None,
) -> None:
    _log_voice(
        "request_protection "
        f"reason={reason} call_sid={call_sid} from_number={from_number} to_number={to_number}"
    )
    if session is not None:
        session.last_protection_reason = reason
    db.add(
        CallLog(
            business_id=business_id,
            call_sid=call_sid,
            from_number=from_number,
            to_number=to_number,
            speech_input=speech_input,
            ai_response=ai_response,
            call_status=call_status,
            detected_intent=session.current_intent if session is not None else "GENERAL_QUESTION",
            intent_data=json.dumps(
                {
                    "intent": session.current_intent if session is not None else "GENERAL_QUESTION",
                    "state": session.current_state if session is not None else "NEW",
                    "response": ai_response,
                    "fields": _load_json_dict(session.slot_data_json) if session is not None else {},
                }
            ),
            protection_reason=reason,
        )
    )


def _count_recent_calls_for_number(db: Session, from_number: str) -> int:
    cutoff = datetime.utcnow() - timedelta(hours=1)
    return (
        db.query(CallSession)
        .filter(
            CallSession.from_number == from_number,
            CallSession.created_at >= cutoff,
        )
        .count()
    )


def _is_rate_limited_new_call(db: Session, from_number: str | None) -> bool:
    if not settings.enable_basic_rate_limiting or not from_number:
        return False
    return _count_recent_calls_for_number(db, from_number) >= settings.max_new_calls_per_number_per_hour


def _is_terminal_call_status(call_status: str | None) -> bool:
    return call_status in {"completed", "canceled", "failed", "busy", "no-answer"}


def _should_create_calendar_event(result_intent: str, result_state: str, slot_data: dict[str, str]) -> bool:
    return (
        settings.google_calendar_enabled
        and result_intent == "BOOK_APPOINTMENT"
        and result_state == "BOOKING_COMPLETE"
        and all(slot_data.get(key) for key in ("appointment_day", "appointment_time", "callback_number"))
    )


def _calendar_unavailable_response() -> str:
    return "That time looks unavailable. Please suggest another time."


def _calendar_unavailable_with_suggestion_response(suggested_slot: str | None) -> str:
    if suggested_slot:
        return f"That time looks unavailable. I could offer {suggested_slot}. Would that work?"
    return _calendar_unavailable_response()


def _get_silence_count(slot_data: dict[str, str]) -> int:
    raw_value = slot_data.get("silence_count", "0")
    try:
        return max(0, int(raw_value))
    except (TypeError, ValueError):
        return 0


def _clear_silence_count(slot_data: dict[str, str]) -> dict[str, str]:
    updated = dict(slot_data)
    updated.pop("silence_count", None)
    return updated


def _build_silence_response(silence_count: int) -> tuple[str, bool]:
    if silence_count <= 1:
        return ("Sorry, I didn't catch that. Please say that again.", False)
    if silence_count == 2:
        return ("I still didn't hear anything. Please tell me how I can help.", False)
    return ("Thanks for calling. Goodbye.", True)


def _build_voice_gather(prompt: str) -> Gather:
    gather = Gather(
        input="speech",
        action="/voice",
        method="POST",
        speech_timeout="auto",
        timeout=3,
        action_on_empty_result=True,
    )
    if prompt:
        gather.say(prompt)
    return gather


def _get_request_validation_url(request: Request) -> str:
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    query = f"?{request.url.query}" if request.url.query else ""
    return f"{scheme}://{host}{request.url.path}{query}"


def _is_valid_twilio_request(request: Request, form_data: dict[str, str | None]) -> bool:
    if settings.disable_twilio_signature_validation:
        return True

    signature = request.headers.get("x-twilio-signature", "")
    if not settings.twilio_auth_token or not signature:
        return False

    validator = RequestValidator(settings.twilio_auth_token)
    params = {key: value or "" for key, value in form_data.items()}
    return validator.validate(_get_request_validation_url(request), params, signature)


@app.post("/voice")
async def voice(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    form_data = {key: form.get(key) for key in form.keys()}
    if not _is_valid_twilio_request(request, form_data):
        _log_voice("request_rejected reason=invalid_twilio_signature")
        return Response(content="Forbidden", status_code=403, media_type="text/plain")

    _log_voice(
        "incoming_form "
        f"keys={sorted(form_data.keys())} "
        f"CallSid={form_data.get('CallSid')} From={form_data.get('From')} To={form_data.get('To')} "
        f"CallStatus={form_data.get('CallStatus')} SpeechResult={form_data.get('SpeechResult')!r}"
    )

    speech = form.get("SpeechResult", "")
    call_sid = form.get("CallSid")
    from_number = form.get("From")
    to_number = form.get("To")
    call_status = form.get("CallStatus")

    if not call_sid or not from_number:
        prompt = "Sorry, we could not process this call. Please try again later."
        _record_protection_log(
            db,
            reason="malformed_request",
            call_sid=call_sid,
            from_number=from_number,
            to_number=to_number,
            call_status=call_status,
            ai_response=prompt,
            speech_input=speech,
        )
        db.commit()
        return _build_terminal_voice_response(prompt)

    existing_session = db.query(CallSession).filter(CallSession.call_sid == call_sid).first()
    if existing_session is None and _is_rate_limited_new_call(db, from_number):
        prompt = "We are receiving too many calls from this number right now. Please try again later."
        _record_protection_log(
            db,
            reason="caller_rate_limited",
            call_sid=call_sid,
            from_number=from_number,
            to_number=to_number,
            call_status=call_status,
            ai_response=prompt,
            speech_input=speech,
        )
        db.commit()
        return _build_terminal_voice_response(prompt)

    session, _ = _get_or_create_session(db, call_sid, from_number, to_number)
    session_context = _build_session_context(session)
    business = _resolve_business(db, to_number)
    business_context = _build_business_context(business)
    _log_voice(
        "request "
        f"call_sid={call_sid} from_number={from_number} to_number={to_number} "
        f"speech_present={bool(speech)} business_id={business_context.id} business_name={business_context.name} "
        f"greeting={business_context.greeting!r}"
    )

    response = VoiceResponse()

    if session is not None and session.turn_count >= settings.max_call_turns:
        prompt = "We need to end this call for now. Please call back if you still need help."
        session.is_active = False
        _record_protection_log(
            db,
            reason="turn_limit_exceeded",
            call_sid=call_sid,
            from_number=from_number,
            to_number=to_number,
            call_status=call_status,
            ai_response=prompt,
            business_id=business_context.id,
            speech_input=speech,
            session=session,
        )
        db.commit()
        return _build_terminal_voice_response(prompt)

    if session is not None:
        session.turn_count = (session.turn_count or 0) + 1

    if not speech:
        merged_slot_data = dict(session_context.slot_data)

        if session is None or not session_context.transcript:
            prompt = business_context.greeting
            merged_slot_data = _clear_silence_count(merged_slot_data)
            gather = _build_voice_gather(prompt)
            if session is not None:
                session.transcript_json = json.dumps(
                    _append_transcript(session_context.transcript, "assistant", prompt)
                )
                session.current_state = "GREETING_SENT"
                session.slot_data_json = json.dumps(merged_slot_data)
                session.last_protection_reason = None
                session.is_active = True
                db.commit()
            response.append(gather)
            return Response(content=str(response), media_type="application/xml")

        silence_count = _get_silence_count(merged_slot_data) + 1
        merged_slot_data["silence_count"] = str(silence_count)
        prompt, should_end_call = _build_silence_response(silence_count)

        if session is not None:
            session.transcript_json = json.dumps(
                _append_transcript(session_context.transcript, "assistant", prompt)
            )
            session.slot_data_json = json.dumps(merged_slot_data)
            session.last_protection_reason = None
            session.is_active = not should_end_call

        log = CallLog(
            business_id=business_context.id,
            call_sid=call_sid,
            from_number=from_number,
            to_number=to_number,
            speech_input="",
            ai_response=prompt,
            call_status=call_status,
            detected_intent=session_context.current_intent,
            intent_data=json.dumps(
                {
                    "intent": session_context.current_intent,
                    "state": session_context.current_state,
                    "response": prompt,
                    "fields": merged_slot_data,
                }
            ),
            protection_reason=None,
        )
        db.add(log)
        db.commit()

        response.say(prompt)
        if should_end_call:
            response.hangup()
        else:
            response.append(_build_voice_gather(""))
        return Response(content=str(response), media_type="application/xml")

    transcript = _append_transcript(session_context.transcript, "user", speech)
    session_context.transcript = transcript
    protection_reason: str | None = None
    llm_limit_exceeded = (
        session is not None
        and bool(settings.openai_api_key)
        and session.llm_call_count >= settings.max_llm_calls_per_session
    )
    if llm_limit_exceeded:
        protection_reason = "llm_limit_exceeded"
        result = detect_and_respond(
            speech,
            business_context,
            session_context,
            force_fallback_reason=protection_reason,
        )
    else:
        if session is not None and settings.openai_api_key:
            session.llm_call_count = (session.llm_call_count or 0) + 1
        result = detect_and_respond(speech, business_context, session_context)
    merged_slot_data = _clear_silence_count(_merge_session_slots(session_context.slot_data, result.fields))
    speech_safe_response = _build_speech_safe_response(
        result.intent,
        result.state,
        result.response,
        merged_slot_data,
    )
    updated_transcript = _append_transcript(transcript, "assistant", speech_safe_response)

    if _should_create_request(result.intent, result.state, merged_slot_data):
        appointment = AppointmentRequest(
            business_id=business_context.id,
            caller_name=merged_slot_data.get("caller_name"),
            caller_phone=merged_slot_data.get("callback_number") or from_number,
            requested_time=_build_requested_time(merged_slot_data),
            notes=speech,
        )
        if _should_create_calendar_event(result.intent, result.state, merged_slot_data):
            try:
                requested_start, requested_end = build_appointment_window(
                    appointment_day=merged_slot_data["appointment_day"],
                    appointment_time=merged_slot_data["appointment_time"],
                    timezone_str=settings.google_timezone,
                    duration_minutes=settings.appointment_duration_minutes,
                )
                availability = check_calendar_availability(
                    start=requested_start,
                    end=requested_end,
                )
                if not availability.available:
                    speech_safe_response = _calendar_unavailable_with_suggestion_response(
                        availability.suggested_slots[0] if availability.suggested_slots else None
                    )
                    raise CalendarServiceError("Requested appointment window overlaps an existing calendar event.")
                calendar_booking = create_calendar_booking(
                    caller_name=merged_slot_data.get("caller_name"),
                    callback_number=merged_slot_data["callback_number"],
                    appointment_day=merged_slot_data["appointment_day"],
                    appointment_time=merged_slot_data["appointment_time"],
                    notes=speech,
                )
                appointment.calendar_event_id = calendar_booking.event_id
                appointment.calendar_event_link = calendar_booking.html_link
                appointment.scheduled_start = calendar_booking.scheduled_start
                appointment.scheduled_end = calendar_booking.scheduled_end
                appointment.confirmed = True
                speech_safe_response = (
                    f"Thanks {merged_slot_data.get('caller_name') or ''}. "
                    f"You're booked for {merged_slot_data['appointment_day']} at {merged_slot_data['appointment_time']}."
                ).replace("  ", " ").strip()
            except CalendarServiceError as exc:
                _log_voice(f"calendar_booking_failed reason=calendar_service_error error={exc}")
                if "overlaps an existing calendar event" in str(exc):
                    speech_safe_response = speech_safe_response or _calendar_unavailable_response()
                else:
                    speech_safe_response = "I have your request and someone from the office will confirm the appointment shortly."
            except Exception as exc:
                _log_voice(f"calendar_booking_failed reason=unexpected_error error={exc}")
                speech_safe_response = "I have your request and someone from the office will confirm the appointment shortly."
        db.add(appointment)
        merged_slot_data["request_saved"] = "true"

    log = CallLog(
        business_id=business_context.id,
        call_sid=call_sid,
        from_number=from_number,
        to_number=to_number,
        speech_input=speech,
        ai_response=speech_safe_response,
        call_status=call_status,
        detected_intent=result.intent,
        intent_data=result.to_json(),
        protection_reason=protection_reason,
    )
    db.add(log)

    if session is not None:
        session.current_intent = result.intent
        session.current_state = result.state
        session.slot_data_json = json.dumps(merged_slot_data)
        session.transcript_json = json.dumps(updated_transcript)
        session.last_protection_reason = protection_reason
        session.is_active = not _is_terminal_call_status(call_status)

    db.commit()

    response.say(speech_safe_response)

    response.append(_build_voice_gather(""))
    return Response(content=str(response), media_type="application/xml")


@app.get("/api/calls", response_model=list[CallLogOut])
def list_calls(db: Session = Depends(get_db)):
    rows = db.query(CallLog).order_by(CallLog.created_at.desc()).limit(100).all()
    return rows


@app.get("/api/settings")
def get_settings(db: Session = Depends(get_db)):
    business = _get_display_business(db)
    return {
        "business_name": business.name,
        "business_greeting": business.greeting,
        "business_hours": business.business_hours,
        "booking_enabled": business.booking_enabled,
    }


@app.post("/api/businesses", response_model=BusinessOut)
def create_business(payload: BusinessCreate, db: Session = Depends(get_db)):
    number_fields = _normalize_business_numbers(
        twilio_number=payload.twilio_number,
        forwarding_number=payload.forwarding_number,
    )
    row = Business(
        name=payload.name,
        twilio_number=number_fields["twilio_number"],
        twilio_number_normalized=number_fields["twilio_number_normalized"],
        forwarding_number=number_fields["forwarding_number"],
        greeting=payload.greeting or settings.business_greeting,
        business_hours=payload.business_hours or settings.business_hours,
        booking_enabled=payload.booking_enabled,
        knowledge_text=payload.knowledge_text,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@app.get("/api/businesses", response_model=list[BusinessOut])
def list_businesses(db: Session = Depends(get_db)):
    return db.query(Business).order_by(Business.created_at.desc()).all()


@app.post("/api/demo-business", response_model=BusinessOut)
def create_demo_business(
    twilio_number: str = "+15550001111",
    forwarding_number: str = "+15550002222",
    db: Session = Depends(get_db),
):
    existing = _resolve_business(db, twilio_number)
    if existing:
        return existing

    number_fields = _normalize_business_numbers(
        twilio_number=twilio_number,
        forwarding_number=forwarding_number,
    )
    row = Business(
        name=settings.business_name,
        twilio_number=number_fields["twilio_number"],
        twilio_number_normalized=number_fields["twilio_number_normalized"],
        forwarding_number=number_fields["forwarding_number"],
        greeting=settings.business_greeting,
        business_hours=settings.business_hours,
        booking_enabled=settings.booking_enabled,
        knowledge_text="Answer using the business details configured for this tenant.",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@app.post("/api/appointments", response_model=AppointmentOut)
def create_appointment(payload: AppointmentCreate, db: Session = Depends(get_db)):
    row = AppointmentRequest(
        business_id=payload.business_id,
        caller_name=payload.caller_name,
        caller_phone=payload.caller_phone,
        requested_time=payload.requested_time,
        notes=payload.notes,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@app.get("/api/appointments", response_model=list[AppointmentOut])
def list_appointments(db: Session = Depends(get_db)):
    rows = db.query(AppointmentRequest).order_by(AppointmentRequest.created_at.desc()).limit(100).all()
    return rows
