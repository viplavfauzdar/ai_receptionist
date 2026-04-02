from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from sqlalchemy.orm import Session
from twilio.twiml.voice_response import Gather, VoiceResponse

from .ai import detect_intent, generate_reply
from .config import settings
from .db import Base, ensure_call_log_columns, engine, get_db
from .models import AppointmentRequest, CallLog
from .schemas import AppointmentCreate, AppointmentOut, CallLogOut

Base.metadata.create_all(bind=engine)
ensure_call_log_columns()

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


@app.get("/debug/twiml")
def debug_twiml(speech: str = ""):
    response = VoiceResponse()

    if not speech:
        gather = Gather(
            input="speech",
            action="/voice",
            method="POST",
            speech_timeout="auto",
        )
        gather.say(settings.business_greeting)
        response.append(gather)
        response.redirect("/voice")
        return Response(content=str(response), media_type="application/xml")

    intent = detect_intent(speech)
    ai_reply = generate_reply(speech, intent)
    response.say(ai_reply)

    gather = Gather(
        input="speech",
        action="/voice",
        method="POST",
        speech_timeout="auto",
    )
    response.append(gather)
    response.redirect("/voice")
    return Response(content=str(response), media_type="application/xml")


@app.post("/voice")
async def voice(request: Request, db: Session = Depends(get_db)):
    form = await request.form()

    speech = form.get("SpeechResult", "")
    call_sid = form.get("CallSid")
    from_number = form.get("From")
    to_number = form.get("To")
    call_status = form.get("CallStatus")

    response = VoiceResponse()

    if not speech:
        gather = Gather(
            input="speech",
            action="/voice",
            method="POST",
            speech_timeout="auto",
        )
        gather.say(settings.business_greeting)
        response.append(gather)
        response.redirect("/voice")
        return Response(content=str(response), media_type="application/xml")

    intent = detect_intent(speech)
    ai_reply = generate_reply(speech, intent)

    if intent.name == "booking_appointment" and settings.booking_enabled:
        appointment = AppointmentRequest(
            caller_phone=from_number,
            requested_time=intent.requested_time,
            notes=speech,
        )
        db.add(appointment)

    log = CallLog(
        call_sid=call_sid,
        from_number=from_number,
        to_number=to_number,
        speech_input=speech,
        ai_response=ai_reply,
        call_status=call_status,
        detected_intent=intent.name,
        intent_data=intent.to_json(),
    )
    db.add(log)
    db.commit()

    response.say(ai_reply)

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


@app.post("/api/appointments", response_model=AppointmentOut)
def create_appointment(payload: AppointmentCreate, db: Session = Depends(get_db)):
    row = AppointmentRequest(
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
