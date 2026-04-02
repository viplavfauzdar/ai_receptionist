from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
import json
import re
from zoneinfo import ZoneInfo

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow, InstalledAppFlow
from googleapiclient.discovery import build

from .config import settings

SCOPES = ["https://www.googleapis.com/auth/calendar"]


class CalendarServiceError(Exception):
    pass


@dataclass
class CalendarBookingResult:
    event_id: str
    html_link: str | None
    scheduled_start: datetime
    scheduled_end: datetime


@dataclass
class CalendarAvailabilityResult:
    available: bool
    conflicting_events: list[dict[str, str]]
    suggested_slots: list[str]


@dataclass
class GoogleOAuthResult:
    token_json: str
    account_email: str | None


def _resolve_day(appointment_day: str, now: datetime) -> datetime:
    lowered = appointment_day.strip().lower()
    if lowered == "today":
        return now
    if lowered == "tomorrow":
        return now + timedelta(days=1)
    if lowered == "next week":
        return now + timedelta(days=7)

    weekdays = {
        "monday": 0,
        "tuesday": 1,
        "wednesday": 2,
        "thursday": 3,
        "friday": 4,
        "saturday": 5,
        "sunday": 6,
    }
    cleaned = lowered.removeprefix("next ").strip()
    if cleaned not in weekdays:
        raise CalendarServiceError(f"Unsupported appointment_day value: {appointment_day}")

    target_weekday = weekdays[cleaned]
    current_weekday = now.weekday()
    days_ahead = (target_weekday - current_weekday) % 7
    if days_ahead == 0:
        days_ahead = 7
    if lowered.startswith("next "):
        days_ahead += 7 if days_ahead < 7 else 0
    return now + timedelta(days=days_ahead)


def _parse_time(appointment_time: str) -> tuple[int, int]:
    match = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)", appointment_time.strip(), flags=re.IGNORECASE)
    if not match:
        raise CalendarServiceError(f"Unsupported appointment_time value: {appointment_time}")

    hour = int(match.group(1))
    minute = int(match.group(2) or "0")
    meridiem = match.group(3).lower()

    if hour < 1 or hour > 12 or minute > 59:
        raise CalendarServiceError(f"Unsupported appointment_time value: {appointment_time}")

    if meridiem == "pm" and hour != 12:
        hour += 12
    if meridiem == "am" and hour == 12:
        hour = 0
    return hour, minute


def build_appointment_window(
    *,
    appointment_day: str,
    appointment_time: str,
    timezone_str: str,
    duration_minutes: int,
    now: datetime | None = None,
) -> tuple[datetime, datetime]:
    tz = ZoneInfo(timezone_str)
    reference = now.astimezone(tz) if now is not None else datetime.now(tz)
    appointment_date = _resolve_day(appointment_day, reference)
    hour, minute = _parse_time(appointment_time)
    start = appointment_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
    end = start + timedelta(minutes=duration_minutes)
    return start, end


def _load_credentials_from_token_json(token_json: str) -> Credentials:
    payload = json.loads(token_json)
    return Credentials.from_authorized_user_info(payload, SCOPES)


def _load_credentials(token_json: str | None = None) -> Credentials:
    credentials = None

    if token_json:
        credentials = _load_credentials_from_token_json(token_json)
    else:
        token_path = Path(settings.google_token_file)
        if token_path.exists():
            credentials = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if credentials and credentials.valid:
        return credentials

    if credentials and credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
        if token_json is None:
            Path(settings.google_token_file).write_text(credentials.to_json())
        return credentials

    if token_json:
        raise CalendarServiceError("Stored Google Calendar token is not authorized anymore.")

    raise CalendarServiceError(
        "Google Calendar credentials are not authorized yet. Run `python -m app.calendar_service` locally first."
    )


def get_calendar_service(*, token_json: str | None = None):
    credentials = _load_credentials(token_json=token_json)
    return build("calendar", "v3", credentials=credentials)


def _parse_event_datetime(value: str, timezone_str: str) -> datetime:
    if "T" in value:
        return datetime.fromisoformat(value)
    return datetime.fromisoformat(f"{value}T00:00:00").replace(tzinfo=ZoneInfo(timezone_str))


def _events_overlap(existing_start: datetime, existing_end: datetime, requested_start: datetime, requested_end: datetime) -> bool:
    return existing_start < requested_end and requested_start < existing_end


def _format_suggested_slot(start: datetime) -> str:
    formatted_time = start.strftime("%I:%M %p").lstrip("0").replace(":00 ", " ")
    return f"{start.strftime('%A')} at {formatted_time}"


