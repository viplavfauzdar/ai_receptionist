from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class RealtimeBridgeSession:
    stream_sid: str = "pending-realtime"
    call_sid: str | None = None
    account_sid: str | None = None
    from_number: str | None = None
    to_number: str | None = None
    openai_session_id: str | None = None
    outbound_audio_active: bool = False
    openai_response_active: bool = False
    outbound_audio_started: bool = False
    first_openai_error_logged: bool = False
    twilio_media_chunks: int = 0
    openai_audio_deltas: int = 0
    clear_messages_sent: int = 0
    call_end_logged: bool = False
    user_said_goodbye: bool = False
    event_history: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def record_event(self, event_type: str) -> None:
        self.event_history.append(event_type)
        self.updated_at = datetime.utcnow()

    def update_from_start(self, start: dict[str, object]) -> None:
        custom_parameters = start.get("customParameters") or {}
        if not isinstance(custom_parameters, dict):
            custom_parameters = {}
        self.stream_sid = str(start.get("streamSid") or self.stream_sid)
        self.call_sid = str(start.get("callSid") or "") or None
        self.account_sid = str(start.get("accountSid") or "") or None
        self.from_number = str(start.get("from") or start.get("caller") or custom_parameters.get("From") or "") or None
        self.to_number = str(start.get("to") or start.get("called") or custom_parameters.get("To") or "") or None
        self.record_event("start")

    def build_twilio_media(self, payload_b64: str) -> dict[str, object]:
        return {
            "event": "media",
            "streamSid": self.stream_sid,
            "media": {"payload": payload_b64},
        }

    def build_twilio_clear(self) -> dict[str, object]:
        self.clear_messages_sent += 1
        return {"event": "clear", "streamSid": self.stream_sid}
