from __future__ import annotations

from openai import OpenAI

from ..config import settings


def _pcm16le_sample_chunks(audio_bytes: bytes) -> list[bytes]:
    if len(audio_bytes) % 2 != 0:
        audio_bytes = audio_bytes[:-1]
    return [audio_bytes[index : index + 2] for index in range(0, len(audio_bytes), 2)]


def resample_pcm16le_24khz_to_8khz(audio_bytes: bytes) -> bytes:
    samples = _pcm16le_sample_chunks(audio_bytes)
    if not samples:
        return b""
    downsampled = bytearray()
    for index in range(0, len(samples), 3):
        downsampled.extend(samples[index])
    return bytes(downsampled)


def _linear_to_mulaw_sample(sample: int) -> int:
    bias = 0x84
    clip = 32635
    sign = 0
    if sample < 0:
        sign = 0x80
        sample = -sample
    if sample > clip:
        sample = clip
    sample += bias

    exponent = 7
    mask = 0x4000
    while exponent > 0 and (sample & mask) == 0:
        exponent -= 1
        mask >>= 1

    mantissa = (sample >> (exponent + 3)) & 0x0F
    return (~(sign | (exponent << 4) | mantissa)) & 0xFF


def pcm16le_to_mulaw_8khz(audio_bytes: bytes) -> bytes:
    if len(audio_bytes) % 2 != 0:
        audio_bytes = audio_bytes[:-1]
    if not audio_bytes:
        return b""
    encoded = bytearray()
    for index in range(0, len(audio_bytes), 2):
        sample = int.from_bytes(audio_bytes[index : index + 2], byteorder="little", signed=True)
        encoded.append(_linear_to_mulaw_sample(sample))
    return bytes(encoded)


class OpenAIStreamingTTSProvider:
    def __init__(self, client: OpenAI | None = None) -> None:
        self._client = client

    def _get_client(self) -> OpenAI | None:
        if self._client is not None:
            return self._client
        if not settings.openai_api_key:
            return None
        self._client = OpenAI(api_key=settings.openai_api_key)
        return self._client

    def synthesize_pcm16(self, reply_text: str) -> bytes | None:
        client = self._get_client()
        if client is None or not reply_text.strip():
            return None
        response = client.audio.speech.create(
            model=settings.streaming_tts_model,
            voice=settings.streaming_tts_voice,
            input=reply_text,
            response_format="pcm",
            timeout=10.0,
        )
        if isinstance(response, bytes):
            return response or None
        read_fn = getattr(response, "read", None)
        if callable(read_fn):
            return read_fn() or None
        content = getattr(response, "content", None)
        if isinstance(content, bytes):
            return content or None
        return None


class StreamingTTSAdapter:
    def __init__(self, provider: OpenAIStreamingTTSProvider | None = None) -> None:
        self._provider = provider or OpenAIStreamingTTSProvider()

    def synthesize_mulaw(self, reply_text: str) -> bytes | None:
        if not reply_text.strip():
            return None
        pcm_24khz = self._provider.synthesize_pcm16(reply_text)
        if not pcm_24khz:
            return None
        pcm_8khz = resample_pcm16le_24khz_to_8khz(pcm_24khz)
        return pcm16le_to_mulaw_8khz(pcm_8khz)
