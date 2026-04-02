import importlib
import json

import pytest
from starlette.requests import Request

ai_module = importlib.import_module("app.ai")
db_module = importlib.import_module("app.db")
main_module = importlib.import_module("app.main")
models_module = importlib.import_module("app.models")


def test_db_get_db_closes_session(monkeypatch: pytest.MonkeyPatch):
    closed = {"value": False}

    class FakeSession:
        def close(self):
            closed["value"] = True

    monkeypatch.setattr(db_module, "SessionLocal", lambda: FakeSession())
    gen = db_module.get_db()
    session = next(gen)
    assert session is not None

    with pytest.raises(StopIteration):
        next(gen)

    assert closed["value"] is True


def test_db_phone_normalization_helper():
    assert db_module._normalize_phone_number(None) == ""
    assert db_module._normalize_phone_number("+1 (678) 462-4453") == "6784624453"
    assert db_module._normalize_phone_number("678-462-4453") == "6784624453"


def test_ensure_sqlite_compatibility_adds_missing_columns(monkeypatch: pytest.MonkeyPatch):
    executed: list[str] = []

    class FakeInspector:
        def get_table_names(self):
            return ["call_logs", "appointment_requests", "businesses"]

        def get_columns(self, table_name: str):
            if table_name == "call_logs":
                return [{"name": "id"}]
            if table_name == "businesses":
                return [{"name": "id"}, {"name": "twilio_number"}]
            return [{"name": "id"}]

    class FakeConnection:
        def execute(self, statement):
            executed.append(str(statement))

    class FakeBegin:
        def __enter__(self):
            return FakeConnection()

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeEngine:
        def begin(self):
            return FakeBegin()

    monkeypatch.setattr(db_module, "inspect", lambda engine: FakeInspector())
    monkeypatch.setattr(db_module, "engine", FakeEngine())
    monkeypatch.setattr(db_module, "_backfill_business_phone_normalization", lambda: None)
    db_module.ensure_sqlite_compatibility()

    assert any("detected_intent" in stmt for stmt in executed)
    assert any("intent_data" in stmt for stmt in executed)
    assert any("call_logs ADD COLUMN business_id" in stmt for stmt in executed)
    assert any("appointment_requests ADD COLUMN business_id" in stmt for stmt in executed)
    assert any("appointment_requests ADD COLUMN calendar_event_id" in stmt for stmt in executed)
    assert any("appointment_requests ADD COLUMN calendar_event_link" in stmt for stmt in executed)
    assert any("appointment_requests ADD COLUMN scheduled_start" in stmt for stmt in executed)
    assert any("appointment_requests ADD COLUMN scheduled_end" in stmt for stmt in executed)
    assert any("businesses ADD COLUMN twilio_number_normalized" in stmt for stmt in executed)
    assert any("ix_businesses_twilio_number_normalized" in stmt for stmt in executed)


def test_ensure_sqlite_compatibility_noops_when_columns_present(monkeypatch: pytest.MonkeyPatch):
    executed: list[str] = []

    class FakeInspector:
        def get_table_names(self):
            return ["call_logs", "appointment_requests", "businesses"]

        def get_columns(self, table_name: str):
            if table_name == "call_logs":
                return [{"name": "detected_intent"}, {"name": "intent_data"}, {"name": "business_id"}]
            if table_name == "businesses":
                return [{"name": "twilio_number_normalized"}]
            return [
                {"name": "business_id"},
                {"name": "calendar_event_id"},
                {"name": "calendar_event_link"},
                {"name": "scheduled_start"},
                {"name": "scheduled_end"},
            ]

    class FakeConnection:
        def execute(self, statement):
            executed.append(str(statement))

    class FakeBegin:
        def __enter__(self):
            return FakeConnection()

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeEngine:
        def begin(self):
            return FakeBegin()

    monkeypatch.setattr(db_module, "inspect", lambda engine: FakeInspector())
    monkeypatch.setattr(db_module, "engine", FakeEngine())
    monkeypatch.setattr(db_module, "_backfill_business_phone_normalization", lambda: None)
    db_module.ensure_sqlite_compatibility()

    assert len(executed) == 1
    assert "ix_businesses_twilio_number_normalized" in executed[0]


