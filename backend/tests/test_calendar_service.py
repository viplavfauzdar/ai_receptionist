from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.calendar_service import (
    CalendarAvailabilityResult,
    CalendarServiceError,
    _load_credentials,
    get_calendar_service,
    build_appointment_window,
    check_calendar_availability,
    create_calendar_booking,
    run_local_oauth_authorization,
)
from app.config import settings


def test_build_appointment_window_resolves_next_weekday(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "google_timezone", "America/New_York")
    start, end = build_appointment_window(
        appointment_day="Tuesday",
        appointment_time="3 pm",
        timezone_str="America/New_York",
        duration_minutes=30,
        now=datetime(2026, 4, 2, 10, 0, tzinfo=ZoneInfo("America/New_York")),
    )

    assert start.isoformat() == "2026-04-07T15:00:00-04:00"
    assert end.isoformat() == "2026-04-07T15:30:00-04:00"


def test_build_appointment_window_rejects_unsupported_time():
    with pytest.raises(CalendarServiceError):
        build_appointment_window(
            appointment_day="Tuesday",
            appointment_time="after lunch",
            timezone_str="America/New_York",
            duration_minutes=30,
            now=datetime(2026, 4, 2, 10, 0, tzinfo=ZoneInfo("America/New_York")),
        )


def test_build_appointment_window_handles_today_and_midnight():
    start, end = build_appointment_window(
        appointment_day="today",
        appointment_time="12:15 am",
        timezone_str="America/New_York",
        duration_minutes=45,
        now=datetime(2026, 4, 2, 10, 0, tzinfo=ZoneInfo("America/New_York")),
    )

    assert start.isoformat() == "2026-04-02T00:15:00-04:00"
    assert end.isoformat() == "2026-04-02T01:00:00-04:00"


def test_build_appointment_window_rejects_unsupported_day():
    with pytest.raises(CalendarServiceError):
        build_appointment_window(
            appointment_day="someday",
            appointment_time="3 pm",
            timezone_str="America/New_York",
            duration_minutes=30,
            now=datetime(2026, 4, 2, 10, 0, tzinfo=ZoneInfo("America/New_York")),
        )


def test_create_calendar_booking_returns_calendar_metadata(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "google_timezone", "America/New_York")
    monkeypatch.setattr(settings, "appointment_duration_minutes", 30)
    monkeypatch.setattr(settings, "google_calendar_id", "primary")
    monkeypatch.setattr(
        "app.calendar_service.build_appointment_window",
        lambda **_: (
            datetime(2026, 4, 7, 15, 0, tzinfo=ZoneInfo("America/New_York")),
            datetime(2026, 4, 7, 15, 30, tzinfo=ZoneInfo("America/New_York")),
        ),
    )

    inserted = {}

    class FakeInsert:
        def execute(self):
            return {"id": "evt_123", "htmlLink": "https://calendar.google.com/event?eid=evt_123"}

    class FakeEvents:
        def insert(self, *, calendarId, body):
            inserted["calendar_id"] = calendarId
            inserted["body"] = body
            return FakeInsert()

    class FakeService:
        def events(self):
            return FakeEvents()

    monkeypatch.setattr("app.calendar_service.get_calendar_service", lambda: FakeService())

    result = create_calendar_booking(
        caller_name="Jane Smith",
        callback_number="6784624453",
        appointment_day="Tuesday",
        appointment_time="3 pm",
        notes="Needs cleaning",
    )

    assert result.event_id == "evt_123"
    assert result.html_link == "https://calendar.google.com/event?eid=evt_123"
    assert inserted["calendar_id"] == "primary"
    assert inserted["body"]["summary"] == "Receptionist Appointment: Jane Smith"
    assert "Callback number: 6784624453" in inserted["body"]["description"]


def test_check_calendar_availability_returns_available_when_no_conflicts(monkeypatch: pytest.MonkeyPatch):
    captured = {}

    class FakeList:
        def execute(self):
            return {"items": []}

    class FakeEvents:
        def list(self, **kwargs):
            captured.update(kwargs)
            return FakeList()

    class FakeService:
        def events(self):
            return FakeEvents()

    monkeypatch.setattr("app.calendar_service.get_calendar_service", lambda: FakeService())
    monkeypatch.setattr(settings, "google_calendar_id", "primary")

    start = datetime(2026, 4, 7, 15, 0, tzinfo=ZoneInfo("America/New_York"))
    end = datetime(2026, 4, 7, 15, 30, tzinfo=ZoneInfo("America/New_York"))
    result = check_calendar_availability(start=start, end=end)

    assert result == CalendarAvailabilityResult(available=True, conflicting_events=[])
    assert captured["calendarId"] == "primary"
    assert captured["timeMin"] == start.isoformat()
    assert captured["timeMax"] == end.isoformat()


