from __future__ import annotations

from typing import Protocol

from .session import AudioFrame, VoiceDuplexSession


class StreamingSTTProvider(Protocol):
    def has_speech(self, audio_bytes: bytes) -> bool:
        ...

    async def transcribe(self, session: VoiceDuplexSession, frame: AudioFrame) -> str | None:
        ...


class StubStreamingSTTProvider:
    def has_speech(self, audio_bytes: bytes) -> bool:
        return any(byte not in {0, 255} for byte in audio_bytes)

    async def transcribe(self, session: VoiceDuplexSession, frame: AudioFrame) -> str | None:
        return None