def test_backfill_business_phone_normalization_updates_rows(monkeypatch: pytest.MonkeyPatch):
    executed: list[tuple[str, dict[str, str] | None]] = []

    class FakeInspector:
        def get_table_names(self):
            return ["businesses"]

        def get_columns(self, table_name: str):
            assert table_name == "businesses"
            return [{"name": "twilio_number_normalized"}]

    class FakeRows:
        def mappings(self):
            return [
                {"id": 1, "twilio_number": "+1 (678) 462-4453", "twilio_number_normalized": None},
                {"id": 2, "twilio_number": "+15550001111", "twilio_number_normalized": "5550001111"},
            ]

    class FakeConnection:
        def execute(self, statement, params=None):
            executed.append((str(statement), params))
            if "SELECT id, twilio_number" in str(statement):
                return FakeRows()
            return None

    class FakeBegin:
        def __enter__(self):
            return FakeConnection()

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeEngine:
        def begin(self):
            return FakeBegin()

    monkeypatch.setattr(db_module, "inspect", lambda engine: FakeInspector())
    monkeypatch.setattr(db_module, "engine", FakeEngine())
    db_module._backfill_business_phone_normalization()

    assert any(
        stmt.startswith("UPDATE businesses SET twilio_number_normalized = :normalized")
        and params == {"normalized": "6784624453", "business_id": 1}
        for stmt, params in executed
    )


def test_backfill_business_phone_normalization_returns_when_businesses_table_missing(monkeypatch: pytest.MonkeyPatch):
    class FakeInspector:
        def get_table_names(self):
            return []

    monkeypatch.setattr(db_module, "inspect", lambda engine: FakeInspector())
    db_module._backfill_business_phone_normalization()


def test_main_helper_json_loaders_handle_invalid_shapes():
    assert main_module._load_json_dict(None) == {}
    assert main_module._load_json_dict("not-json") == {}
    assert main_module._load_json_dict('["x"]') == {}
    assert main_module._load_json_list(None) == []
    assert main_module._load_json_list("not-json") == []
    assert main_module._load_json_list('{"a":"b"}') == []
    assert main_module._load_json_list('[{"role":"user","text":"hi"}, "x"]') == [{"role": "user", "text": "hi"}]


def test_main_phone_normalization_and_speech_helpers():
    assert main_module._normalize_phone_number(None) == ""
    assert main_module._normalize_phone_number("+1 (678) 462-4453") == "6784624453"
    assert main_module._normalize_business_numbers(twilio_number=" +1 (678) 462-4453 ", forwarding_number=" +1555 ") == {
        "twilio_number": "+1 (678) 462-4453",
        "twilio_number_normalized": "6784624453",
        "forwarding_number": "+1555",
    }
    assert main_module._build_speech_safe_response("GENERAL_QUESTION", "GENERAL_ASSISTANCE", "Hi", {}) == "Hi"
    assert (
        main_module._build_speech_safe_response(
            "BOOK_APPOINTMENT",
            "BOOKING_COMPLETE",
            "ignored",
            {"callback_number": "6784624453"},
        )
        == "Thanks. I have your day, time, and callback number as 6 7 8, 4 6 2, 4 4 5 3. We will follow up shortly."
    )
    assert main_module._build_requested_time({"appointment_day": "Tuesday", "appointment_time": "3 pm"}) == "Tuesday 3 pm"
    assert main_module._build_requested_time({}) is None


