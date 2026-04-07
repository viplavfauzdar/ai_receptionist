from __future__ import annotations

from dataclasses import dataclass

from ..ai import (
    BusinessContext,
    ReceptionistResult,
    SessionContext,
    detect_and_respond,
    extract_phone_digits_fragment,
    normalize_us_phone_number,
)
from .session import StreamingSession


@dataclass
class StreamingReplyPlan:
    transcript_text: str | None
    intent: str | None
    reply_text: str | None
    fallback_used: bool


def _log_streaming_voice(message: str) -> None:
    print(f"[streaming-voice] {message}", flush=True)


def _state_specific_reprompt(state: str) -> str:
    if state == "COLLECTING_APPOINTMENT_DAY":
        return "I didn't catch the day. You can say something like Thursday or tomorrow."
    if state == "COLLECTING_APPOINTMENT_TIME":
        return "I didn't catch the time. You can say something like 3 PM."
    if state == "COLLECTING_CALLBACK_NUMBER":
        return "I didn't catch the number. You can say it digit by digit, like 678 462 4453."
    if state == "COLLECTING_CALLER_NAME":
        return "I didn't catch the name. Please say your first and last name."
    return "Sorry, I didn't catch that. Could you say that again?"


def _apply_repetition_guard(session: StreamingSession, state_before: str, state_after: str, reply_text: str) -> str:
    if state_after != state_before:
        return reply_text
    if state_after not in {
        "COLLECTING_APPOINTMENT_DAY",
        "COLLECTING_APPOINTMENT_TIME",
        "COLLECTING_CALLBACK_NUMBER",
        "COLLECTING_CALLER_NAME",
    }:
        return reply_text
    if session.last_reply_text != reply_text:
        return reply_text
    return _state_specific_reprompt(state_after)


def _handle_streaming_callback_digits(
    session: StreamingSession,
    transcript_text: str,
) -> ReceptionistResult | None:
    if session.current_state != "COLLECTING_CALLBACK_NUMBER":
        return None
    extracted_digits = extract_phone_digits_fragment(transcript_text)
    if not extracted_digits:
        return None

    digit_buffer = f"{session.digit_buffer}{extracted_digits}"
    normalized_number = normalize_us_phone_number(digit_buffer)
    if normalized_number:
        return detect_and_respond(
            normalized_number,
            business=BusinessContext(),
            session=SessionContext(
                call_sid=session.call_sid,
                current_intent=session.current_intent,
                current_state=session.current_state,
                slot_data=dict(session.slot_data),
                transcript=list(session.transcript),
            ),
            force_fallback_reason="streaming_experimental_path",
        )

    session.digit_buffer = digit_buffer[:11]
    _log_streaming_voice(
        f"transcript={transcript_text!r} state_before={session.current_state} "
        f"extracted_digits={extracted_digits!r} digit_buffer={session.digit_buffer!r} "
        f"state_after={session.current_state}"
    )
    return ReceptionistResult(
        intent=session.current_intent or "BOOK_APPOINTMENT",
        state="COLLECTING_CALLBACK_NUMBER",
        response="What callback number should we use?",
        fields={},
    )


def maybe_transcript_to_reply(session: StreamingSession, transcript_text: str | None) -> StreamingReplyPlan:
    normalized_transcript = " ".join((transcript_text or "").split()).strip()
    session.last_transcript_text = normalized_transcript or None
    state_before = session.current_state
    if not normalized_transcript:
        reply_text = _state_specific_reprompt(state_before)
        session.last_reply_text = reply_text
        _log_streaming_voice(
            f"transcript={normalized_transcript!r} state_before={state_before} "
            f"extracted_fields={{}} state_after={state_before} reply={reply_text!r}"
        )
        return StreamingReplyPlan(
            transcript_text=None,
            intent="GENERAL_QUESTION",
            reply_text=reply_text,
            fallback_used=True,
        )

    session.transcript.append({"role": "caller", "text": normalized_transcript})
    result = _handle_streaming_callback_digits(session, normalized_transcript)
    if result is None:
        result = detect_and_respond(
            normalized_transcript,
            business=BusinessContext(),
            session=SessionContext(
                call_sid=session.call_sid,
                current_intent=session.current_intent,
                current_state=session.current_state,
                slot_data=dict(session.slot_data),
                transcript=list(session.transcript),
            ),
            force_fallback_reason="streaming_experimental_path",
        )
    state_after = result.state
    slot_data_after_merge = dict(session.slot_data)
    slot_data_after_merge.update(result.fields)
    reply_text = _apply_repetition_guard(session, state_before, state_after, result.response)
    session.current_intent = result.intent
    session.current_state = state_after
    session.slot_data.update(result.fields)
    if result.fields.get("callback_number") or state_after != "COLLECTING_CALLBACK_NUMBER":
        session.digit_buffer = ""
    session.transcript.append({"role": "assistant", "text": reply_text})
    session.last_reply_text = reply_text
    _log_streaming_voice(
        f"transcript={normalized_transcript!r} state_before={state_before} "
        f"extracted_fields={result.fields} digit_buffer={session.digit_buffer!r} "
        f"slot_data_after_merge={slot_data_after_merge} "
        f"state_after={state_after} reply={reply_text!r}"
    )
    return StreamingReplyPlan(
        transcript_text=normalized_transcript,
        intent=result.intent,
        reply_text=reply_text,
        fallback_used=True,
    )
