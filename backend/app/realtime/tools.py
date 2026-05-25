from __future__ import annotations

from typing import Any

from .session import RealtimeBridgeSession


REALTIME_TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": "lookup_business",
        "description": "Look up business settings for the called Twilio number.",
        "parameters": {
            "type": "object",
            "properties": {"to_number": {"type": "string"}},
            "required": ["to_number"],
        },
    },
    {
        "type": "function",
        "name": "check_availability",
        "description": "Check whether a requested appointment slot is available.",
        "parameters": {
            "type": "object",
            "properties": {
                "appointment_day": {"type": "string"},
                "appointment_time": {"type": "string"},
            },
            "required": ["appointment_day", "appointment_time"],
        },
    },
    {
        "type": "function",
        "name": "create_booking",
        "description": "Create a booking request once appointment details are complete.",
        "parameters": {
            "type": "object",
            "properties": {
                "caller_name": {"type": "string"},
                "callback_number": {"type": "string"},
                "appointment_day": {"type": "string"},
                "appointment_time": {"type": "string"},
            },
            "required": ["caller_name", "callback_number", "appointment_day", "appointment_time"],
        },
    },
    {
        "type": "function",
        "name": "capture_callback",
        "description": "Capture a callback request when the caller does not book.",
        "parameters": {
            "type": "object",
            "properties": {
                "caller_name": {"type": "string"},
                "callback_number": {"type": "string"},
                "reason": {"type": "string"},
            },
            "required": ["callback_number"],
        },
    },
    {
        "type": "function",
        "name": "log_call_summary",
        "description": "Persist a short call summary after the realtime session ends.",
        "parameters": {
            "type": "object",
            "properties": {"summary": {"type": "string"}},
            "required": ["summary"],
        },
    },
]


async def lookup_business(session: RealtimeBridgeSession, arguments: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "stub",
        "to_number": arguments.get("to_number") or session.to_number,
        "message": "Business lookup is wired as a Realtime tool boundary.",
    }


async def check_availability(session: RealtimeBridgeSession, arguments: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "stub",
        "available": None,
        "message": "Calendar availability will call existing backend logic in a later patch.",
    }


async def create_booking(session: RealtimeBridgeSession, arguments: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "stub",
        "message": "Booking creation will call existing appointment persistence in a later patch.",
    }


async def capture_callback(session: RealtimeBridgeSession, arguments: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "stub",
        "message": "Callback capture will call existing appointment request logic in a later patch.",
    }


async def log_call_summary(session: RealtimeBridgeSession, arguments: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "stub",
        "call_sid": session.call_sid,
        "summary": arguments.get("summary", ""),
    }


REALTIME_TOOL_HANDLERS = {
    "lookup_business": lookup_business,
    "check_availability": check_availability,
    "create_booking": create_booking,
    "capture_callback": capture_callback,
    "log_call_summary": log_call_summary,
}
