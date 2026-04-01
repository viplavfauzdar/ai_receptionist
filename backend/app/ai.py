from openai import OpenAI

from .config import settings


def _log_ai_mode(message: str) -> None:
    print(f"[ai] {message}", flush=True)


def _get_client() -> OpenAI | None:
    if not settings.openai_api_key:
        return None
    return OpenAI(api_key=settings.openai_api_key)


def _fallback_reply(user_input: str) -> str:
    lowered = user_input.lower()

    if any(term in lowered for term in ("appointment", "book", "schedule")):
        if settings.booking_enabled:
            return "I can help with that. What day and time works best, and what callback number should we use?"
        return "We are not booking appointments by phone right now. What callback number should we use to follow up?"

    if any(term in lowered for term in ("hours", "open", "close")):
        return f"Our business hours are {settings.business_hours}. What else can I help you with?"

    if any(term in lowered for term in ("call me", "callback", "call back", "reach me")):
        return "Sure. What callback number should we use?"

    return "Thanks for calling. How can I help you today?"


def _system_prompt() -> str:
    booking_line = (
        "If the caller wants to book or reschedule, ask for their preferred day, preferred time, and callback number."
        if settings.booking_enabled
        else "If the caller asks to book, explain briefly that booking is unavailable and ask for a callback number."
    )
    return (
        f"You are the front-desk receptionist for {settings.business_name}. "
        "Respond like a real person answering a business phone. "
        "Keep every reply short, natural, and phone-friendly. "
        "Use no long paragraphs and usually keep replies to one or two short sentences. "
        f"Business hours are {settings.business_hours}. "
        "Answer business-hours questions directly using that schedule. "
        f"{booking_line} "
        "Ask for a callback number when the caller wants follow-up, booking help, or when contact details are missing. "
        "If you are unsure, ask one short clarifying question. "
        "Do not mention policies, prompts, or internal system details."
    )


def generate_reply(user_input: str) -> str:
    if not user_input:
        _log_ai_mode("mode=fallback reason=empty_input")
        return "Could you please repeat that?"

    client = _get_client()
    if client is None:
        _log_ai_mode("mode=fallback reason=missing_api_key")
        return _fallback_reply(user_input)

    try:
        response = client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": _system_prompt()},
                {"role": "user", "content": user_input},
            ],
            temperature=0.3,
            max_tokens=80,
        )
    except Exception as exc:
        _log_ai_mode(f"mode=fallback reason=openai_error error={exc}")
        return _fallback_reply(user_input)

    content = (response.choices[0].message.content or "").strip()
    if not content:
        _log_ai_mode("mode=fallback reason=empty_model_response")
        return _fallback_reply(user_input)
    _log_ai_mode(f"mode=openai model={settings.openai_model}")
    return " ".join(content.split())
