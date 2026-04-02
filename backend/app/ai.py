import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from openai import OpenAI

from .config import settings

INTENTS = {
    "BOOK_APPOINTMENT",
    "BUSINESS_HOURS",
    "CALLBACK_REQUEST",
    "GENERAL_QUESTION",
}

SAFE_STATES = {
    "NEW",
    "GREETING_SENT",
    "COLLECTING_APPOINTMENT_DAY",
    "COLLECTING_APPOINTMENT_TIME",
    "COLLECTING_CALLBACK_NUMBER",
    "COLLECTING_CALLER_NAME",
    "BOOKING_COMPLETE",
    "CALLBACK_READY",
    "ANSWERED_BUSINESS_HOURS",
    "GENERAL_ASSISTANCE",
    "CALLBACK_REQUEST",
}

PROMPT_FILE_PATH = Path(__file__).with_name("skills") / "receptionist_system_prompt.md"
DEFAULT_SYSTEM_PROMPT_TEMPLATE = (
    "You are the front-desk receptionist for {{business_name}}. "
    "Classify the caller's request into exactly one of these intents: "
    "BOOK_APPOINTMENT, BUSINESS_HOURS, CALLBACK_REQUEST, GENERAL_QUESTION. "
    'Return valid JSON only with this exact shape: {"intent":"...","state":"...","response":"...","fields":{}}. '
    "Keep the response short, phone-friendly, and limited to one or two short sentences. "
    "Business hours are {{business_hours}}. "
    "Booking by phone is {{booking_status}}. "
    "Current session intent is {{session_current_intent}}. "
    "Current session state is {{session_current_state}}. "
    "Current collected slots are {{slot_snapshot}}. "
    "Recent transcript is {{transcript_tail}}. "
    "{{knowledge_section}}"
    "For BOOK_APPOINTMENT, use and preserve collected slots across turns. "
    "Collect appointment_day, appointment_time, callback_number, and caller_name until complete. "
    "Use state values like COLLECTING_APPOINTMENT_DAY, COLLECTING_APPOINTMENT_TIME, COLLECTING_CALLBACK_NUMBER, COLLECTING_CALLER_NAME, or BOOKING_COMPLETE. "
    "For BUSINESS_HOURS, answer directly with the hours. "
    "For CALLBACK_REQUEST, ask for a callback number if missing, then ask for the caller's name if missing, and use states like COLLECTING_CALLBACK_NUMBER, COLLECTING_CALLER_NAME, or CALLBACK_READY. "
    "Treat phone numbers as digit strings, never as numeric quantities. "
    "If you mention a phone number, keep it as digits and do not spell it as a large number. "
    "For GENERAL_QUESTION, use GENERAL_ASSISTANCE. "
    "Do not output markdown or extra text."
)


def _log_ai_mode(message: str) -> None:
    print(f"[ai] {message}", flush=True)


def _load_prompt_template() -> str:
    try:
        content = PROMPT_FILE_PATH.read_text(encoding="utf-8").strip()
    except OSError:
        return DEFAULT_SYSTEM_PROMPT_TEMPLATE
    return content or DEFAULT_SYSTEM_PROMPT_TEMPLATE


def _render_prompt_template(template: str, replacements: dict[str, str]) -> str:
    rendered = template
    for key, value in replacements.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", value)
    return rendered


@dataclass
class ReceptionistResult:
    intent: str
    state: str
    response: str
    fields: dict[str, str]

    def to_json(self) -> str:
        return json.dumps(asdict(self))


@dataclass
class BusinessContext:
    id: int | None = None
    name: str = settings.business_name
    twilio_number: str | None = None
    forwarding_number: str | None = None
    greeting: str = settings.business_greeting
    business_hours: str = settings.business_hours
    booking_enabled: bool = settings.booking_enabled
    knowledge_text: str = ""
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass
class SessionContext:
    call_sid: str | None = None
    current_intent: str = "GENERAL_QUESTION"
    current_state: str = "NEW"
    slot_data: dict[str, str] = field(default_factory=dict)
    transcript: list[dict[str, str]] = field(default_factory=list)


def _get_client() -> OpenAI | None:
    if not settings.openai_api_key:
        return None
    return OpenAI(api_key=settings.openai_api_key)


def _extract_phone_number(user_input: str) -> str | None:
    match = re.search(r"(\+?\d[\d\-\(\) ]{7,}\d)", user_input)
    return match.group(1).strip() if match else None


