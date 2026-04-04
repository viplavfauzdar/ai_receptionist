from __future__ import annotations


class StreamingTTSAdapter:
    def synthesize_mulaw(self, reply_text: str) -> bytes | None:
        if not reply_text.strip():
            return None
        # Placeholder boundary for a future streaming TTS provider.
        return None
