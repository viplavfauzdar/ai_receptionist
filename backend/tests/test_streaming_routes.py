import importlib
import json
import xml.etree.ElementTree as ET
from base64 import b64encode


streaming_module = importlib.import_module("app.streaming.routes")


def _parse_xml(text: str) -> ET.Element:
    return ET.fromstring(text)


def test_voice_stream_returns_connect_stream_twiml(client, monkeypatch):
    monkeypatch.setattr(streaming_module.settings, "enable_streaming_voice_experiment", True)
    monkeypatch.setattr(streaming_module.settings, "business_name", "Bright Smile Dental")
    streaming_module.streaming_session_store._sessions.clear()

    res = client.post(
        "/voice-stream",
        headers={"host": "example.ngrok.app", "x-forwarded-proto": "https"},
    )

    assert res.status_code == 200
    xml = _parse_xml(res.text)
    say = xml.find("Say")
    assert say is not None
    assert say.text == "Hi, Bright Smile Dental. How can I help?"
    connect = xml.find("Connect")
    assert connect is not None
    stream = connect.find("Stream")
    assert stream is not None
    assert stream.attrib["url"] == "wss://example.ngrok.app/ws/media-stream"


def test_media_stream_websocket_accepts_twilio_message_sequence(client, monkeypatch):
    monkeypatch.setattr(streaming_module.settings, "enable_streaming_voice_experiment", True)
    streaming_module.streaming_session_store._sessions.clear()

    with client.websocket_connect("/ws/media-stream") as websocket:
        websocket.send_text(json.dumps({"event": "connected", "protocol": "Call", "version": "1.0.0"}))
        websocket.send_text(
            json.dumps(
                {
                    "event": "start",
                    "start": {
                        "streamSid": "MZ123",
                        "callSid": "CA123",
                        "accountSid": "AC123",
                        "customParameters": {"From": "+15551230000", "To": "+15557654321"},
                    },
                }
            )
        )
        start_ack = websocket.receive_json()
        assert start_ack["event"] == "mark"
        assert start_ack["mark"]["name"] == "stream-started"
        websocket.send_text(
            json.dumps(
                {
                    "event": "media",
                    "streamSid": "MZ123",
                    "media": {"payload": "aGVsbG8="},
                }
            )
        )
        media_ack = websocket.receive_json()
        assert media_ack["event"] == "mark"
        assert media_ack["mark"]["name"] == "media-received"
        session = streaming_module.streaming_session_store.get("MZ123")
        assert session is not None
        assert session.call_sid == "CA123"
        assert session.media_chunk_count == 1
        assert session.total_audio_bytes == 5

        websocket.send_text(
            json.dumps(
                {
                    "event": "mark",
                    "streamSid": "MZ123",
                    "mark": {"name": "twilio-mark"},
                }
            )
        )
        mark_ack = websocket.receive_json()
        assert mark_ack["mark"]["name"] == "mark-received"
        assert "mark" in session.event_history

        websocket.send_text(
            json.dumps(
                {
                    "event": "stop",
                    "stop": {"streamSid": "MZ123", "callSid": "CA123"},
                }
            )
        )

    assert streaming_module.streaming_session_store.get("MZ123") is None


def test_media_stream_disconnect_cleans_up_session(client, monkeypatch):
    monkeypatch.setattr(streaming_module.settings, "enable_streaming_voice_experiment", True)
    streaming_module.streaming_session_store._sessions.clear()

    with client.websocket_connect("/ws/media-stream") as websocket:
        websocket.send_text(
            json.dumps(
                {
                    "event": "start",
                    "start": {
                        "streamSid": "MZ-cleanup",
                        "callSid": "CA-cleanup",
                        "customParameters": {},
                    },
                }
            )
        )
        start_ack = websocket.receive_json()
        assert start_ack["mark"]["name"] == "stream-started"
        assert streaming_module.streaming_session_store.get("MZ-cleanup") is not None

    assert streaming_module.streaming_session_store.get("MZ-cleanup") is None


def test_media_stream_transcribes_buffered_audio_and_updates_session(client, monkeypatch):
    monkeypatch.setattr(streaming_module.settings, "enable_streaming_voice_experiment", True)
    streaming_module.streaming_session_store._sessions.clear()
    monkeypatch.setattr(
        streaming_module.stt_adapter,
        "transcribe_buffer",
        lambda session, audio_chunk: "What are your hours?" if audio_chunk else None,
    )
    monkeypatch.setattr(
        streaming_module.tts_adapter,
        "synthesize_mulaw",
        lambda reply_text: b"\x01\x02" if reply_text else None,
    )
    monkeypatch.setattr(streaming_module, "TRANSCRIBE_BUFFER_BYTES", 640)

    payload = b64encode(b"\xff" * 160).decode("ascii")

    with client.websocket_connect("/ws/media-stream") as websocket:
        websocket.send_text(
            json.dumps(
                {
                    "event": "start",
                    "start": {
                        "streamSid": "MZ-transcribe",
                        "callSid": "CA-transcribe",
                        "customParameters": {},
                    },
                }
            )
        )
        websocket.receive_json()
        websocket.send_text(
            json.dumps(
                {
                    "event": "media",
                    "streamSid": "MZ-transcribe",
                    "media": {"payload": payload},
                }
            )
        )
        media_ack = websocket.receive_json()
        assert media_ack["mark"]["name"] == "media-received"
        outbound_media = websocket.receive_json()
        assert outbound_media["event"] == "media"
        assert outbound_media["streamSid"] == "MZ-transcribe"
        assert outbound_media["media"]["payload"] == b64encode(b"\x01\x02").decode("ascii")
        reply_ack = websocket.receive_json()
        assert reply_ack["mark"]["name"] == "reply-sent"

        session = streaming_module.streaming_session_store.get("MZ-transcribe")
        assert session is not None
        assert session.last_transcript_text == "What are your hours?"
        assert session.last_reply_text is not None
        assert session.last_reply_text.startswith("Our hours are ")
        assert session.current_intent == "BUSINESS_HOURS"


