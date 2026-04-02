from collections.abc import Iterator
import importlib
from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from twilio.request_validator import RequestValidator

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

ai_module = importlib.import_module("app.ai")
calendar_module = importlib.import_module("app.calendar_service")
main_module = importlib.import_module("app.main")
from app.db import Base


@pytest.fixture
def env_overrides(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    original = {
        "openai_api_key": ai_module.settings.openai_api_key,
        "openai_model": ai_module.settings.openai_model,
        "max_call_turns": ai_module.settings.max_call_turns,
        "max_llm_calls_per_session": ai_module.settings.max_llm_calls_per_session,
        "enable_basic_rate_limiting": ai_module.settings.enable_basic_rate_limiting,
        "max_new_calls_per_number_per_hour": ai_module.settings.max_new_calls_per_number_per_hour,
        "google_calendar_enabled": ai_module.settings.google_calendar_enabled,
        "google_calendar_id": ai_module.settings.google_calendar_id,
        "google_client_secrets_file": ai_module.settings.google_client_secrets_file,
        "google_token_file": ai_module.settings.google_token_file,
        "google_oauth_redirect_uri": ai_module.settings.google_oauth_redirect_uri,
        "google_timezone": ai_module.settings.google_timezone,
        "appointment_duration_minutes": ai_module.settings.appointment_duration_minutes,
        "twilio_auth_token": ai_module.settings.twilio_auth_token,
        "disable_twilio_signature_validation": ai_module.settings.disable_twilio_signature_validation,
        "cors_allowed_origins": ai_module.settings.cors_allowed_origins,
    }
    monkeypatch.setattr(ai_module.settings, "openai_api_key", "")
    monkeypatch.setattr(ai_module.settings, "openai_model", "gpt-4o-mini")
    monkeypatch.setattr(ai_module.settings, "max_call_turns", 12)
    monkeypatch.setattr(ai_module.settings, "max_llm_calls_per_session", 6)
    monkeypatch.setattr(ai_module.settings, "enable_basic_rate_limiting", True)
    monkeypatch.setattr(ai_module.settings, "max_new_calls_per_number_per_hour", 5)
    monkeypatch.setattr(ai_module.settings, "google_calendar_enabled", False)
    monkeypatch.setattr(ai_module.settings, "google_calendar_id", "primary")
    monkeypatch.setattr(ai_module.settings, "google_client_secrets_file", "./credentials.json")
    monkeypatch.setattr(ai_module.settings, "google_token_file", "./token.json")
    monkeypatch.setattr(ai_module.settings, "google_oauth_redirect_uri", "")
    monkeypatch.setattr(ai_module.settings, "google_timezone", "America/New_York")
    monkeypatch.setattr(ai_module.settings, "appointment_duration_minutes", 30)
    monkeypatch.setattr(ai_module.settings, "twilio_auth_token", "test-twilio-token")
    monkeypatch.setattr(ai_module.settings, "disable_twilio_signature_validation", True)
    monkeypatch.setattr(
        ai_module.settings,
        "cors_allowed_origins",
        "http://localhost:3000,http://127.0.0.1:3000",
    )
    return original


@pytest.fixture
def db_session(tmp_path: Path) -> Iterator[sessionmaker]:
    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    try:
        yield TestingSessionLocal
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture
def client(db_session: sessionmaker, env_overrides: dict[str, str]) -> Iterator[TestClient]:
    def override_get_db() -> Iterator[sessionmaker]:
        db = db_session()
        try:
            yield db
        finally:
            db.close()

    main_module.app.dependency_overrides[main_module.get_db] = override_get_db
    with TestClient(main_module.app) as test_client:
        yield test_client
    main_module.app.dependency_overrides.clear()


class _FakeOpenAIResponse:
    def __init__(self, content: str):
        self.choices = [type("Choice", (), {"message": type("Message", (), {"content": content})()})()]


class _FakeCompletions:
    def __init__(self, content: str | None = None, error: Exception | None = None):
        self.content = content
        self.error = error

    def create(self, **_: object) -> _FakeOpenAIResponse:
        if self.error is not None:
            raise self.error
        return _FakeOpenAIResponse(self.content or "")


class FakeOpenAIClient:
    def __init__(self, content: str | None = None, error: Exception | None = None):
        self.chat = type("Chat", (), {"completions": _FakeCompletions(content=content, error=error)})()


@pytest.fixture
def mock_openai(monkeypatch: pytest.MonkeyPatch):
    def _apply(*, content: str | None = None, error: Exception | None = None) -> None:
        monkeypatch.setattr(ai_module.settings, "openai_api_key", "test-key")
        monkeypatch.setattr(ai_module, "_get_client", lambda: FakeOpenAIClient(content=content, error=error))

    return _apply


@pytest.fixture
def twilio_signature():
    def _build(url: str, params: dict[str, str]) -> str:
        validator = RequestValidator(ai_module.settings.twilio_auth_token)
        return validator.compute_signature(url, params)

    return _build


@pytest.fixture
def mock_calendar_booking(monkeypatch: pytest.MonkeyPatch):
    def _apply(
        *,
        result=None,
        error: Exception | None = None,
        availability_error: Exception | None = None,
        available: bool = True,
        suggested_slots: list[str] | None = None,
    ):
        monkeypatch.setattr(main_module.settings, "google_calendar_enabled", True)

        def _fake_check_calendar_availability(**_: object):
            if availability_error is not None:
                raise availability_error
            return calendar_module.CalendarAvailabilityResult(
                available=available,
                conflicting_events=[] if available else [{"id": "evt_conflict", "summary": "Booked"}],
                suggested_slots=suggested_slots or [],
            )

        def _fake_create_calendar_booking(**_: object):
            if error is not None:
                raise error
            return result

        monkeypatch.setattr(main_module, "check_calendar_availability", _fake_check_calendar_availability)
        monkeypatch.setattr(main_module, "create_calendar_booking", _fake_create_calendar_booking)

    return _apply
