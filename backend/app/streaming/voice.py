from __future__ import annotations

from dataclasses import dataclass

from ..ai import BusinessContext, SessionContext, detect_and_respond
from .session import StreamingSession


@dataclass
class StreamingReplyPlan:
    transcript_text: str | None
    reply_text: str | None


def maybe_transcript_to_reply(session: StreamingSession, transcript_text: str | None) -> StreamingReplyPlan:
    session.last_transcript_text = transcript_text
    if not transcript_text:
        return StreamingReplyPlan(transcript_text=None, reply_text=None)

    session.transcript.append({"role": "caller", "text": transcript_text})
    result = detect_and_respond(
        transcript_text,
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
    return StreamingReplyPlan(transcript_text=transcript_text, reply_text=reply_text)
