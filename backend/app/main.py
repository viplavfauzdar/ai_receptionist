from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from sqlalchemy.orm import Session
from twilio.twiml.voice_response import Gather, VoiceResponse

from .ai import BusinessContext, detect_and_respond
from .config import settings
from .db import Base, ensure_sqlite_compatibility, engine, get_db
from .models import AppointmentRequest, Business, CallLog
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
    return {"status": "ok", "business_name": settings.business_name}


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
        name=business.name or settings.business_name,
        twilio_number=business.twilio_number,
        forwarding_number=business.forwarding_number,
        greeting=business.greeting or settings.business_greeting,
        business_hours=business.business_hours or settings.business_hours,
        booking_enabled=business.booking_enabled,
        knowledge_text=business.knowledge_text or "",
    )


@app.post("/voice")
async def voice(request: Request, db: Session = Depends(get_db)):
    form = await request.form()

    speech = form.get("SpeechResult", "")
    call_sid = form.get("CallSid")
    from_number = form.get("From")
    to_number = form.get("To")
    call_status = form.get("CallStatus")
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
        response.append(gather)
        response.redirect("/voice")
        return Response(content=str(response), media_type="application/xml")

    result = detect_and_respond(speech, business_context)

    if result.intent in {"BOOK_APPOINTMENT", "CALLBACK_REQUEST"}:
        appointment = AppointmentRequest(
            business_id=business_context.id,
            caller_phone=from_number,
            requested_time=result.fields.get("requested_time"),
            notes=speech,
        )
        db.add(appointment)

    log = CallLog(
        business_id=business_context.id,
        call_sid=call_sid,
        from_number=from_number,
        to_number=to_number,
        speech_input=speech,
        ai_response=result.response,
        call_status=call_status,
        detected_intent=result.intent,
        intent_data=result.to_json(),
    )
    db.add(log)
    db.commit()

    response.say(result.response)

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
def get_settings():
    return {
        "business_name": settings.business_name,
        "business_greeting": settings.business_greeting,
        "business_hours": settings.business_hours,
        "booking_enabled": settings.booking_enabled,
    }


@app.post("/api/businesses", response_model=BusinessOut)
def create_business(payload: BusinessCreate, db: Session = Depends(get_db)):
    row = Business(
        name=payload.name,
        twilio_number=payload.twilio_number,
        forwarding_number=payload.forwarding_number,
        greeting=payload.greeting,
        business_hours=payload.business_hours,
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
        name=settings.business_name,
        twilio_number=twilio_number,
        forwarding_number=forwarding_number,
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
