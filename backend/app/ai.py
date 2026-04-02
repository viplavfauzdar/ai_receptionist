import json
import re
from dataclasses import asdict, dataclass

from openai import OpenAI

from .config import settings

INTENTS = {
    "BOOK_APPOINTMENT",
    "BUSINESS_HOURS",
    "CALLBACK_REQUEST",
    "GENERAL_QUESTION",
}


def _log_ai_mode(message: str) -> None:
    print(f"[ai] {message}", flush=True)


@dataclass
class ReceptionistResult:
    intent: str
    response: str
    fields: dict[str, str]

    def to_json(self) -> str:
        return json.dumps(asdict(self))


def _get_client() -> OpenAI | None:
    if not settings.openai_api_key:
        return None
    return OpenAI(api_key=settings.openai_api_key)


def _extract_phone_number(user_input: str) -> str | None:
    match = re.search(r"(\+?\d[\d\-\(\) ]{7,}\d)", user_input)
    return match.group(1).strip() if match else None


def _extract_requested_time(user_input: str) -> str | None:
    patterns = [
        r"\b(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b(?:[^.?!,;]*)",
        r"\b(?:today|tomorrow|next week|next monday|next tuesday|next wednesday|next thursday|next friday)\b(?:[^.?!,;]*)",
        r"\b\d{1,2}(?::\d{2})?\s?(?:am|pm)\b(?:[^.?!,;]*)",
    ]
    for pattern in patterns:
        match = re.search(pattern, user_input, flags=re.IGNORECASE)
        if match:
            return match.group(0).strip()
    return None


def _detect_intent_fallback(user_input: str) -> str:
    lowered = user_input.lower()

    if any(term in lowered for term in ("appointment", "book", "schedule", "reschedule")):
        return "BOOK_APPOINTMENT"
    if any(term in lowered for term in ("hours", "open", "close", "closing time", "what time")):
        return "BUSINESS_HOURS"
    if any(term in lowered for term in ("call me", "callback", "call back", "reach me", "give me a call")):
        return "CALLBACK_REQUEST"
    return "GENERAL_QUESTION"


def _fallback_result(user_input: str) -> ReceptionistResult:
    intent = _detect_intent_fallback(user_input)
    fields: dict[str, str] = {}

    phone_number = _extract_phone_number(user_input)
    requested_time = _extract_requested_time(user_input)

    if intent == "BOOK_APPOINTMENT":
        if requested_time:
            fields["requested_time"] = requested_time
        if phone_number:
            fields["callback_number"] = phone_number
        if settings.booking_enabled:
            response = "Sure, I can help schedule that. What day and time works for you?"
            if requested_time:
                response = "Sure, I can help schedule that. What callback number should we use?"
        else:
            response = "We are not booking appointments by phone right now. What callback number should we use?"
        return ReceptionistResult(intent=intent, response=response, fields=fields)

    if intent == "BUSINESS_HOURS":
        return ReceptionistResult(
            intent=intent,
            response=f"Our hours are {settings.business_hours}.",
            fields=fields,
        )

    if intent == "CALLBACK_REQUEST":
        if phone_number:
            fields["callback_number"] = phone_number
            response = "Thanks. We can follow up at that number."
        else:
            response = "I can have someone call you back. What number should we use?"
        return ReceptionistResult(intent=intent, response=response, fields=fields)

    return ReceptionistResult(
        intent=intent,
        response="Thanks for calling. How can I help you today?",
        fields=fields,
    )


def _system_prompt() -> str:
    booking_status = "enabled" if settings.booking_enabled else "disabled"
    return (
        f"You are the front-desk receptionist for {settings.business_name}. "
        "Classify the caller's request into exactly one of these intents: "
        "BOOK_APPOINTMENT, BUSINESS_HOURS, CALLBACK_REQUEST, GENERAL_QUESTION. "
        "Return valid JSON only with this exact shape: "
        '{"intent":"...","response":"...","fields":{}}. '
        "Keep the response short, phone-friendly, and limited to one or two short sentences. "
        f"Business hours are {settings.business_hours}. "
        f"Booking by phone is {booking_status}. "
        "For BOOK_APPOINTMENT, ask for day/time or callback number if missing. "
        "For BUSINESS_HOURS, answer directly with the hours. "
        "For CALLBACK_REQUEST, ask for a callback number if missing. "
        "Do not output markdown or extra text."
    )


def _coerce_result(payload: object, user_input: str) -> ReceptionistResult:
    if not isinstance(payload, dict):
        return _fallback_result(user_input)

    intent = payload.get("intent")
    response = payload.get("response")
    fields = payload.get("fields")

    if intent not in INTENTS or not isinstance(response, str) or not response.strip():
        return _fallback_result(user_input)

    if not isinstance(fields, dict):
        fields = {}

    clean_fields = {str(key): str(value) for key, value in fields.items() if value is not None}
    return ReceptionistResult(intent=intent, response=" ".join(response.split()), fields=clean_fields)


def detect_and_respond(user_input: str) -> ReceptionistResult:
    if not user_input:
        _log_ai_mode("mode=fallback reason=empty_input")
        return ReceptionistResult(
            intent="GENERAL_QUESTION",
            response="Could you please repeat that?",
            fields={},
        )

    client = _get_client()
    if client is None:
        _log_ai_mode("mode=fallback reason=missing_api_key")
        return _fallback_result(user_input)

    try:
        response = client.chat.completions.create(
            model=settings.openai_model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _system_prompt()},
                {"role": "user", "content": user_input},
            ],
            temperature=0.2,
            max_tokens=140,
        )
        content = (response.choices[0].message.content or "").strip()
        if not content:
            _log_ai_mode("mode=fallback reason=empty_model_response")
            return _fallback_result(user_input)
        result = _coerce_result(json.loads(content), user_input)
    except Exception as exc:
        _log_ai_mode(f"mode=fallback reason=openai_error error={exc}")
        return _fallback_result(user_input)

    _log_ai_mode(f"mode=openai model={settings.openai_model} intent={result.intent}")
    return result
