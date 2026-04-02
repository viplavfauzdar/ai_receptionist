from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
import json
import re
from zoneinfo import ZoneInfo

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from .config import settings

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]


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


def _load_credentials() -> Credentials:
    token_path = Path(settings.google_token_file)
    credentials = None

    if token_path.exists():
        credentials = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if credentials and credentials.valid:
        return credentials

    if credentials and credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
        token_path.write_text(credentials.to_json())
        return credentials

    raise CalendarServiceError(
        "Google Calendar credentials are not authorized yet. Run `python -m app.calendar_service` locally first."
    )


def get_calendar_service():
    credentials = _load_credentials()
    return build("calendar", "v3", credentials=credentials)


def check_calendar_availability(*, start: datetime, end: datetime) -> CalendarAvailabilityResult:
    service = get_calendar_service()
    response = (
        service.events()
        .list(
            calendarId=settings.google_calendar_id,
            timeMin=start.isoformat(),
            timeMax=end.isoformat(),
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )

    conflicts: list[dict[str, str]] = []
    for event in response.get("items", []):
        if event.get("status") == "cancelled":
            continue
        conflict_start = (event.get("start") or {}).get("dateTime") or (event.get("start") or {}).get("date")
        conflict_end = (event.get("end") or {}).get("dateTime") or (event.get("end") or {}).get("date")
        conflicts.append(
            {
                "id": event.get("id", ""),
                "summary": event.get("summary", ""),
                "start": conflict_start or "",
                "end": conflict_end or "",
            }
        )
    return CalendarAvailabilityResult(available=not conflicts, conflicting_events=conflicts)


def create_calendar_booking(
    *,
    caller_name: str | None,
    callback_number: str,
    appointment_day: str,
    appointment_time: str,
    notes: str | None,
) -> CalendarBookingResult:
    start, end = build_appointment_window(
        appointment_day=appointment_day,
        appointment_time=appointment_time,
        timezone_str=settings.google_timezone,
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
                f"Requested via AI receptionist.",
                f"Notes: {notes}" if notes else None,
            )
            if line
        ),
        "start": {"dateTime": start.isoformat(), "timeZone": settings.google_timezone},
        "end": {"dateTime": end.isoformat(), "timeZone": settings.google_timezone},
    }

    service = get_calendar_service()
    created = (
        service.events()
        .insert(calendarId=settings.google_calendar_id, body=event_body)
        .execute()
    )
    return CalendarBookingResult(
        event_id=created["id"],
        html_link=created.get("htmlLink"),
        scheduled_start=start,
        scheduled_end=end,
    )


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
    print(f"Scopes: {payload.get('scopes', [])}")


if __name__ == "__main__":
    main()