def test_check_calendar_availability_blocks_overlapping_events_and_ignores_cancelled(monkeypatch: pytest.MonkeyPatch):
    class FakeList:
        def execute(self):
            return {
                "items": [
                    {
                        "id": "evt_live",
                        "summary": "Existing appointment",
                        "status": "confirmed",
                        "start": {"dateTime": "2026-04-07T15:15:00-04:00"},
                        "end": {"dateTime": "2026-04-07T15:45:00-04:00"},
                    },
                    {
                        "id": "evt_cancelled",
                        "summary": "Cancelled",
                        "status": "cancelled",
                        "start": {"dateTime": "2026-04-07T15:00:00-04:00"},
                        "end": {"dateTime": "2026-04-07T15:30:00-04:00"},
                    },
                ]
            }

    class FakeEvents:
        def list(self, **kwargs):
            return FakeList()

    class FakeService:
        def events(self):
            return FakeEvents()

    monkeypatch.setattr("app.calendar_service.get_calendar_service", lambda: FakeService())

    result = check_calendar_availability(
        start=datetime(2026, 4, 7, 15, 0, tzinfo=ZoneInfo("America/New_York")),
        end=datetime(2026, 4, 7, 15, 30, tzinfo=ZoneInfo("America/New_York")),
    )

    assert result.available is False
    assert result.conflicting_events == [
        {
            "id": "evt_live",
            "summary": "Existing appointment",
            "start": "2026-04-07T15:15:00-04:00",
            "end": "2026-04-07T15:45:00-04:00",
        }
    ]


def test_check_calendar_availability_allows_exact_boundary_gap(monkeypatch: pytest.MonkeyPatch):
    class FakeList:
        def execute(self):
            return {"items": []}

    class FakeEvents:
        def list(self, **kwargs):
            return FakeList()

    class FakeService:
        def events(self):
            return FakeEvents()

    monkeypatch.setattr("app.calendar_service.get_calendar_service", lambda: FakeService())

    result = check_calendar_availability(
        start=datetime(2026, 4, 7, 15, 30, tzinfo=ZoneInfo("America/New_York")),
        end=datetime(2026, 4, 7, 16, 0, tzinfo=ZoneInfo("America/New_York")),
    )

    assert result.available is True


def test_get_calendar_service_uses_loaded_credentials(monkeypatch: pytest.MonkeyPatch):
    fake_credentials = object()
    captured = {}

    monkeypatch.setattr("app.calendar_service._load_credentials", lambda: fake_credentials)
    monkeypatch.setattr(
        "app.calendar_service.build",
        lambda api, version, credentials: captured.update(
            {"api": api, "version": version, "credentials": credentials}
        )
        or "service",
    )

    service = get_calendar_service()

    assert service == "service"
    assert captured == {"api": "calendar", "version": "v3", "credentials": fake_credentials}


def test_load_credentials_raises_when_token_missing(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "google_token_file", "./missing-token.json")

    with pytest.raises(CalendarServiceError):
        _load_credentials()


def test_load_credentials_refreshes_expired_token(monkeypatch: pytest.MonkeyPatch, tmp_path):
    token_path = tmp_path / "token.json"
    token_path.write_text("{}")
    monkeypatch.setattr(settings, "google_token_file", str(token_path))

    class FakeCredentials:
        valid = False
        expired = True
        refresh_token = "refresh-token"

        def refresh(self, request):
            self.valid = True

        def to_json(self):
            return '{"token":"fresh"}'

    monkeypatch.setattr(
        "app.calendar_service.Credentials.from_authorized_user_file",
        lambda path, scopes: FakeCredentials(),
    )

    credentials = _load_credentials()

    assert credentials.valid is True
    assert token_path.read_text() == '{"token":"fresh"}'


def test_run_local_oauth_authorization_requires_client_secrets(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "google_client_secrets_file", "./missing-credentials.json")

    with pytest.raises(CalendarServiceError):
        run_local_oauth_authorization()


def test_run_local_oauth_authorization_writes_token(monkeypatch: pytest.MonkeyPatch, tmp_path):
    secrets_path = tmp_path / "credentials.json"
    token_path = tmp_path / "token.json"
    secrets_path.write_text("{}")
    monkeypatch.setattr(settings, "google_client_secrets_file", str(secrets_path))
    monkeypatch.setattr(settings, "google_token_file", str(token_path))

    class FakeCredentials:
        def to_json(self):
            return '{"scopes":["https://www.googleapis.com/auth/calendar.events"]}'

    class FakeFlow:
        def run_local_server(self, port):
            assert port == 0
            return FakeCredentials()

    monkeypatch.setattr(
        "app.calendar_service.InstalledAppFlow.from_client_secrets_file",
        lambda path, scopes: FakeFlow(),
    )

    credentials = run_local_oauth_authorization()

    assert token_path.exists()
    assert "calendar.events" in token_path.read_text()
    assert credentials.to_json().startswith("{")