def _extract_caller_name(user_input: str) -> str | None:
    patterns = [
        r"\bmy name is ([A-Za-z][A-Za-z' -]{0,48})\b",
        r"\bthis is ([A-Za-z][A-Za-z' -]{0,48})\b",
        r"\bi am ([A-Za-z][A-Za-z' -]{0,48})\b",
        r"\bi'm ([A-Za-z][A-Za-z' -]{0,48})\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, user_input, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip(" .,!?:;")
    return None


def format_phone_number_for_speech(phone_number: str) -> str:
    stripped = phone_number.strip()
    has_plus = stripped.startswith("+")
    digits = "".join(char for char in stripped if char.isdigit())

    if not digits:
        return stripped

    if len(digits) == 10:
        groups = (digits[:3], digits[3:6], digits[6:])
        spoken = ", ".join(" ".join(group) for group in groups)
    else:
        spoken = " ".join(digits)

    if has_plus:
        return f"plus {spoken}"
    return spoken


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


def _extract_appointment_day(user_input: str) -> str | None:
    patterns = [
        r"\b(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
        r"\b(?:today|tomorrow|next monday|next tuesday|next wednesday|next thursday|next friday|next saturday|next sunday|next week)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, user_input, flags=re.IGNORECASE)
        if match:
            return match.group(0).strip()
    return None


def _extract_appointment_time(user_input: str) -> str | None:
    match = re.search(r"\b\d{1,2}(?::\d{2})?\s?(?:am|pm)\b", user_input, flags=re.IGNORECASE)
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


def _merge_slot_data(current_slots: dict[str, str], new_fields: dict[str, str]) -> dict[str, str]:
    merged = dict(current_slots)
    for key, value in new_fields.items():
        if value:
            merged[key] = value
    return merged


def _build_booking_response(slot_data: dict[str, str], business: BusinessContext) -> tuple[str, str]:
    if not business.booking_enabled:
        return (
            "CALLBACK_REQUEST",
            "We are not booking appointments by phone right now. What callback number should we use?",
        )

    missing_fields = [
        field_name
        for field_name in ("appointment_day", "appointment_time", "callback_number", "caller_name")
        if not slot_data.get(field_name)
    ]
    if not missing_fields:
        return (
            "BOOKING_COMPLETE",
            "Thanks. I have your day, time, callback number, and name. We will follow up shortly.",
        )
    if missing_fields[0] == "appointment_day":
        return ("COLLECTING_APPOINTMENT_DAY", "Sure, I can help schedule that. What day works for you?")
    if missing_fields[0] == "appointment_time":
        return ("COLLECTING_APPOINTMENT_TIME", "What time works best for you?")
    if missing_fields[0] == "callback_number":
        return ("COLLECTING_CALLBACK_NUMBER", "What callback number should we use?")
    return ("COLLECTING_CALLER_NAME", "What name should I put on that request?")


def _normalize_fields(fields: dict[str, str]) -> dict[str, str]:
    normalized = dict(fields)

    if "requested_time" in normalized and "appointment_day" not in normalized and "appointment_time" not in normalized:
        requested_time = normalized.pop("requested_time")
        day = _extract_appointment_day(requested_time)
        time = _extract_appointment_time(requested_time)
        if day:
            normalized["appointment_day"] = day
        if time:
            normalized["appointment_time"] = time

    alias_map = {
        "day": "appointment_day",
        "date": "appointment_day",
        "time": "appointment_time",
        "phone_number": "callback_number",
        "caller_phone": "callback_number",
        "name": "caller_name",
        "customer_name": "caller_name",
    }
    for source_key, target_key in alias_map.items():
        if source_key in normalized and target_key not in normalized:
            normalized[target_key] = normalized[source_key]

    allowed_keys = {"appointment_day", "appointment_time", "callback_number", "caller_name"}
    cleaned = {key: value.strip() for key, value in normalized.items() if key in allowed_keys and value.strip()}
    return cleaned


def _default_state_for_intent(intent: str, business: BusinessContext, slot_data: dict[str, str]) -> str:
    if intent == "BOOK_APPOINTMENT":
        state, _ = _build_booking_response(slot_data, business)
        return state
    if intent == "BUSINESS_HOURS":
        return "ANSWERED_BUSINESS_HOURS"
    if intent == "CALLBACK_REQUEST":
        if not slot_data.get("callback_number"):
            return "COLLECTING_CALLBACK_NUMBER"
        if not slot_data.get("caller_name"):
            return "COLLECTING_CALLER_NAME"
        return "CALLBACK_READY"
    return "GENERAL_ASSISTANCE"


def _default_response_for_intent(intent: str, business: BusinessContext, slot_data: dict[str, str]) -> str:
    if intent == "BOOK_APPOINTMENT":
        _, response = _build_booking_response(slot_data, business)
        return response
    if intent == "BUSINESS_HOURS":
        return f"Our hours are {business.business_hours}."
    if intent == "CALLBACK_REQUEST":
        if slot_data.get("callback_number") and slot_data.get("caller_name"):
            return "Thanks. We can follow up at that number."
        if slot_data.get("callback_number"):
            return "Thanks. What name should I put on that callback request?"
        return "I can have someone call you back. What number should we use?"
    return "Thanks for calling. How can I help you today?"


def _normalize_intent(intent: object) -> str | None:
    if not isinstance(intent, str):
        return None
    normalized = intent.strip().upper()
    if normalized in INTENTS:
        return normalized
    return None


def _normalize_state(state: object, session: SessionContext, intent: str, business: BusinessContext, slot_data: dict[str, str]) -> str:
    if isinstance(state, str):
        cleaned = state.strip().upper()
        if cleaned in SAFE_STATES:
            if cleaned == "BOOKING_COMPLETE" and not all(
                slot_data.get(key) for key in ("appointment_day", "appointment_time", "callback_number", "caller_name")
            ):
                return _default_state_for_intent(intent, business, slot_data)
            if cleaned == "CALLBACK_READY" and not all(slot_data.get(key) for key in ("callback_number", "caller_name")):
                return _default_state_for_intent(intent, business, slot_data)
            return cleaned
    if session.current_state in SAFE_STATES and session.current_state not in {"NEW", "GREETING_SENT"}:
        return session.current_state
    return _default_state_for_intent(intent, business, slot_data)


def _sanitize_response_text(response: object) -> str:
    if not isinstance(response, str):
        return ""
    cleaned = " ".join(response.split()).strip()
    if not cleaned:
        return ""
    sentences = re.split(r"(?<=[.!?])\s+", cleaned)
    cleaned = " ".join(sentences[:2]).strip()
    if len(cleaned) > 220:
        cleaned = cleaned[:217].rstrip(" ,;:-") + "..."
    return cleaned


def _fallback_result(
    user_input: str,
    business: BusinessContext,
    session: SessionContext,
) -> ReceptionistResult:
    intent = _detect_intent_fallback(user_input)
    if session.current_intent == "BOOK_APPOINTMENT" and session.current_state.startswith("COLLECTING_"):
        intent = "BOOK_APPOINTMENT"
    elif session.current_intent == "CALLBACK_REQUEST" and session.current_state.startswith("COLLECTING_"):
        intent = "CALLBACK_REQUEST"

    fields: dict[str, str] = {}

    phone_number = _extract_phone_number(user_input)
    appointment_day = _extract_appointment_day(user_input)
    appointment_time = _extract_appointment_time(user_input)
    caller_name = _extract_caller_name(user_input)
    stripped_input = user_input.strip(" .,!?:;")

    if not caller_name and session.current_state == "COLLECTING_CALLER_NAME":
        if stripped_input and re.fullmatch(r"[A-Za-z][A-Za-z' -]{0,48}", stripped_input):
            caller_name = stripped_input

    if intent == "BOOK_APPOINTMENT":
        if appointment_day:
            fields["appointment_day"] = appointment_day
        if appointment_time:
            fields["appointment_time"] = appointment_time
        if phone_number:
            fields["callback_number"] = phone_number
        if caller_name:
            fields["caller_name"] = caller_name
        merged_slots = _merge_slot_data(session.slot_data, fields)
        state, response = _build_booking_response(merged_slots, business)
        return ReceptionistResult(intent=intent, state=state, response=response, fields=fields)

    if intent == "BUSINESS_HOURS":
        return ReceptionistResult(
            intent=intent,
            state="ANSWERED_BUSINESS_HOURS",
            response=f"Our hours are {business.business_hours}.",
            fields=fields,
        )

    if intent == "CALLBACK_REQUEST":
        if phone_number:
            fields["callback_number"] = phone_number
        if caller_name:
            fields["caller_name"] = caller_name
        merged_slots = _merge_slot_data(session.slot_data, fields)
        if merged_slots.get("callback_number") and merged_slots.get("caller_name"):
            state = "CALLBACK_READY"
            response = "Thanks. We can follow up at that number."
        elif merged_slots.get("callback_number"):
            state = "COLLECTING_CALLER_NAME"
            response = "Thanks. What name should I put on that callback request?"
        else:
            state = "COLLECTING_CALLBACK_NUMBER"
            response = "I can have someone call you back. What number should we use?"
        return ReceptionistResult(intent=intent, state=state, response=response, fields=fields)

    return ReceptionistResult(
        intent=intent,
        state="GENERAL_ASSISTANCE",
        response="Thanks for calling. How can I help you today?",
        fields=fields,
    )


def _system_prompt(business: BusinessContext, session: SessionContext) -> str:
    booking_status = "enabled" if business.booking_enabled else "disabled"
    knowledge_text = business.knowledge_text.strip()
    knowledge_section = f" Business knowledge: {knowledge_text}." if knowledge_text else ""
    transcript_tail = json.dumps(session.transcript[-6:])
    slot_snapshot = json.dumps(session.slot_data)
    return _render_prompt_template(
        _load_prompt_template(),
        {
            "business_name": business.name,
            "business_hours": business.business_hours,
            "booking_status": booking_status,
            "session_current_intent": session.current_intent,
            "session_current_state": session.current_state,
            "slot_snapshot": slot_snapshot,
            "transcript_tail": transcript_tail,
            "knowledge_section": knowledge_section,
        },
    )


def _coerce_result(
    payload: object,
    user_input: str,
    business: BusinessContext,
    session: SessionContext,
) -> ReceptionistResult:
    if not isinstance(payload, dict):
        return _fallback_result(user_input, business, session)

    fallback = _fallback_result(user_input, business, session)

    normalized_intent = _normalize_intent(payload.get("intent"))
    intent = normalized_intent or fallback.intent
    fields = payload.get("fields")

    if not isinstance(fields, dict):
        fields = {}

    clean_fields = _normalize_fields({str(key): str(value) for key, value in fields.items() if value is not None})
    merged_slots = _merge_slot_data(session.slot_data, clean_fields)
    raw_state = payload.get("state")
    state = _normalize_state(raw_state, session, intent, business, merged_slots)
    response = _sanitize_response_text(payload.get("response"))
    state_valid = isinstance(raw_state, str) and raw_state.strip().upper() in SAFE_STATES

    if not normalized_intent or not state_valid or not response:
        response = _default_response_for_intent(intent, business, merged_slots)

    return ReceptionistResult(
        intent=intent,
        state=state,
        response=response,
        fields=clean_fields,
    )


def detect_and_respond(
    user_input: str,
    business: BusinessContext | None = None,
    session: SessionContext | None = None,
) -> ReceptionistResult:
    business = business or BusinessContext()
    session = session or SessionContext()

    if not user_input:
        _log_ai_mode("mode=fallback reason=empty_input")
        return ReceptionistResult(
            intent="GENERAL_QUESTION",
            state=session.current_state,
            response="Could you please repeat that?",
            fields={},
        )

    client = _get_client()
    if client is None:
        _log_ai_mode("mode=fallback reason=missing_api_key")
        return _fallback_result(user_input, business, session)

    try:
        response = client.chat.completions.create(
            model=settings.openai_model,
            response_format={"type": "json_object"},
            timeout=10.0,
            messages=[
                {"role": "system", "content": _system_prompt(business, session)},
                {"role": "user", "content": user_input},
            ],
            temperature=0.2,
            max_completion_tokens=140,
        )
        content = (response.choices[0].message.content or "").strip()
        if not content:
            _log_ai_mode("mode=fallback reason=empty_model_response")
            return _fallback_result(user_input, business, session)
        result = _coerce_result(json.loads(content), user_input, business, session)
    except Exception as exc:
        _log_ai_mode(f"mode=fallback reason=openai_error error={exc}")
        return _fallback_result(user_input, business, session)

    _log_ai_mode(f"mode=openai model={settings.openai_model} intent={result.intent} state={result.state}")
    return result
