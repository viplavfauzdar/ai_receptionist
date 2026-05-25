from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class VoiceDuplexState(StrEnum):
    IDLE = "IDLE"
    LISTENING = "LISTENING"
    THINKING = "THINKING"
    SPEAKING = "SPEAKING"
    INTERRUPTED = "INTERRUPTED"


@dataclass
class AudioFrame:
    payload_b64: str
    audio_bytes: bytes
    sequence_number: str | None = None


@dataclass
class VoiceDuplexSession:
    stream_sid: str
    call_sid: str | None = None
    account_sid: str | None = None
    from_number: str | None = None
    to_number: str | None = None
    state: VoiceDuplexState = VoiceDuplexState.IDLE
    audio_queue: asyncio.Queue[AudioFrame | None] = field(default_factory=asyncio.Queue)
    transcript_queue: asyncio.Queue[str | None] = field(default_factory=asyncio.Queue)
    response_queue: asyncio.Queue[str | None] = field(default_factory=asyncio.Queue)
    outbound_queue: asyncio.Queue[dict[str, object] | None] = field(default_factory=asyncio.Queue)
    interruption_queue: asyncio.Queue[str | None] = field(default_factory=asyncio.Queue)
    current_tts_task: asyncio.Task[None] | None = None
    stop_event: asyncio.Event = field(default_factory=asyncio.Event)
    transition_history: list[str] = field(default_factory=lambda: [VoiceDuplexState.IDLE.value])
    media_chunk_count: int = 0
    total_audio_bytes: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def transition(self, next_state: VoiceDuplexState) -> None:
        if self.state == next_state:
            return
        self.state = next_state
        self.transition_history.append(next_state.value)
        self.updated_at = datetime.utcnow()

    def update_start(
        self,
        *,
        stream_sid: str,
        call_sid: str | None,
        account_sid: str | None,
        from_number: str | None,
        to_number: str | None,
    ) -> None:
        self.stream_sid = stream_sid
        self.call_sid = call_sid
        self.account_sid = account_sid
        self.from_number = from_number
        self.to_number = to_number
        self.updated_at = datetime.utcnow()
        self.transition(VoiceDuplexState.LISTENING)

    def record_audio(self, audio_bytes: bytes) -> None:
        self.media_chunk_count += 1
        self.total_audio_bytes += len(audio_bytes)
        self.updated_at = datetime.utcnow()

    def build_clear_message(self) -> dict[str, object]:
        return {"event": "clear", "streamSid": self.stream_sid}

    def build_mark_message(self, mark_name: str) -> dict[str, object]:
        return {
            "event": "mark",
            "streamSid": self.stream_sid,
            "mark": {"name": mark_name},
        }

    def build_media_message(self, payload_b64: str) -> dict[str, object]:
        return {
            "event": "media",
            "streamSid": self.stream_sid,
            "media": {"payload": payload_b64},
        }

    def drain_queues(self) -> None:
        for queue in (
            self.audio_queue,
            self.transcript_queue,
            self.response_queue,
            self.outbound_queue,
            self.interruption_queue,
        ):
            while not queue.empty():
                queue.get_nowait()
                queue.task_done()
