from __future__ import annotations

from .session import StreamingSession


class StreamingSTTAdapter:
    def transcribe_buffer(self, session: StreamingSession, audio_chunk: bytes) -> str | None:
        if not audio_chunk:
            return None
        # Placeholder boundary for a future streaming STT provider.
        return None