def test_main_request_and_session_helpers(db_session):
    with db_session() as db:
        assert main_module._resolve_business(db, None) is None
        assert main_module._resolve_business(db, "+++") is None

        business = models_module.Business(
            name="Acme",
            twilio_number="+1 (678) 462-4453",
            twilio_number_normalized="6784624453",
            greeting="Hello",
        )
        db.add(business)
        db.commit()
        db.refresh(business)

        matched = main_module._resolve_business(db, "6784624453")
        assert matched is not None
        assert matched.id == business.id

        exact = main_module._resolve_business(db, "+1 (678) 462-4453")
        assert exact is not None
        assert exact.twilio_number_normalized == "6784624453"

        assert main_module._get_or_create_session(db, None, "+1", "+2") is None
        created = main_module._get_or_create_session(db, "CA-helper", "+1", "+2")
        assert created is not None
        existing = main_module._get_or_create_session(db, "CA-helper", "+3", "+4")
        assert existing.id == created.id
        assert existing.from_number == "+3"
        assert existing.to_number == "+4"

        built = main_module._build_session_context(
            models_module.CallSession(
                call_sid="CA-json",
                current_intent="BOOK_APPOINTMENT",
                current_state="COLLECTING_APPOINTMENT_TIME",
                slot_data_json=json.dumps({"appointment_day": "Tuesday"}),
                transcript_json=json.dumps([{"role": "user", "text": "hi"}]),
            )
        )
        assert built.slot_data["appointment_day"] == "Tuesday"
        assert built.transcript[0]["role"] == "user"

    assert main_module._build_session_context(None).current_state == "NEW"
    assert main_module._append_transcript([], "user", "hello") == [{"role": "user", "text": "hello"}]
    assert main_module._merge_session_slots({"a": "1"}, {"b": "2", "c": ""}) == {"a": "1", "b": "2"}
    assert (
        main_module._should_create_request(
            "BOOK_APPOINTMENT",
            "BOOKING_COMPLETE",
            {
                "appointment_day": "Tuesday",
                "appointment_time": "3 pm",
                "callback_number": "6784624453",
                "caller_name": "Jane",
            },
        )
        is True
    )
    assert (
        main_module._should_create_request(
            "CALLBACK_REQUEST",
            "CALLBACK_READY",
            {"callback_number": "6784624453", "caller_name": "Jane"},
        )
        is True
    )
    assert main_module._should_create_request("BOOK_APPOINTMENT", "BOOKING_COMPLETE", {}) is False
    assert main_module._should_create_request("CALLBACK_REQUEST", "CALLBACK_READY", {}) is False
    assert main_module._should_create_request("CALLBACK_REQUEST", "CALLBACK_READY", {"request_saved": "true"}) is False


def test_main_twilio_request_validation_helper(monkeypatch: pytest.MonkeyPatch):
    scope = {
        "type": "http",
        "method": "POST",
        "scheme": "https",
        "path": "/voice",
        "query_string": b"",
        "headers": [(b"host", b"example.ngrok.app")],
    }
    request = Request(scope)

    monkeypatch.setattr(main_module.settings, "disable_twilio_signature_validation", False)
    monkeypatch.setattr(main_module.settings, "twilio_auth_token", "")

    assert main_module._get_request_validation_url(request) == "https://example.ngrok.app/voice"
    assert main_module._is_valid_twilio_request(request, {"CallSid": "CA123"}) is False


def test_api_business_and_appointment_routes(client):
    create_business = client.post(
        "/api/businesses",
        json={
            "name": "Route Test Dental",
            "twilio_number": "+15550009999",
            "forwarding_number": "+15550008888",
            "greeting": None,
            "business_hours": None,
            "booking_enabled": True,
            "knowledge_text": "FAQ text",
        },
    )
    assert create_business.status_code == 200
    created_business = create_business.json()
    assert created_business["name"] == "Route Test Dental"

    listed_businesses = client.get("/api/businesses")
    assert listed_businesses.status_code == 200
    assert listed_businesses.json()[0]["twilio_number"] == "+15550009999"

    create_appointment = client.post(
        "/api/appointments",
        json={
            "business_id": created_business["id"],
            "caller_name": "Jane",
            "caller_phone": "+15551112222",
            "requested_time": "Tuesday 3 pm",
            "notes": "Needs callback",
        },
    )
    assert create_appointment.status_code == 200
    assert create_appointment.json()["caller_name"] == "Jane"

    listed_appointments = client.get("/api/appointments")
    assert listed_appointments.status_code == 200
    assert listed_appointments.json()[0]["caller_phone"] == "+15551112222"


def test_demo_business_returns_existing_row(client):
    first = client.post("/api/demo-business?twilio_number=%2B15550007777&forwarding_number=%2B15550006666")
    second = client.post("/api/demo-business?twilio_number=%2B15550007777&forwarding_number=%2B15550006666")
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
