import base64
import importlib


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

    assert pcm_8khz[:2] == (0).to_bytes(2, byteorder="little", signed=True)
    assert len(pcm_8khz) == 4

    pcm_16khz = stt_module.resample_pcm16le_8khz_to_16khz(pcm_8khz)
    assert pcm_16khz[:4] == pcm_8khz[:2] * 2
    assert len(pcm_16khz) == 8


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
    assert session.current_intent == "BOOK_APPOINTMENT"
    assert session.current_state == "COLLECTING_APPOINTMENT_DAY"
    assert session.transcript == [
        {"role": "caller", "text": "I want to book an appointment"},
        {"role": "assistant", "text": "Sure, I can help schedule that. What day works for you?"},
    ]