def check_calendar_availability(
    *,
    start: datetime,
    end: datetime,
    token_json: str | None = None,
    calendar_id: str | None = None,
    timezone_str: str | None = None,
) -> CalendarAvailabilityResult:
    service = get_calendar_service(token_json=token_json)
    search_end = end + timedelta(hours=4)
    effective_calendar_id = calendar_id or settings.google_calendar_id
    effective_timezone = timezone_str or settings.google_timezone
    response = (
        service.events()
        .list(
            calendarId=effective_calendar_id,
            timeMin=start.isoformat(),
            timeMax=search_end.isoformat(),
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )

    active_events: list[tuple[datetime, datetime, dict[str, str]]] = []
    conflicts: list[dict[str, str]] = []
    for event in response.get("items", []):
        if event.get("status") == "cancelled":
            continue
        conflict_start = (event.get("start") or {}).get("dateTime") or (event.get("start") or {}).get("date")
        conflict_end = (event.get("end") or {}).get("dateTime") or (event.get("end") or {}).get("date")
        if not conflict_start or not conflict_end:
            continue
        parsed_start = _parse_event_datetime(conflict_start, effective_timezone)
        parsed_end = _parse_event_datetime(conflict_end, effective_timezone)
        event_payload = {
            "id": event.get("id", ""),
            "summary": event.get("summary", ""),
            "start": conflict_start,
            "end": conflict_end,
        }
        active_events.append((parsed_start, parsed_end, event_payload))
        if _events_overlap(parsed_start, parsed_end, start, end):
            conflicts.append(event_payload)

    if not conflicts:
        return CalendarAvailabilityResult(available=True, conflicting_events=[], suggested_slots=[])

    duration = end - start
    candidate_start = start
    candidate_end = end
    for event_start, event_end, _ in sorted(active_events, key=lambda item: item[0]):
        if _events_overlap(event_start, event_end, candidate_start, candidate_end):
            candidate_start = event_end
            candidate_end = candidate_start + duration

    suggested_slots = []
    if candidate_start != start:
        suggested_slots.append(_format_suggested_slot(candidate_start))
    return CalendarAvailabilityResult(available=False, conflicting_events=conflicts, suggested_slots=suggested_slots)


def create_calendar_booking(
    *,
    caller_name: str | None,
    callback_number: str,
    appointment_day: str,
    appointment_time: str,
    notes: str | None,
    token_json: str | None = None,
    calendar_id: str | None = None,
    timezone_str: str | None = None,
) -> CalendarBookingResult:
    effective_timezone = timezone_str or settings.google_timezone
    start, end = build_appointment_window(
        appointment_day=appointment_day,
        appointment_time=appointment_time,
        timezone_str=effective_timezone,
        duration_minutes=settings.appointment_duration_minutes,
    )

    title_name = caller_name or "Caller"
    event_body = {
        "summary": f"Receptionist Appointment: {title_name}",
        "description": "\n".join(
            line
            for line in (
                f"Caller name: {caller_name}" if caller_name else None,
                f"Callback number: {callback_number}",
                "Requested via AI receptionist.",
                f"Notes: {notes}" if notes else None,
            )
            if line
        ),
        "start": {"dateTime": start.isoformat(), "timeZone": effective_timezone},
        "end": {"dateTime": end.isoformat(), "timeZone": effective_timezone},
    }

    service = get_calendar_service(token_json=token_json)
    effective_calendar_id = calendar_id or settings.google_calendar_id
    created = (
        service.events()
        .insert(calendarId=effective_calendar_id, body=event_body)
        .execute()
    )
    return CalendarBookingResult(
        event_id=created["id"],
        html_link=created.get("htmlLink"),
        scheduled_start=start,
        scheduled_end=end,
    )


def _build_oauth_flow(*, redirect_uri: str, state: str | None = None) -> Flow:
    secrets_path = Path(settings.google_client_secrets_file)
    if not secrets_path.exists():
        raise CalendarServiceError(f"Google client secrets file not found: {settings.google_client_secrets_file}")
    flow = Flow.from_client_secrets_file(str(secrets_path), SCOPES, state=state)
    flow.redirect_uri = redirect_uri
    return flow


def create_google_oauth_authorization_url(*, business_id: int, redirect_uri: str) -> str:
    flow = _build_oauth_flow(redirect_uri=redirect_uri, state=str(business_id))
    authorization_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    return authorization_url


def _get_google_account_email(credentials: Credentials) -> str | None:
    try:
        service = build("oauth2", "v2", credentials=credentials)
        profile = service.userinfo().get().execute()
    except Exception:
        return None
    email = profile.get("email")
    return str(email) if email else None


def exchange_google_oauth_code(*, business_id: int, code: str, redirect_uri: str) -> GoogleOAuthResult:
    flow = _build_oauth_flow(redirect_uri=redirect_uri, state=str(business_id))
    flow.fetch_token(code=code)
    credentials = flow.credentials
    return GoogleOAuthResult(
        token_json=credentials.to_json(),
        account_email=_get_google_account_email(credentials),
    )


def list_google_calendars(*, token_json: str) -> list[dict[str, str]]:
    service = get_calendar_service(token_json=token_json)
    response = service.calendarList().list().execute()
    calendars: list[dict[str, str]] = []
    for item in response.get("items", []):
        calendar_id = item.get("id")
        summary = item.get("summary")
        if not calendar_id or not summary:
            continue
        calendars.append(
            {
                "id": str(calendar_id),
                "name": str(summary),
                "primary": "true" if item.get("primary") else "false",
            }
        )
    return calendars


def run_local_oauth_authorization() -> Credentials:
    secrets_path = Path(settings.google_client_secrets_file)
    if not secrets_path.exists():
        raise CalendarServiceError(f"Google client secrets file not found: {settings.google_client_secrets_file}")

    flow = InstalledAppFlow.from_client_secrets_file(str(secrets_path), SCOPES)
    credentials = flow.run_local_server(port=0)
    Path(settings.google_token_file).write_text(credentials.to_json())
    return credentials


def main() -> None:
    credentials = run_local_oauth_authorization()
    payload = json.loads(credentials.to_json())
    print(f"Saved Google Calendar token to {settings.google_token_file}")
    print(f"Authorized Google scopes: {payload.get('scopes')}")


if __name__ == "__main__":
    main()
