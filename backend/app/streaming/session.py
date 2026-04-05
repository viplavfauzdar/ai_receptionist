from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import base64


@dataclass
class StreamingSession:
    stream_sid: str
    call_sid: str | None = None
    account_sid: str | None = None
    from_number: str | None = None
    to_number: str | None = None
    custom_parameters: dict[str, str] = field(default_factory=dict)
    event_history: list[str] = field(default_factory=list)
    media_chunk_count: int = 0
    total_audio_bytes: int = 0
    audio_buffer: bytearray = field(default_factory=bytearray)
    last_transcript_text: str | None = None
    last_reply_text: str | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def record_event(self, event_type: str) -> None:
        self.event_history.append(event_type)
        self.updated_at = datetime.utcnow()

    def append_media_payload(self, payload_b64: str) -> bytes:
        decoded = base64.b64decode(payload_b64)
        self.audio_buffer.extend(decoded)
        self.media_chunk_count += 1
        self.total_audio_bytes += len(decoded)
        self.updated_at = datetime.utcnow()
        return decoded

    def flush_audio_buffer(self) -> bytes:
        chunk = bytes(self.audio_buffer)
        self.audio_buffer.clear()
        self.updated_at = datetime.utcnow()
        return chunk


class StreamingSessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, StreamingSession] = {}

    def create_or_update_start(
        self,
        *,
        stream_sid: str,
        call_sid: str | None,
        account_sid: str | None,
        from_number: str | None,
        to_number: str | None,
        custom_parameters: dict[str, str] | None = None,
    ) -> StreamingSession:
        session = self._sessions.get(stream_sid)
        if session is None:
            session = StreamingSession(stream_sid=stream_sid)
            self._sessions[stream_sid] = session
        session.call_sid = call_sid
        session.account_sid = account_sid
        session.from_number = from_number
        session.to_number = to_number
        session.custom_parameters = dict(custom_parameters or {})
        session.record_event("start")
        return session

    def create_connected_placeholder(self, stream_sid: str) -> StreamingSession:
        session = self._sessions.get(stream_sid)
        if session is None:
            session = StreamingSession(stream_sid=stream_sid)
            self._sessions[stream_sid] = session
        session.record_event("connected")
        return session

    def get(self, stream_sid: str) -> StreamingSession | None:
        return self._sessions.get(stream_sid)

    def remove(self, stream_sid: str) -> StreamingSession | None:
        return self._sessions.pop(stream_sid, None)

    def count(self) -> int:
        return len(self._sessions)
