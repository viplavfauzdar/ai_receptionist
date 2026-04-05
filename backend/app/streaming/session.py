from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
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
    current_intent: str = "GENERAL_QUESTION"
    current_state: str = "NEW"
    slot_data: dict[str, str] = field(default_factory=dict)
    transcript: list[dict[str, str]] = field(default_factory=list)
    last_transcript_text: str | None = None
    last_reply_text: str | None = None
    playback_gate_until: datetime | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def record_event(self, event_type: str) -> None:
        self.event_history.append(event_type)
        self.updated_at = datetime.utcnow()

    def append_media_payload(self, payload_b64: str) -> bytes:
        decoded = base64.b64decode(payload_b64)
        self.record_media_chunk(len(decoded))
        self.append_audio_bytes(decoded)
        return decoded

    def flush_audio_buffer(self) -> bytes:
        chunk = bytes(self.audio_buffer)
        self.audio_buffer.clear()
        self.updated_at = datetime.utcnow()
        return chunk

    def record_media_chunk(self, raw_size_bytes: int) -> None:
        self.media_chunk_count += 1
        self.total_audio_bytes += raw_size_bytes
        self.updated_at = datetime.utcnow()

    def append_audio_bytes(self, audio_bytes: bytes) -> None:
        if not audio_bytes:
            return
        self.audio_buffer.extend(audio_bytes)
        self.updated_at = datetime.utcnow()

    def consume_audio_chunk(self, minimum_bytes: int) -> bytes | None:
        if minimum_bytes <= 0 or len(self.audio_buffer) < minimum_bytes:
            return None
        chunk = bytes(self.audio_buffer[:minimum_bytes])
        del self.audio_buffer[:minimum_bytes]
        self.updated_at = datetime.utcnow()
        return chunk

    def clear_audio_buffer(self) -> None:
        self.audio_buffer.clear()
        self.updated_at = datetime.utcnow()

    def activate_playback_gate(self, duration_seconds: float) -> None:
        self.playback_gate_until = datetime.utcnow() + timedelta(seconds=max(duration_seconds, 0))
        self.clear_audio_buffer()
        self.updated_at = datetime.utcnow()

    def is_playback_gate_active(self) -> bool:
        if self.playback_gate_until is None:
            return False
        if datetime.utcnow() >= self.playback_gate_until:
            self.playback_gate_until = None
            return False
        return True


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