def test_media_stream_does_not_call_stt_for_tiny_audio_chunks(client, monkeypatch):
    monkeypatch.setattr(streaming_module.settings, "enable_streaming_voice_experiment", True)
    streaming_module.streaming_session_store._sessions.clear()
    monkeypatch.setattr(streaming_module, "TRANSCRIBE_BUFFER_BYTES", 32000)
    call_count = {"count": 0}

    def _fake_transcribe(session, audio_chunk):
        call_count["count"] += 1
        return "should not happen"

    monkeypatch.setattr(streaming_module.stt_adapter, "transcribe_buffer", _fake_transcribe)
    payload = b64encode(b"\xff" * 80).decode("ascii")

    with client.websocket_connect("/ws/media-stream") as websocket:
        websocket.send_text(
            json.dumps(
                {
                    "event": "start",
                    "start": {
                        "streamSid": "MZ-tiny",
                        "callSid": "CA-tiny",
                        "customParameters": {},
                    },
                }
            )
        )
        websocket.receive_json()
        websocket.send_text(
            json.dumps(
                {
                    "event": "media",
                    "streamSid": "MZ-tiny",
                    "media": {"payload": payload},
                }
            )
        )
        media_ack = websocket.receive_json()
        assert media_ack["mark"]["name"] == "media-received"

        session = streaming_module.streaming_session_store.get("MZ-tiny")
        assert session is not None
        assert session.last_transcript_text is None
        assert call_count["count"] == 0


def test_media_stream_survives_stt_failure_and_keeps_session_alive(client, monkeypatch):
    monkeypatch.setattr(streaming_module.settings, "enable_streaming_voice_experiment", True)
    streaming_module.streaming_session_store._sessions.clear()
    monkeypatch.setattr(streaming_module, "TRANSCRIBE_BUFFER_BYTES", 640)

    def _failing_transcribe(session, audio_chunk):
        raise RuntimeError("unsupported audio")

    monkeypatch.setattr(streaming_module.stt_adapter, "transcribe_buffer", _failing_transcribe)
    payload = b64encode(b"\xff" * 80).decode("ascii")

    with client.websocket_connect("/ws/media-stream") as websocket:
        websocket.send_text(
            json.dumps(
                {
                    "event": "start",
                    "start": {
                        "streamSid": "MZ-stt-error",
                        "callSid": "CA-stt-error",
                        "customParameters": {},
                    },
                }
            )
        )
        websocket.receive_json()
        websocket.send_text(
            json.dumps(
                {
                    "event": "media",
                    "streamSid": "MZ-stt-error",
                    "media": {"payload": payload},
                }
            )
        )
        media_ack = websocket.receive_json()
        assert media_ack["mark"]["name"] == "media-received"

        session = streaming_module.streaming_session_store.get("MZ-stt-error")
        assert session is not None
        assert session.last_transcript_text is None

        websocket.send_text(
            json.dumps(
                {
                    "event": "mark",
                    "streamSid": "MZ-stt-error",
                    "mark": {"name": "after-error"},
                }
            )
        )
        mark_ack = websocket.receive_json()
        assert mark_ack["mark"]["name"] == "mark-received"


def test_media_stream_survives_tts_failure_and_keeps_session_alive(client, monkeypatch):
    monkeypatch.setattr(streaming_module.settings, "enable_streaming_voice_experiment", True)
    streaming_module.streaming_session_store._sessions.clear()
    monkeypatch.setattr(
        streaming_module.stt_adapter,
        "transcribe_buffer",
        lambda session, audio_chunk: "Can I book an appointment?" if audio_chunk else None,
    )
    monkeypatch.setattr(streaming_module, "TRANSCRIBE_BUFFER_BYTES", 640)

    def _failing_tts(reply_text):
        raise RuntimeError("tts unavailable")

    monkeypatch.setattr(streaming_module.tts_adapter, "synthesize_mulaw", _failing_tts)
    payload = b64encode(b"\xff" * 160).decode("ascii")

    with client.websocket_connect("/ws/media-stream") as websocket:
        websocket.send_text(
            json.dumps(
                {
                    "event": "start",
                    "start": {
                        "streamSid": "MZ-tts-error",
                        "callSid": "CA-tts-error",
                        "customParameters": {},
                    },
                }
            )
        )
        websocket.receive_json()
        websocket.send_text(
            json.dumps(
                {
                    "event": "media",
                    "streamSid": "MZ-tts-error",
                    "media": {"payload": payload},
                }
            )
        )
        media_ack = websocket.receive_json()
        assert media_ack["mark"]["name"] == "media-received"

        session = streaming_module.streaming_session_store.get("MZ-tts-error")
        assert session is not None
        assert session.last_reply_text is not None

        websocket.send_text(
            json.dumps(
                {
                    "event": "mark",
                    "streamSid": "MZ-tts-error",
                    "mark": {"name": "after-tts-error"},
                }
            )
        )
        mark_ack = websocket.receive_json()
        assert mark_ack["mark"]["name"] == "mark-received"
