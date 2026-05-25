from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

from .session import VoiceDuplexSession


class StreamingTTSProvider(Protocol):
    async def synthesize_stream(self, session: VoiceDuplexSession, text: str) -> AsyncIterator[bytes]:
        ...


class StubStreamingTTSProvider:
    async def synthesize_stream(self, session: VoiceDuplexSession, text: str) -> AsyncIterator[bytes]:
        if False:
            yield b""
