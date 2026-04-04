from __future__ import annotations

from dataclasses import dataclass

from .streaming_session import StreamingSession


@dataclass
class StreamingReplyPlan:
    transcript_text: str | None
    reply_text: str | None


def maybe_transcript_to_reply(session: StreamingSession, transcript_text: str | None) -> StreamingReplyPlan:
    session.last_transcript_text = transcript_text
    if not transcript_text:
        return StreamingReplyPlan(transcript_text=None, reply_text=None)

    # Placeholder boundary for future integration:
    # detect_and_respond(transcript_text, business_context, session_context)
    reply_text = f"Experimental streaming placeholder received: {transcript_text}"
    session.last_reply_text = reply_text
    return StreamingReplyPlan(transcript_text=transcript_text, reply_text=reply_text)
