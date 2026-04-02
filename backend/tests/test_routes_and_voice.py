import json
import xml.etree.ElementTree as ET

from sqlalchemy.orm import sessionmaker

from app.models import AppointmentRequest, Business, CallLog, CallSession


def _parse_xml(text: str) -> ET.Element:
    return ET.fromstring(text)


def _post_voice(client, **form_data):
    return client.post("/voice", data=form_data)


def test_root_health_and_docs_routes(client):
    root_res = client.get("/")
    assert root_res.status_code == 200
    assert root_res.json()["health"] == "/health"

    health_res = client.get("/health")
    assert health_res.status_code == 200
    body = health_res.json()
    assert body["status"] == "ok"
    assert "mode" in body

    docs_res = client.get("/docs")
    assert docs_res.status_code == 200
    assert "swagger" in docs_res.text.lower()


def test_voice_initial_request_returns_gather_and_fallback_greeting(client, db_session: sessionmaker):
    res = _post_voice(
        client,
        CallSid="CA-initial",
        From="+15551230000",
        To="+15557654321",
        CallStatus="ringing",
    )

    assert res.status_code == 200
    assert "application/xml" in res.headers["content-type"]
    xml = _parse_xml(res.text)
    assert xml.find("Gather") is not None
    assert "Bright Smile Dental" in res.text

    with db_session() as db:
        session = db.query(CallSession).filter(CallSession.call_sid == "CA-initial").one()
        transcript = json.loads(session.transcript_json)
        assert transcript[-1]["role"] == "assistant"
        assert "Bright Smile Dental" in transcript[-1]["text"]


def test_voice_initial_request_uses_business_greeting_when_business_matches(client, db_session: sessionmaker):
    with db_session() as db:
        db.add(
            Business(
                name="Acme Dental",
                twilio_number="+15550001111",
                greeting="Hello from Acme Dental.",
                business_hours="Mon-Fri 8 AM to 4 PM",
                booking_enabled=True,
            )
        )
        db.commit()

    res = _post_voice(
        client,
        CallSid="CA-business-greeting",
        From="+15551230000",
        To="+15550001111",
        CallStatus="ringing",
    )

    assert res.status_code == 200
    assert "Hello from Acme Dental." in res.text
    xml = _parse_xml(res.text)
    assert xml.find("Gather") is not None


def test_voice_spoken_input_logs_call_and_returns_twilml(client, db_session: sessionmaker):
    res = _post_voice(
        client,
        CallSid="CA-spoken",
        From="+15551230000",
        To="+15557654321",
        CallStatus="in-progress",
        SpeechResult="What are your hours?",
    )

    assert res.status_code == 200
    xml = _parse_xml(res.text)
    assert xml.find("Gather") is not None
    assert xml.find("Redirect") is not None
    assert "Our hours are" in res.text

    with db_session() as db:
        call_log = db.query(CallLog).filter(CallLog.call_sid == "CA-spoken").one()
        assert call_log.speech_input == "What are your hours?"
        assert call_log.detected_intent == "BUSINESS_HOURS"
        assert "Our hours are" in call_log.ai_response


def test_booking_flow_persists_state_across_turns_and_creates_appointment(client, db_session: sessionmaker):
    call_sid = "CA-booking"

    _post_voice(
        client,
        CallSid=call_sid,
        From="+15551230000",
        To="+15557654321",
        CallStatus="in-progress",
        SpeechResult="I want to book an appointment",
    )
    _post_voice(
        client,
        CallSid=call_sid,
        From="+15551230000",
        To="+15557654321",
        CallStatus="in-progress",
        SpeechResult="Tuesday",
    )
    res = _post_voice(
        client,
        CallSid=call_sid,
        From="+15551230000",
        To="+15557654321",
        CallStatus="in-progress",
        SpeechResult="3 pm and my number is 6784624453",
    )

    assert res.status_code == 200
    assert "6 7 8, 4 6 2, 4 4 5 3" in res.text

    with db_session() as db:
        session = db.query(CallSession).filter(CallSession.call_sid == call_sid).one()
        slot_data = json.loads(session.slot_data_json)
        assert session.current_intent == "BOOK_APPOINTMENT"
        assert session.current_state == "BOOKING_COMPLETE"
        assert slot_data["appointment_day"] == "Tuesday"
        assert slot_data["appointment_time"] == "3 pm"
        assert slot_data["callback_number"] == "6784624453"

        appointment = db.query(AppointmentRequest).one()
        assert appointment.caller_phone == "+15551230000"
        assert appointment.requested_time == "Tuesday 3 pm"


def test_callback_flow_persists_state_and_creates_request(client, db_session: sessionmaker):
    call_sid = "CA-callback"

    _post_voice(
        client,
        CallSid=call_sid,
        From="+15551230000",
        To="+15557654321",
        CallStatus="in-progress",
        SpeechResult="Can someone call me back?",
    )
    res = _post_voice(
        client,
        CallSid=call_sid,
        From="+15551230000",
        To="+15557654321",
        CallStatus="in-progress",
        SpeechResult="Use 6784624453",
    )

    assert res.status_code == 200
    assert "6 7 8, 4 6 2, 4 4 5 3" in res.text

    with db_session() as db:
        session = db.query(CallSession).filter(CallSession.call_sid == call_sid).one()
        slot_data = json.loads(session.slot_data_json)
        assert session.current_intent == "CALLBACK_REQUEST"
        assert session.current_state == "CALLBACK_READY"
        assert slot_data["callback_number"] == "6784624453"

        appointment = db.query(AppointmentRequest).one()
        assert appointment.caller_phone == "+15551230000"


def test_settings_endpoint_reads_from_business_table(client, db_session: sessionmaker):
    with db_session() as db:
        db.add(
            Business(
                name="Westside Dental",
                twilio_number="+15550001111",
                greeting="Welcome to Westside Dental.",
                business_hours="Sat 10 AM to 2 PM",
                booking_enabled=False,
            )
        )
        db.commit()

    res = client.get("/api/settings")
    assert res.status_code == 200
    body = res.json()
    assert body["business_name"] == "Westside Dental"
    assert body["business_greeting"] == "Welcome to Westside Dental."
    assert body["business_hours"] == "Sat 10 AM to 2 PM"
    assert body["booking_enabled"] is False
