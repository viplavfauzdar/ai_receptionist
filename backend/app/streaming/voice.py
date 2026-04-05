from __future__ import annotations

from dataclasses import dataclass

from ..ai import BusinessContext, SessionContext, detect_and_respond
from .session import StreamingSession


@dataclass
class StreamingReplyPlan:
    transcript_text: str | None
    intent: str | None
    reply_text: str | None
    fallback_used: bool


def maybe_transcript_to_reply(session: StreamingSession, transcript_text: str | None) -> StreamingReplyPlan:
    normalized_transcript = " ".join((transcript_text or "").split()).strip()
    session.last_transcript_text = normalized_transcript or None
    if not normalized_transcript:
        reply_text = "Sorry, I didn't catch that. Could you say that again?"
        session.last_reply_text = reply_text
        return StreamingReplyPlan(
            transcript_text=None,
            intent="GENERAL_QUESTION",
            reply_text=reply_text,
            fallback_used=True,
        )

    session.transcript.append({"role": "caller", "text": normalized_transcript})
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
    session.current_intent = result.intent
    session.current_state = result.state
    session.slot_data.update(result.fields)
    reply_text = result.response
    session.transcript.append({"role": "assistant", "text": reply_text})
    session.last_reply_text = reply_text
    return StreamingReplyPlan(
        transcript_text=normalized_transcript,
        intent=result.intent,
        reply_text=reply_text,
        fallback_used=True,
    )
