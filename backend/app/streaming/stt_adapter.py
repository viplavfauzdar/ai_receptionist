from __future__ import annotations

import base64
from binascii import Error as BinasciiError
from typing import Final

from .session import StreamingSession

_MU_LAW_BIAS: Final[int] = 0x84


def decode_twilio_mulaw_payload(payload_b64: str) -> bytes:
    if not payload_b64:
        return b""
    try:
        return base64.b64decode(payload_b64, validate=True)
    except (BinasciiError, ValueError):
        return b""


def _mulaw_byte_to_pcm16_sample(value: int) -> int:
    ulaw = (~value) & 0xFF
    sign = ulaw & 0x80
    exponent = (ulaw >> 4) & 0x07
    mantissa = ulaw & 0x0F
    sample = ((mantissa << 3) + _MU_LAW_BIAS) << exponent
    sample -= _MU_LAW_BIAS
    return -sample if sign else sample


def mulaw_bytes_to_pcm16le(audio_bytes: bytes) -> bytes:
    if not audio_bytes:
        return b""
    pcm = bytearray()
    for byte in audio_bytes:
        sample = _mulaw_byte_to_pcm16_sample(byte)
        pcm.extend(int(sample).to_bytes(2, byteorder="little", signed=True))
    return bytes(pcm)


def resample_pcm16le_8khz_to_16khz(audio_bytes: bytes) -> bytes:
    if not audio_bytes:
        return b""
    if len(audio_bytes) % 2 != 0:
        audio_bytes = audio_bytes[:-1]
    if not audio_bytes:
        return b""
    upsampled = bytearray()
    for index in range(0, len(audio_bytes), 2):
        sample = audio_bytes[index : index + 2]
        upsampled.extend(sample)
        upsampled.extend(sample)
    return bytes(upsampled)


class StreamingSTTAdapter:
    def decode_payload_to_pcm16_16khz(self, payload_b64: str) -> bytes:
        mulaw_audio = decode_twilio_mulaw_payload(payload_b64)
        pcm16_8khz = mulaw_bytes_to_pcm16le(mulaw_audio)
        return resample_pcm16le_8khz_to_16khz(pcm16_8khz)

    def transcribe_pcm16(self, session: StreamingSession, pcm_audio_16khz: bytes) -> str | None:
        if not pcm_audio_16khz:
            return None
        # Placeholder boundary for a future streaming STT provider.
        return None

    def transcribe_buffer(self, session: StreamingSession, audio_chunk: bytes) -> str | None:
        if not audio_chunk:
            return None
        return self.transcribe_pcm16(session, audio_chunk)
