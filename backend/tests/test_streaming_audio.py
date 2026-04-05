import base64
import importlib
import io
import wave


ai_module = importlib.import_module("app.ai")
session_module = importlib.import_module("app.streaming.session")
stt_module = importlib.import_module("app.streaming.stt_adapter")
voice_module = importlib.import_module("app.streaming.voice")


def test_decode_twilio_mulaw_payload_handles_valid_and_invalid_base64():
    payload = base64.b64encode(b"\xff\x7f\x00").decode("ascii")

    assert stt_module.decode_twilio_mulaw_payload(payload) == b"\xff\x7f\x00"
    assert stt_module.decode_twilio_mulaw_payload("%%%not-base64%%%") == b""


def test_mulaw_to_pcm16_and_resample_boundaries():
    pcm_8khz = stt_module.mulaw_bytes_to_pcm16le(b"\xff\x00")

    assert len(pcm_8khz) == 4
    assert pcm_8khz != b"\x00\x00\x00\x00"
    assert len(pcm_8khz) == 4

    pcm_16khz = stt_module.resample_pcm16le_8khz_to_16khz(pcm_8khz)
    assert pcm_16khz[:2] == pcm_8khz[:2]
    assert len(pcm_16khz) == 8


def test_build_wav_file_bytes_wraps_pcm_with_expected_format():
    wav_bytes = stt_module.build_wav_file_bytes(b"\x01\x00\x02\x00")

    assert wav_bytes.startswith(b"RIFF")
    assert wav_bytes[8:12] == b"WAVE"
    with wave.open(io.BytesIO(wav_bytes), "rb") as wav_file:
        assert wav_file.getnchannels() == 1
        assert wav_file.getsampwidth() == 2
        assert wav_file.getframerate() == 16000
        assert wav_file.readframes(2) == b"\x01\x00\x02\x00"


def test_streaming_session_audio_buffering_consumes_threshold_chunks():
    session = session_module.StreamingSession(stream_sid="MZ-buffer")

    session.record_media_chunk(80)
    session.append_audio_bytes(b"a" * 200)
    assert session.consume_audio_chunk(320) is None

    session.append_audio_bytes(b"b" * 140)
    first_chunk = session.consume_audio_chunk(320)
    assert first_chunk == (b"a" * 200) + (b"b" * 120)
    assert bytes(session.audio_buffer) == b"b" * 20
    assert session.media_chunk_count == 1
    assert session.total_audio_bytes == 80


def test_openai_streaming_stt_provider_calls_transcriptions_api(monkeypatch):
    captured: dict[str, object] = {}

    class _FakeTranscriptions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return type("Resp", (), {"text": " hello world "})()

    fake_client = type("FakeClient", (), {"audio": type("Audio", (), {"transcriptions": _FakeTranscriptions()})()})()
    provider = stt_module.OpenAIStreamingSTTProvider(client=fake_client)
    monkeypatch.setattr(stt_module.settings, "streaming_stt_model", "gpt-4o-mini-transcribe")

    transcript = provider.transcribe_pcm16(b"\x01\x00\x02\x00")

    assert transcript == "hello world"
    assert captured["model"] == "gpt-4o-mini-transcribe"
    assert captured["timeout"] == 10.0
    uploaded_file = captured["file"]
    assert getattr(uploaded_file, "name", "") == "streaming_chunk.wav"
    assert uploaded_file.read(4) == b"RIFF"


def test_openai_streaming_stt_provider_returns_none_without_key_or_text(monkeypatch):
    provider = stt_module.OpenAIStreamingSTTProvider(client=None)
    monkeypatch.setattr(stt_module.settings, "openai_api_key", "")
    assert provider.transcribe_pcm16(b"\x01\x00") is None

    class _FakeTranscriptions:
        def create(self, **kwargs):
            return type("Resp", (), {"text": "   "})()

    fake_client = type("FakeClient", (), {"audio": type("Audio", (), {"transcriptions": _FakeTranscriptions()})()})()
    provider = stt_module.OpenAIStreamingSTTProvider(client=fake_client)
    assert provider.transcribe_pcm16(b"\x01\x00") is None


def test_streaming_stt_adapter_decode_pipeline_produces_non_empty_pcm():
    payload = base64.b64encode(b"\xff" * 160).decode("ascii")
    adapter = stt_module.StreamingSTTAdapter()

    pcm_audio = adapter.decode_payload_to_pcm16_16khz(payload)

    assert pcm_audio
    assert len(pcm_audio) >= 640


def test_streaming_voice_bridge_uses_existing_conversational_logic(monkeypatch):
    session = session_module.StreamingSession(stream_sid="MZ-voice", call_sid="CA-voice")

    def _fake_detect_and_respond(user_input, business, session, force_fallback_reason=None):
        assert user_input == "I want to book an appointment"
        assert force_fallback_reason == "streaming_experimental_path"
        return ai_module.ReceptionistResult(
            intent="BOOK_APPOINTMENT",
            state="COLLECTING_APPOINTMENT_DAY",
            response="Sure, I can help schedule that. What day works for you?",
            fields={},
        )

    monkeypatch.setattr(voice_module, "detect_and_respond", _fake_detect_and_respond)

    reply_plan = voice_module.maybe_transcript_to_reply(session, "I want to book an appointment")

    assert reply_plan.reply_text == "Sure, I can help schedule that. What day works for you?"
    assert reply_plan.intent == "BOOK_APPOINTMENT"
    assert reply_plan.fallback_used is True
    assert session.current_intent == "BOOK_APPOINTMENT"
    assert session.current_state == "COLLECTING_APPOINTMENT_DAY"
    assert session.transcript == [
        {"role": "caller", "text": "I want to book an appointment"},
        {"role": "assistant", "text": "Sure, I can help schedule that. What day works for you?"},
    ]


def test_streaming_tts_adapter_converts_provider_pcm_to_mulaw(monkeypatch):
    class _FakeProvider:
        def synthesize_pcm16(self, reply_text: str) -> bytes | None:
            assert reply_text == "Hello there"
            return (
                b"\x10\x00\x20\x00\x30\x00"
                b"\x40\x00\x50\x00\x60\x00"
                b"\x70\x00\x80\x00\x90\x00"
            )

    adapter = importlib.import_module("app.streaming.tts_adapter").StreamingTTSAdapter(provider=_FakeProvider())

    mulaw = adapter.synthesize_mulaw("Hello there")

    assert mulaw is not None
    assert len(mulaw) == 3


def test_streaming_voice_bridge_short_booking_transcript_enters_booking_flow():
    session = session_module.StreamingSession(stream_sid="MZ-short", call_sid="CA-short")

    reply_plan = voice_module.maybe_transcript_to_reply(session, "appointment")

    assert reply_plan.intent == "BOOK_APPOINTMENT"
    assert reply_plan.reply_text == "Sure, I can help schedule that. What day works for you?"
    assert reply_plan.reply_text != "Sorry, I didn't catch that. Could you say that again?"
    assert session.current_intent == "BOOK_APPOINTMENT"
    assert session.current_state == "COLLECTING_APPOINTMENT_DAY"


def test_streaming_voice_bridge_empty_transcript_repompts_instead_of_reset():
    session = session_module.StreamingSession(stream_sid="MZ-empty", call_sid="CA-empty")

    reply_plan = voice_module.maybe_transcript_to_reply(session, "   ")

    assert reply_plan.intent == "GENERAL_QUESTION"
    assert reply_plan.reply_text == "Sorry, I didn't catch that. Could you say that again?"
    assert reply_plan.fallback_used is True
    assert session.last_reply_text == "Sorry, I didn't catch that. Could you say that again?"
