import json

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from sqlalchemy.orm import Session
from twilio.twiml.voice_response import Gather, VoiceResponse

from .ai import (
    DEFAULT_BOOKING_ENABLED,
    DEFAULT_BUSINESS_GREETING,
    DEFAULT_BUSINESS_HOURS,
    DEFAULT_BUSINESS_NAME,
    BusinessContext,
    SessionContext,
    detect_and_respond,
    format_phone_number_for_speech,
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
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
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
    return "".join(char for char in value if char.isdigit())


def _resolve_business(db: Session, to_number: str | None) -> Business | None:
    if not to_number:
        return None

    business = db.query(Business).filter(Business.twilio_number == to_number).first()
    if business:
        return business

    normalized_target = _normalize_phone_number(to_number)
    if not normalized_target:
        return None

    for candidate in db.query(Business).all():
        if _normalize_phone_number(candidate.twilio_number) == normalized_target:
            return candidate
    return None


def _build_business_context(business: Business | None) -> BusinessContext:
    if business is None:
        return BusinessContext()

    return BusinessContext(
        id=business.id,
        name=business.name or DEFAULT_BUSINESS_NAME,
        twilio_number=business.twilio_number,
        forwarding_number=business.forwarding_number,
        greeting=business.greeting or DEFAULT_BUSINESS_GREETING,
        business_hours=business.business_hours or DEFAULT_BUSINESS_HOURS,
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
) -> CallSession | None:
    if not call_sid:
        return None

    session = db.query(CallSession).filter(CallSession.call_sid == call_sid).first()
    if session:
        session.from_number = from_number
        session.to_number = to_number
        return session

    session = CallSession(
        call_sid=call_sid,
        from_number=from_number,
        to_number=to_number,
        current_intent="GENERAL_QUESTION",
        current_state="NEW",
        slot_data_json="{}",
        transcript_json="[]",
        is_active=True,
    )
    db.add(session)
    db.flush()
    return session


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
        return True
    if result_intent == "CALLBACK_REQUEST" and result_state == "CALLBACK_READY":
        return True
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


@app.post("/voice")
async def voice(request: Request, db: Session = Depends(get_db)):
    form = await request.form()

    speech = form.get("SpeechResult", "")
    call_sid = form.get("CallSid")
    from_number = form.get("From")
    to_number = form.get("To")
    call_status = form.get("CallStatus")
    session = _get_or_create_session(db, call_sid, from_number, to_number)
    session_context = _build_session_context(session)
    business = _resolve_business(db, to_number)
    business_context = _build_business_context(business)

    response = VoiceResponse()

    if not speech:
        gather = Gather(
            input="speech",
            action="/voice",
            method="POST",
            speech_timeout="auto",
        )
        gather.say(business_context.greeting)
        if session is not None:
            session.transcript_json = json.dumps(
                _append_transcript(session_context.transcript, "assistant", business_context.greeting)
            )
            session.current_state = "GREETING_SENT"
            session.is_active = True
            db.commit()
        response.append(gather)
        response.redirect("/voice")
        return Response(content=str(response), media_type="application/xml")

    transcript = _append_transcript(session_context.transcript, "user", speech)
    session_context.transcript = transcript
    result = detect_and_respond(speech, business_context, session_context)
    merged_slot_data = _merge_session_slots(session_context.slot_data, result.fields)
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
            caller_phone=from_number,
            requested_time=" ".join(
                part
                for part in (
                    merged_slot_data.get("appointment_day"),
                    merged_slot_data.get("appointment_time"),
                )
                if part
            )
            or None,
            notes=speech,
        )
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
    )
    db.add(log)

    if session is not None:
        session.current_intent = result.intent
        session.current_state = result.state
        session.slot_data_json = json.dumps(merged_slot_data)
        session.transcript_json = json.dumps(updated_transcript)
        session.is_active = call_status not in {"completed", "canceled", "failed", "busy", "no-answer"}

    db.commit()

    response.say(speech_safe_response)

    gather = Gather(
        input="speech",
        action="/voice",
        method="POST",
        speech_timeout="auto",
    )
    response.append(gather)
    response.redirect("/voice")
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
    row = Business(
        name=payload.name,
        twilio_number=payload.twilio_number,
        forwarding_number=payload.forwarding_number,
        greeting=payload.greeting or DEFAULT_BUSINESS_GREETING,
        business_hours=payload.business_hours or DEFAULT_BUSINESS_HOURS,
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

    row = Business(
        name=DEFAULT_BUSINESS_NAME,
        twilio_number=twilio_number,
        forwarding_number=forwarding_number,
        greeting=DEFAULT_BUSINESS_GREETING,
        business_hours=DEFAULT_BUSINESS_HOURS,
        booking_enabled=DEFAULT_BOOKING_ENABLED,
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
