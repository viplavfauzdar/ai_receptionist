import json
import xml.etree.ElementTree as ET
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from sqlalchemy.orm import sessionmaker

from app.calendar_service import CalendarServiceError
from app.config import settings
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


def test_cors_allows_configured_local_origin(client):
    res = client.options(
        "/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert res.status_code == 200
    assert res.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_cors_rejects_unconfigured_origin(client):
    res = client.options(
        "/health",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert "access-control-allow-origin" not in res.headers


def test_voice_rejects_invalid_twilio_signature(client, db_session: sessionmaker, monkeypatch):
    monkeypatch.setattr(settings, "disable_twilio_signature_validation", False)

    res = client.post(
        "/voice",
        data={
            "CallSid": "CA-invalid-signature",
            "From": "+15551230000",
            "To": "+15557654321",
            "CallStatus": "in-progress",
            "SpeechResult": "What are your hours?",
        },
        headers={"x-twilio-signature": "bad-signature"},
    )

    assert res.status_code == 403

    with db_session() as db:
        assert db.query(CallLog).count() == 0
        assert db.query(CallSession).count() == 0


def test_voice_accepts_valid_twilio_signature(client, db_session: sessionmaker, monkeypatch, twilio_signature):
    monkeypatch.setattr(settings, "disable_twilio_signature_validation", False)
    payload = {
        "CallSid": "CA-valid-signature",
        "From": "+15551230000",
        "To": "+15557654321",
        "CallStatus": "in-progress",
        "SpeechResult": "What are your hours?",
    }
    signature = twilio_signature("http://testserver/voice", payload)

    res = client.post("/voice", data=payload, headers={"x-twilio-signature": signature})

    assert res.status_code == 200
    assert "Our hours are" in res.text


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
    gather = xml.find("Gather")
    assert gather is not None
    assert gather.attrib["speechTimeout"] == "auto"
    assert gather.attrib["timeout"] == "3"
    assert gather.attrib["actionOnEmptyResult"] == "true"
    assert xml.find("Redirect") is None
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
                twilio_number="+1 (555) 000-1111",
                twilio_number_normalized="5550001111",
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
        To="5550001111",
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
    gather = xml.find("Gather")
    assert gather is not None
    assert gather.attrib["actionOnEmptyResult"] == "true"
    assert xml.find("Redirect") is None
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
    second = _post_voice(
        client,
        CallSid=call_sid,
        From="+15551230000",
        To="+15557654321",
        CallStatus="in-progress",
        SpeechResult="3 pm and my number is 6784624453",
    )
    with db_session() as db:
        assert db.query(AppointmentRequest).count() == 0

    assert "What name should I put on that request?" in second.text

    res = _post_voice(
        client,
        CallSid=call_sid,
        From="+15551230000",
        To="+15557654321",
        CallStatus="in-progress",
        SpeechResult="My name is Jane Smith",
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
        assert slot_data["caller_name"] == "Jane Smith"

        appointment = db.query(AppointmentRequest).one()
        assert appointment.caller_name == "Jane Smith"
        assert appointment.caller_phone == "6784624453"
        assert appointment.requested_time == "Tuesday 3 pm"
        assert appointment.calendar_event_id is None


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
    second = _post_voice(
        client,
        CallSid=call_sid,
        From="+15551230000",
        To="+15557654321",
        CallStatus="in-progress",
        SpeechResult="Use 6784624453",
    )
    with db_session() as db:
        assert db.query(AppointmentRequest).count() == 0

    assert "What name should I put on that callback request?" in second.text

    res = _post_voice(
        client,
        CallSid=call_sid,
        From="+15551230000",
        To="+15557654321",
        CallStatus="in-progress",
        SpeechResult="This is Maya",
    )

    assert res.status_code == 200
    assert "6 7 8, 4 6 2, 4 4 5 3" in res.text

    with db_session() as db:
        session = db.query(CallSession).filter(CallSession.call_sid == call_sid).one()
        slot_data = json.loads(session.slot_data_json)
        assert session.current_intent == "CALLBACK_REQUEST"
        assert session.current_state == "CALLBACK_READY"
        assert slot_data["callback_number"] == "6784624453"
        assert slot_data["caller_name"] == "Maya"

        appointment = db.query(AppointmentRequest).one()
        assert appointment.caller_name == "Maya"
        assert appointment.caller_phone == "6784624453"


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


def test_calls_endpoint_returns_logged_calls(client):
    _post_voice(
        client,
        CallSid="CA-calls-endpoint",
        From="+15551230000",
        To="+15557654321",
        CallStatus="in-progress",
        SpeechResult="What are your hours?",
    )

    res = client.get("/api/calls")

    assert res.status_code == 200
    assert res.json()[0]["call_sid"] == "CA-calls-endpoint"


def test_booking_completion_creates_calendar_event_and_confirms_to_caller(
    client,
    db_session: sessionmaker,
    mock_calendar_booking,
):
    mock_calendar_booking(
        result=SimpleNamespace(
            event_id="evt_123",
            html_link="https://calendar.google.com/event?eid=evt_123",
            scheduled_start=datetime(2026, 4, 7, 15, 0, tzinfo=ZoneInfo("America/New_York")),
            scheduled_end=datetime(2026, 4, 7, 15, 30, tzinfo=ZoneInfo("America/New_York")),
        )
    )
    call_sid = "CA-calendar-success"

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
    _post_voice(
        client,
        CallSid=call_sid,
        From="+15551230000",
        To="+15557654321",
        CallStatus="in-progress",
        SpeechResult="3 pm and my number is 6784624453",
    )
    res = _post_voice(
        client,
        CallSid=call_sid,
        From="+15551230000",
        To="+15557654321",
        CallStatus="in-progress",
        SpeechResult="My name is Jane Smith",
    )

    assert res.status_code == 200
    assert "You're booked for Tuesday at 3 pm." in res.text

    with db_session() as db:
        appointment = db.query(AppointmentRequest).filter(AppointmentRequest.notes == "My name is Jane Smith").one()
        assert appointment.confirmed is True
        assert appointment.calendar_event_id == "evt_123"
        assert appointment.calendar_event_link == "https://calendar.google.com/event?eid=evt_123"
        assert appointment.scheduled_start is not None
        assert appointment.scheduled_end is not None


def test_booking_completion_falls_back_when_calendar_creation_fails(
    client,
    db_session: sessionmaker,
    mock_calendar_booking,
):
    mock_calendar_booking(error=CalendarServiceError("calendar offline"))
    call_sid = "CA-calendar-failure"

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
    _post_voice(
        client,
        CallSid=call_sid,
        From="+15551230000",
        To="+15557654321",
        CallStatus="in-progress",
        SpeechResult="3 pm and my number is 6784624453",
    )
    res = _post_voice(
        client,
        CallSid=call_sid,
        From="+15551230000",
        To="+15557654321",
        CallStatus="in-progress",
        SpeechResult="My name is Jane Smith",
    )

    assert res.status_code == 200
    assert "someone from the office will confirm the appointment shortly" in res.text

    with db_session() as db:
        appointment = db.query(AppointmentRequest).filter(AppointmentRequest.notes == "My name is Jane Smith").one()
        assert appointment.confirmed is False
        assert appointment.calendar_event_id is None
        assert appointment.calendar_event_link is None


def test_booking_completion_blocks_conflicting_calendar_slot(
    client,
    db_session: sessionmaker,
    mock_calendar_booking,
):
    mock_calendar_booking(available=False, suggested_slots=["Tuesday at 4 PM"])
    call_sid = "CA-calendar-conflict"

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
    _post_voice(
        client,
        CallSid=call_sid,
        From="+15551230000",
        To="+15557654321",
        CallStatus="in-progress",
        SpeechResult="3 pm and my number is 6784624453",
    )
    res = _post_voice(
        client,
        CallSid=call_sid,
        From="+15551230000",
        To="+15557654321",
        CallStatus="in-progress",
        SpeechResult="My name is Jane Smith",
    )

    assert res.status_code == 200
    assert "That time looks unavailable. I could offer Tuesday at 4 PM. Would that work?" in res.text

    with db_session() as db:
        appointment = db.query(AppointmentRequest).filter(AppointmentRequest.notes == "My name is Jane Smith").one()
        assert appointment.confirmed is False
        assert appointment.calendar_event_id is None
        assert appointment.calendar_event_link is None


def test_booking_completion_uses_generic_conflict_response_when_no_suggestion(
    client,
    db_session: sessionmaker,
    mock_calendar_booking,
):
    mock_calendar_booking(available=False, suggested_slots=[])
    call_sid = "CA-calendar-conflict-generic"

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
    _post_voice(
        client,
        CallSid=call_sid,
        From="+15551230000",
        To="+15557654321",
        CallStatus="in-progress",
        SpeechResult="3 pm and my number is 6784624453",
    )
    res = _post_voice(
        client,
        CallSid=call_sid,
        From="+15551230000",
        To="+15557654321",
        CallStatus="in-progress",
        SpeechResult="My name is Jane Smith",
    )

    assert res.status_code == 200
    assert "That time looks unavailable. Please suggest another time." in res.text

    with db_session() as db:
        appointment = db.query(AppointmentRequest).filter(AppointmentRequest.notes == "My name is Jane Smith").one()
        assert appointment.confirmed is False


def test_incomplete_booking_does_not_attempt_calendar_creation(client, monkeypatch):
    called = {"value": False}

    def _should_not_run(**_: object):
        called["value"] = True
        raise AssertionError("calendar should not be created for incomplete booking")

    import importlib

    main_module = importlib.import_module("app.main")

    monkeypatch.setattr(main_module.settings, "google_calendar_enabled", True)
    monkeypatch.setattr(main_module, "create_calendar_booking", _should_not_run)
    res = _post_voice(
        client,
        CallSid="CA-calendar-incomplete",
        From="+15551230000",
        To="+15557654321",
        CallStatus="in-progress",
        SpeechResult="I want to book an appointment",
    )

    assert res.status_code == 200
    assert called["value"] is False


def test_booking_completion_falls_back_when_availability_check_fails(
    client,
    db_session: sessionmaker,
    mock_calendar_booking,
):
    mock_calendar_booking(availability_error=CalendarServiceError("calendar offline"))
    call_sid = "CA-calendar-availability-failure"

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
    _post_voice(
        client,
        CallSid=call_sid,
        From="+15551230000",
        To="+15557654321",
        CallStatus="in-progress",
        SpeechResult="3 pm and my number is 6784624453",
    )
    res = _post_voice(
        client,
        CallSid=call_sid,
        From="+15551230000",
        To="+15557654321",
        CallStatus="in-progress",
        SpeechResult="My name is Jane Smith",
    )

    assert res.status_code == 200
    assert "someone from the office will confirm the appointment shortly" in res.text

    with db_session() as db:
        appointment = db.query(AppointmentRequest).filter(AppointmentRequest.notes == "My name is Jane Smith").one()
        assert appointment.confirmed is False
        assert appointment.calendar_event_id is None


def test_booking_completion_handles_unexpected_calendar_error(
    client,
    db_session: sessionmaker,
    mock_calendar_booking,
):
    mock_calendar_booking(error=RuntimeError("boom"))
    call_sid = "CA-calendar-unexpected"

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
    _post_voice(
        client,
        CallSid=call_sid,
        From="+15551230000",
        To="+15557654321",
        CallStatus="in-progress",
        SpeechResult="3 pm and my number is 6784624453",
    )
    res = _post_voice(
        client,
        CallSid=call_sid,
        From="+15551230000",
        To="+15557654321",
        CallStatus="in-progress",
        SpeechResult="My name is Jane Smith",
    )

    assert res.status_code == 200
    assert "someone from the office will confirm the appointment shortly" in res.text

    with db_session() as db:
        appointment = db.query(AppointmentRequest).filter(AppointmentRequest.notes == "My name is Jane Smith").one()
        assert appointment.confirmed is False


def test_voice_silence_turn_reprompts_and_logs_without_redirect(client, db_session: sessionmaker):
    call_sid = "CA-silence-once"

    _post_voice(
        client,
        CallSid=call_sid,
        From="+15551230000",
        To="+15557654321",
        CallStatus="ringing",
    )
    res = _post_voice(
        client,
        CallSid=call_sid,
        From="+15551230000",
        To="+15557654321",
        CallStatus="in-progress",
        SpeechResult="",
    )

    assert res.status_code == 200
    xml = _parse_xml(res.text)
    assert xml.find("Redirect") is None
    assert xml.find("Gather") is not None
    assert "Sorry, I didn't catch that." in res.text

    with db_session() as db:
        session = db.query(CallSession).filter(CallSession.call_sid == call_sid).one()
        slot_data = json.loads(session.slot_data_json)
        assert slot_data["silence_count"] == "1"
        log = db.query(CallLog).filter(CallLog.call_sid == call_sid).order_by(CallLog.id.desc()).first()
        assert log is not None
        assert log.speech_input == ""
        assert "didn't catch that" in log.ai_response


def test_voice_repeated_silence_ends_call_cleanly(client, db_session: sessionmaker):
    call_sid = "CA-silence-end"

    _post_voice(
        client,
        CallSid=call_sid,
        From="+15551230000",
        To="+15557654321",
        CallStatus="ringing",
    )
    _post_voice(
        client,
        CallSid=call_sid,
        From="+15551230000",
        To="+15557654321",
        CallStatus="in-progress",
        SpeechResult="",
    )
    second = _post_voice(
        client,
        CallSid=call_sid,
        From="+15551230000",
        To="+15557654321",
        CallStatus="in-progress",
        SpeechResult="",
    )
    third = _post_voice(
        client,
        CallSid=call_sid,
        From="+15551230000",
        To="+15557654321",
        CallStatus="in-progress",
        SpeechResult="",
    )

    assert "I still didn't hear anything." in second.text
    third_xml = _parse_xml(third.text)
    assert third.status_code == 200
    assert third_xml.find("Gather") is None
    assert third_xml.find("Hangup") is not None
    assert third_xml.find("Redirect") is None
    assert "Thanks for calling. Goodbye." in third.text

    with db_session() as db:
        session = db.query(CallSession).filter(CallSession.call_sid == call_sid).one()
        slot_data = json.loads(session.slot_data_json)
        assert slot_data["silence_count"] == "3"
        assert session.is_active is False
