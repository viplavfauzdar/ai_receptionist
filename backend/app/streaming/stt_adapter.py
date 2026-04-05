from __future__ import annotations

import base64
from binascii import Error as BinasciiError
from io import BytesIO
from typing import Final
import wave

from openai import OpenAI

from ..config import settings

from .session import StreamingSession

_MU_LAW_BIAS: Final[int] = 0x84


def decode_twilio_mulaw_payload(payload_b64: str) -> bytes:
    if not payload_b64:
        return b""
    try:
        return base64.b64decode(payload_b64, validate=True)
    except (BinasciiError, ValueError):
        return b""

def mulaw_bytes_to_pcm16le(audio_bytes: bytes) -> bytes:
    if not audio_bytes:
        return b""
    pcm = bytearray()
    for byte in audio_bytes:
        ulaw = (~byte) & 0xFF
        sign = ulaw & 0x80
        exponent = (ulaw >> 4) & 0x07
        mantissa = ulaw & 0x0F
        sample = ((mantissa << 3) + _MU_LAW_BIAS) << exponent
        sample -= _MU_LAW_BIAS
        if sign:
            sample = -sample
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


def build_wav_file_bytes(pcm_audio_16khz: bytes) -> bytes:
    if not pcm_audio_16khz:
        return b""
    if len(pcm_audio_16khz) % 2 != 0:
        pcm_audio_16khz = pcm_audio_16khz[:-1]
    if not pcm_audio_16khz:
        return b""
    wav_buffer = BytesIO()
    with wave.open(wav_buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(16000)
        wav_file.writeframes(pcm_audio_16khz)
    return wav_buffer.getvalue()


class OpenAIStreamingSTTProvider:
    def __init__(self, client: OpenAI | None = None) -> None:
        self._client = client

    def _get_client(self) -> OpenAI | None:
        if self._client is not None:
            return self._client
        if not settings.openai_api_key:
            return None
        self._client = OpenAI(api_key=settings.openai_api_key)
        return self._client

    def transcribe_pcm16(self, pcm_audio_16khz: bytes) -> str | None:
        client = self._get_client()
        if client is None or not pcm_audio_16khz:
            return None

        wav_bytes = build_wav_file_bytes(pcm_audio_16khz)
        if not wav_bytes:
            return None

        audio_file = BytesIO(wav_bytes)
        audio_file.name = "streaming_chunk.wav"
        response = client.audio.transcriptions.create(
            model=settings.streaming_stt_model,
            file=audio_file,
            timeout=10.0,
        )
        text = getattr(response, "text", None)
        if not isinstance(text, str):
            return None
        cleaned = " ".join(text.split()).strip()
        return cleaned or None


class StreamingSTTAdapter:
    def __init__(self, provider: OpenAIStreamingSTTProvider | None = None) -> None:
        self._provider = provider or OpenAIStreamingSTTProvider()

    def decode_payload_to_pcm16_16khz(self, payload_b64: str) -> bytes:
        mulaw_audio = decode_twilio_mulaw_payload(payload_b64)
        pcm16_8khz = mulaw_bytes_to_pcm16le(mulaw_audio)
        return resample_pcm16le_8khz_to_16khz(pcm16_8khz)

    def transcribe_pcm16(self, session: StreamingSession, pcm_audio_16khz: bytes) -> str | None:
        if not pcm_audio_16khz:
            return None
        return self._provider.transcribe_pcm16(pcm_audio_16khz)

    def transcribe_buffer(self, session: StreamingSession, audio_chunk: bytes) -> str | None:
        if not audio_chunk:
            return None
        return self.transcribe_pcm16(session, audio_chunk)
