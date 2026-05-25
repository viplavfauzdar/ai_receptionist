import asyncio
from base64 import b64encode
import json
import xml.etree.ElementTree as ET

from app.config import Settings, settings
from app.realtime import routes as realtime_routes
from app.realtime.bridge import OpenAIRealtimeBridge, build_realtime_receptionist_instructions
from app.realtime.session import RealtimeBridgeSession


def _parse_xml(text: str) -> ET.Element:
    return ET.fromstring(text)


def test_voice_realtime_disabled_returns_safe_twilml_error(client, monkeypatch):
    monkeypatch.setattr(settings, "enable_openai_realtime_experiment", False)

    res = client.post("/voice-realtime")

    assert res.status_code == 200
    assert "application/xml" in res.headers["content-type"]
    xml = _parse_xml(res.text)
    assert xml.find("Say") is not None
    assert xml.find("Hangup") is not None
    assert "OpenAI Realtime experiment is not enabled" in res.text


def test_voice_realtime_enabled_returns_connect_stream_twilml(client, monkeypatch):
    monkeypatch.setattr(settings, "enable_openai_realtime_experiment", True)

    res = client.post(
        "/voice-realtime",
        headers={"host": "example.ngrok.app", "x-forwarded-proto": "https"},
    )

    assert res.status_code == 200
    assert "application/xml" in res.headers["content-type"]
    xml = _parse_xml(res.text)
    assert xml.find("Say") is None
    connect = xml.find("Connect")
    assert connect is not None
    stream = connect.find("Stream")
    assert stream is not None
    assert stream.attrib["url"] == "wss://example.ngrok.app/ws/openai-realtime"


def test_realtime_session_update_uses_configured_model_voice_and_tools(monkeypatch):
    monkeypatch.setattr(settings, "openai_realtime_model", "gpt-realtime-test")
    monkeypatch.setattr(settings, "openai_realtime_voice", "verse")

    payload = OpenAIRealtimeBridge().build_session_update()

    session = payload["session"]
    assert payload["type"] == "session.update"
    assert session["model"] == "gpt-realtime-test"
    assert session["audio"]["output"]["voice"] == "verse"
    tool_names = {tool["name"] for tool in session["tools"]}
    assert {
        "lookup_business",
        "check_availability",
        "create_booking",
        "capture_callback",
        "log_call_summary",
    }.issubset(tool_names)


def test_realtime_default_voice_is_marin(monkeypatch):
    monkeypatch.delenv("OPENAI_REALTIME_VOICE", raising=False)

    assert Settings(_env_file=None).openai_realtime_voice == "marin"


def test_realtime_openai_connect_url_uses_current_websocket_endpoint(monkeypatch):
    monkeypatch.setattr(settings, "openai_realtime_model", "gpt-realtime-test")

    assert OpenAIRealtimeBridge().build_connect_url() == (
        "wss://api.openai.com/v1/realtime?model=gpt-realtime-test"
    )


def test_realtime_openai_headers_do_not_use_deprecated_beta_header(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "test-key")

    headers = OpenAIRealtimeBridge().build_connect_headers()

    assert headers == {"Authorization": "Bearer test-key"}
    assert "OpenAI-Beta" not in headers


def test_realtime_connect_openai_uses_current_headers(monkeypatch):
    captured = {}

    async def _fake_websocket_connect(url, *, additional_headers):
        captured["url"] = url
        captured["additional_headers"] = additional_headers
        return _FakeOpenAISocket()

    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    monkeypatch.setattr(settings, "openai_realtime_model", "gpt-realtime-test")
    monkeypatch.setattr("app.realtime.bridge.websockets.connect", _fake_websocket_connect)

    asyncio.run(OpenAIRealtimeBridge()._connect_openai())

    assert captured["url"] == "wss://api.openai.com/v1/realtime?model=gpt-realtime-test"
    assert captured["additional_headers"] == {"Authorization": "Bearer test-key"}
    assert "OpenAI-Beta" not in captured["additional_headers"]


def test_realtime_session_update_uses_current_ga_shape(monkeypatch):
    monkeypatch.setattr(settings, "openai_realtime_model", "gpt-realtime-test")
    monkeypatch.setattr(settings, "openai_realtime_voice", "verse")
    monkeypatch.setattr(settings, "realtime_turn_detection_type", "semantic_vad")
    monkeypatch.setattr(settings, "enable_realtime_barge_in", False)

    payload = OpenAIRealtimeBridge().build_session_update()
    session = payload["session"]

    assert payload["type"] == "session.update"
    assert session["type"] == "realtime"
    assert session["model"] == "gpt-realtime-test"
    assert session["output_modalities"] == ["audio"]
    assert session["audio"]["input"]["format"] == {"type": "audio/pcmu"}
    assert session["audio"]["input"]["transcription"] == {"model": "gpt-4o-mini-transcribe"}
    # The model owns turn-taking: it auto-creates a response at end-of-turn.
    assert session["audio"]["input"]["turn_detection"]["type"] == "semantic_vad"
    assert session["audio"]["input"]["turn_detection"]["create_response"] is True
    assert session["audio"]["input"]["turn_detection"]["interrupt_response"] is False
    assert session["audio"]["output"]["format"] == {"type": "audio/pcmu"}
    assert session["audio"]["output"]["voice"] == "verse"
    assert "input_audio_format" not in session
    assert "output_audio_format" not in session
    assert "modalities" not in session


def test_realtime_session_update_uses_configured_transcription_model(monkeypatch):
    monkeypatch.setattr(settings, "streaming_stt_model", "gpt-4o-transcribe")

    session = OpenAIRealtimeBridge().build_session_update()["session"]

    assert session["audio"]["input"]["transcription"] == {"model": "gpt-4o-transcribe"}


def test_realtime_instructions_are_conversational_receptionist_style(monkeypatch):
    monkeypatch.setattr(settings, "business_name", "Bright Smile Dental")

    instructions = build_realtime_receptionist_instructions()
    lower_instructions = instructions.lower()

    assert "calm, friendly dental front-desk receptionist" in lower_instructions
    assert "not an ivr script" in lower_instructions
    assert "keep most responses under 12 words" in lower_instructions


def test_realtime_instructions_include_booking_conversation_rules():
    instructions = build_realtime_receptionist_instructions()
    lower_instructions = instructions.lower()

    assert "do not repeat the greeting" in lower_instructions
    assert "do not assume the caller wants an appointment" in lower_instructions
    assert "do not advance booking flow until the caller clearly asks" in lower_instructions
    assert "after the greeting, wait silently" in lower_instructions
    assert "never ask for date or time unless appointment intent is clear" in lower_instructions
    assert "never produce repair prompts unless the caller actually spoke" in lower_instructions
    assert "ask for date and time together" in lower_instructions
    assert "Sure — what day and time works best?" in instructions


def test_realtime_session_update_includes_conversational_instructions():
    session = OpenAIRealtimeBridge().build_session_update()["session"]
    instructions = session["instructions"]

    assert "Do not repeat the greeting" in instructions
    assert "Do not assume the caller wants an appointment" in instructions
    assert "Ask for date and time together" in instructions


def test_realtime_session_audio_config_uses_current_pcmu_format(monkeypatch):
    monkeypatch.setattr(settings, "realtime_turn_detection_type", "semantic_vad")
    monkeypatch.setattr(settings, "enable_realtime_barge_in", False)
    session = OpenAIRealtimeBridge().build_session_update()["session"]

    assert session["audio"]["input"]["format"] == {"type": "audio/pcmu"}
    assert session["audio"]["output"]["format"] == {"type": "audio/pcmu"}
    assert session["audio"]["input"]["turn_detection"]["type"] == "semantic_vad"
    assert session["audio"]["input"]["turn_detection"]["create_response"] is True
    assert session["audio"]["input"]["turn_detection"]["interrupt_response"] is False


def test_realtime_session_update_uses_marin_output_voice_by_default():
    session = OpenAIRealtimeBridge().build_session_update()["session"]

    assert session["audio"]["output"]["voice"] == "marin"


def test_realtime_session_update_shape_logging_is_secret_safe(capsys, monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "test-secret-key")
    bridge = OpenAIRealtimeBridge()

    bridge._log_session_update_shape(bridge.build_session_update())

    captured = capsys.readouterr().out
    assert "event=session_update_shape" in captured
    assert "input_format=audio/pcmu" in captured
    assert "output_format=audio/pcmu" in captured
    assert "transcription_model=gpt-4o-mini-transcribe" in captured
    assert "voice=marin" in captured
    assert "Authorization" not in captured
    assert "test-secret-key" not in captured


def test_realtime_initial_greeting_response_create_uses_business_greeting(monkeypatch):
    monkeypatch.setattr(settings, "business_greeting", "Hello from the front desk.")

    payload = OpenAIRealtimeBridge().build_initial_greeting_response_create()

    assert payload == {
        "type": "response.create",
        "response": {
            "instructions": "Say exactly this greeting, then wait for the caller: Hello from the front desk.",
        },
    }


def test_realtime_initial_greeting_response_create_contains_greeting_only(monkeypatch):
    monkeypatch.setattr(settings, "business_greeting", "Bright Smile Dental, how can I help you today?")

    payload = OpenAIRealtimeBridge().build_initial_greeting_response_create()
    instructions = payload["response"]["instructions"]

    assert "Bright Smile Dental, how can I help you today?" in instructions
    assert "appointment" not in instructions.lower()
    assert "date" not in instructions.lower()
    assert "time" not in instructions.lower()
    assert "day and time" not in instructions.lower()


def test_realtime_initial_greeting_response_create_uses_short_fallback(monkeypatch):
    monkeypatch.setattr(settings, "business_greeting", "   ")

    payload = OpenAIRealtimeBridge().build_initial_greeting_response_create()

    assert payload["type"] == "response.create"
    assert payload["response"]["instructions"].endswith("Hi, thanks for calling. How can I help?")


def test_realtime_barge_in_config_false_by_default():
    # The code default is conservative (off); runtime enables it via .env.
    assert Settings(_env_file=None).enable_realtime_barge_in is False


def test_realtime_turn_detection_type_defaults_to_semantic_vad():
    assert Settings(_env_file=None).realtime_turn_detection_type == "semantic_vad"


def test_realtime_session_update_interrupt_response_follows_barge_in_flag(monkeypatch):
    monkeypatch.setattr(settings, "enable_realtime_barge_in", True)
    session = OpenAIRealtimeBridge().build_session_update()["session"]
    assert session["audio"]["input"]["turn_detection"]["interrupt_response"] is True


class _FakeOpenAISocket:
    def __init__(self):
        self.sent: list[dict[str, object]] = []
        self.closed = False

    async def send(self, message: str) -> None:
        self.sent.append(json.loads(message))

    async def recv(self) -> str:
        await asyncio.sleep(60)
        return json.dumps({"type": "noop"})

    async def close(self) -> None:
        self.closed = True


def test_openai_realtime_websocket_accepts_twilio_start_media_stop(client, monkeypatch):
    monkeypatch.setattr(settings, "enable_openai_realtime_experiment", True)
    fake_socket = _FakeOpenAISocket()
    original_bridge = realtime_routes.realtime_bridge
    realtime_routes.realtime_bridge = OpenAIRealtimeBridge(connector=lambda: _fake_connect(fake_socket))

    try:
        with client.websocket_connect("/ws/openai-realtime") as websocket:
            websocket.send_text(json.dumps({"event": "connected", "protocol": "Call", "version": "1.0.0"}))
            websocket.send_text(
                json.dumps(
                    {
                        "event": "start",
                        "start": {
                            "streamSid": "MZ-realtime",
                            "callSid": "CA-realtime",
                            "accountSid": "AC-realtime",
                            "customParameters": {"From": "+15551230000", "To": "+15557654321"},
                        },
                    }
                )
            )
            websocket.send_text(
                json.dumps(
                    {
                        "event": "media",
                        "streamSid": "MZ-realtime",
                        "media": {"payload": b64encode(b"\x01\x02").decode("ascii")},
                    }
                )
            )
            websocket.send_text(
                json.dumps(
                    {
                        "event": "stop",
                        "stop": {"streamSid": "MZ-realtime", "callSid": "CA-realtime"},
                    }
                )
            )
    finally:
        realtime_routes.realtime_bridge = original_bridge

    sent_types = [message["type"] for message in fake_socket.sent]
    assert sent_types[0] == "session.update"
    assert sent_types[1] == "response.create"
    assert sent_types.count("response.create") == 1
    assert "How can I help you today?" in fake_socket.sent[1]["response"]["instructions"]
    assert "input_audio_buffer.append" in sent_types
    assert fake_socket.closed is True


class _QueuedOpenAISocket:
    def __init__(self, events: list[dict[str, object]]):
        self.events = list(events)
        self.sent: list[dict[str, object]] = []
        self.closed = False

    async def send(self, message: str) -> None:
        self.sent.append(json.loads(message))

    async def recv(self) -> str:
        if self.events:
            return json.dumps(self.events.pop(0))
        await asyncio.sleep(60)
        return json.dumps({"type": "noop"})

    async def close(self) -> None:
        self.closed = True


def test_realtime_bridge_forwards_openai_audio_delta_and_barge_in_clear(client, monkeypatch):
    monkeypatch.setattr(settings, "enable_openai_realtime_experiment", True)
    monkeypatch.setattr(settings, "enable_realtime_barge_in", True)
    # The assistant emits audio, then the server VAD reports the caller started speaking.
    fake_socket = _QueuedOpenAISocket(
        [
            {"type": "response.output_audio.delta", "delta": b64encode(b"\x05\x06").decode("ascii")},
            {"type": "input_audio_buffer.speech_started"},
        ]
    )
    original_bridge = realtime_routes.realtime_bridge
    realtime_routes.realtime_bridge = OpenAIRealtimeBridge(connector=lambda: _fake_connect(fake_socket))

    try:
        with client.websocket_connect("/ws/openai-realtime") as websocket:
            websocket.send_text(
                json.dumps(
                    {
                        "event": "start",
                        "start": {"streamSid": "MZ-barge", "callSid": "CA-barge"},
                    }
                )
            )
            outbound_media = websocket.receive_json()
            assert outbound_media["event"] == "media"
            assert outbound_media["streamSid"] == "MZ-barge"
            assert outbound_media["media"]["payload"] == b64encode(b"\x05\x06").decode("ascii")

            # speech_started triggers a Twilio buffer flush so the assistant goes silent.
            clear_message = websocket.receive_json()
            assert clear_message == {"event": "clear", "streamSid": "MZ-barge"}
            websocket.send_text(json.dumps({"event": "stop", "stop": {"streamSid": "MZ-barge"}}))
    finally:
        realtime_routes.realtime_bridge = original_bridge

    sent_types = [message["type"] for message in fake_socket.sent]
    # interrupt_response=true truncates the model server-side, so the bridge must NOT send
    # response.cancel (races interrupt_response) or input_audio_buffer.clear (drops speech).
    assert "response.cancel" not in sent_types
    assert "input_audio_buffer.clear" not in sent_types
    assert fake_socket.closed is True


def test_realtime_pcmu_delta_is_forwarded_unchanged_to_twilio(client, monkeypatch):
    monkeypatch.setattr(settings, "enable_openai_realtime_experiment", True)
    openai_delta = "openai-pcmu-delta-not-decoded"
    fake_socket = _QueuedOpenAISocket(
        [
            {"type": "response.output_audio.delta", "delta": openai_delta},
        ]
    )
    original_bridge = realtime_routes.realtime_bridge
    realtime_routes.realtime_bridge = OpenAIRealtimeBridge(connector=lambda: _fake_connect(fake_socket))

    try:
        with client.websocket_connect("/ws/openai-realtime") as websocket:
            websocket.send_text(
                json.dumps(
                    {
                        "event": "start",
                        "start": {"streamSid": "MZ-direct-pcmu", "callSid": "CA-direct-pcmu"},
                    }
                )
            )
            outbound_media = websocket.receive_json()
            assert outbound_media == {
                "event": "media",
                "streamSid": "MZ-direct-pcmu",
                "media": {"payload": openai_delta},
            }
            websocket.send_text(json.dumps({"event": "stop", "stop": {"streamSid": "MZ-direct-g711"}}))
    finally:
        realtime_routes.realtime_bridge = original_bridge


def test_realtime_noise_only_events_do_not_send_extra_response_create(client, monkeypatch):
    monkeypatch.setattr(settings, "enable_openai_realtime_experiment", True)
    fake_socket = _QueuedOpenAISocket(
        [
            {"type": "input_audio_buffer.speech_started"},
            {"type": "input_audio_buffer.speech_stopped"},
        ]
    )
    original_bridge = realtime_routes.realtime_bridge
    realtime_routes.realtime_bridge = OpenAIRealtimeBridge(connector=lambda: _fake_connect(fake_socket))

    try:
        with client.websocket_connect("/ws/openai-realtime") as websocket:
            websocket.send_text(
                json.dumps(
                    {
                        "event": "start",
                        "start": {"streamSid": "MZ-noise-only", "callSid": "CA-noise-only"},
                    }
                )
            )
            websocket.send_text(json.dumps({"event": "stop", "stop": {"streamSid": "MZ-noise-only"}}))
    finally:
        realtime_routes.realtime_bridge = original_bridge

    response_creates = [message for message in fake_socket.sent if message["type"] == "response.create"]
    assert len(response_creates) == 1
    assert "initial_greeting" not in response_creates[0]["response"]["instructions"]


def test_realtime_user_transcript_does_not_trigger_bridge_response_create(client, monkeypatch):
    # With create_response=true the model auto-creates the reply at end-of-turn, so the
    # bridge must NOT send its own response.create when a transcript completes. The only
    # bridge-issued response.create is the initial greeting.
    monkeypatch.setattr(settings, "enable_openai_realtime_experiment", True)
    fake_socket = _QueuedOpenAISocket(
        [
            {"type": "response.created"},
            {"type": "response.done"},
            {"type": "conversation.item.input_audio_transcription.completed", "transcript": "I need an appointment"},
        ]
    )
    original_bridge = realtime_routes.realtime_bridge
    realtime_routes.realtime_bridge = OpenAIRealtimeBridge(connector=lambda: _fake_connect(fake_socket))

    try:
        with client.websocket_connect("/ws/openai-realtime") as websocket:
            websocket.send_text(
                json.dumps(
                    {
                        "event": "start",
                        "start": {"streamSid": "MZ-user-input", "callSid": "CA-user-input"},
                    }
                )
            )
            websocket.send_text(json.dumps({"event": "stop", "stop": {"streamSid": "MZ-user-input"}}))
    finally:
        realtime_routes.realtime_bridge = original_bridge

    sent_types = [message["type"] for message in fake_socket.sent]
    assert sent_types.count("response.create") == 1


def test_realtime_user_transcript_before_awaiting_input_does_not_create_response(client, monkeypatch):
    monkeypatch.setattr(settings, "enable_openai_realtime_experiment", True)
    fake_socket = _QueuedOpenAISocket(
        [
            {"type": "conversation.item.input_audio_transcription.completed", "transcript": "I need an appointment"},
        ]
    )
    original_bridge = realtime_routes.realtime_bridge
    realtime_routes.realtime_bridge = OpenAIRealtimeBridge(connector=lambda: _fake_connect(fake_socket))

    try:
        with client.websocket_connect("/ws/openai-realtime") as websocket:
            websocket.send_text(
                json.dumps(
                    {
                        "event": "start",
                        "start": {"streamSid": "MZ-early-user-input", "callSid": "CA-early-user-input"},
                    }
                )
            )
            websocket.send_text(json.dumps({"event": "stop", "stop": {"streamSid": "MZ-early-user-input"}}))
    finally:
        realtime_routes.realtime_bridge = original_bridge

    sent_types = [message["type"] for message in fake_socket.sent]
    assert sent_types.count("response.create") == 1


def test_realtime_user_item_without_text_does_not_create_response(client, monkeypatch):
    monkeypatch.setattr(settings, "enable_openai_realtime_experiment", True)
    fake_socket = _QueuedOpenAISocket(
        [
            {"type": "response.created"},
            {"type": "response.done"},
            {"type": "conversation.item.created", "item": {"role": "user", "content": []}},
        ]
    )
    original_bridge = realtime_routes.realtime_bridge
    realtime_routes.realtime_bridge = OpenAIRealtimeBridge(connector=lambda: _fake_connect(fake_socket))

    try:
        with client.websocket_connect("/ws/openai-realtime") as websocket:
            websocket.send_text(
                json.dumps(
                    {
                        "event": "start",
                        "start": {"streamSid": "MZ-user-empty", "callSid": "CA-user-empty"},
                    }
                )
            )
            websocket.send_text(json.dumps({"event": "stop", "stop": {"streamSid": "MZ-user-empty"}}))
    finally:
        realtime_routes.realtime_bridge = original_bridge

    sent_types = [message["type"] for message in fake_socket.sent]
    assert sent_types.count("response.create") == 1


def test_realtime_inbound_media_before_response_does_not_cancel(client, monkeypatch):
    monkeypatch.setattr(settings, "enable_openai_realtime_experiment", True)
    fake_socket = _FakeOpenAISocket()
    original_bridge = realtime_routes.realtime_bridge
    realtime_routes.realtime_bridge = OpenAIRealtimeBridge(connector=lambda: _fake_connect(fake_socket))

    try:
        with client.websocket_connect("/ws/openai-realtime") as websocket:
            websocket.send_text(
                json.dumps(
                    {
                        "event": "start",
                        "start": {"streamSid": "MZ-no-response", "callSid": "CA-no-response"},
                    }
                )
            )
            websocket.send_text(
                json.dumps(
                    {
                        "event": "media",
                        "streamSid": "MZ-no-response",
                        "media": {"payload": b64encode(b"\x07\x08").decode("ascii")},
                    }
                )
            )
            websocket.send_text(json.dumps({"event": "stop", "stop": {"streamSid": "MZ-no-response"}}))
    finally:
        realtime_routes.realtime_bridge = original_bridge

    sent_types = [message["type"] for message in fake_socket.sent]
    assert "input_audio_buffer.append" in sent_types
    assert "response.cancel" not in sent_types
    assert "input_audio_buffer.clear" not in sent_types


def test_realtime_inbound_media_during_active_response_does_not_cancel_when_barge_in_disabled(client, monkeypatch):
    monkeypatch.setattr(settings, "enable_openai_realtime_experiment", True)
    monkeypatch.setattr(settings, "enable_realtime_barge_in", False)
    fake_socket = _QueuedOpenAISocket([{"type": "response.created"}])
    original_bridge = realtime_routes.realtime_bridge
    realtime_routes.realtime_bridge = OpenAIRealtimeBridge(connector=lambda: _fake_connect(fake_socket))

    try:
        with client.websocket_connect("/ws/openai-realtime") as websocket:
            websocket.send_text(
                json.dumps(
                    {
                        "event": "start",
                        "start": {"streamSid": "MZ-disabled-barge", "callSid": "CA-disabled-barge"},
                    }
                )
            )
            websocket.send_text(
                json.dumps(
                    {
                        "event": "media",
                        "streamSid": "MZ-disabled-barge",
                        "media": {"payload": b64encode(b"\x07\x08").decode("ascii")},
                    }
                )
            )
            websocket.send_text(json.dumps({"event": "stop", "stop": {"streamSid": "MZ-disabled-barge"}}))
    finally:
        realtime_routes.realtime_bridge = original_bridge

    sent_types = [message["type"] for message in fake_socket.sent]
    assert "input_audio_buffer.append" in sent_types
    assert "response.cancel" not in sent_types
    assert "input_audio_buffer.clear" not in sent_types


def test_realtime_inbound_media_never_sends_response_cancel_even_with_barge_in(client, monkeypatch):
    # Inbound Twilio media frames are just forwarded; they never cancel the response.
    # Interruption is driven by the server VAD's speech_started event, and truncation is
    # handled server-side by interrupt_response — the bridge never sends response.cancel.
    monkeypatch.setattr(settings, "enable_openai_realtime_experiment", True)
    monkeypatch.setattr(settings, "enable_realtime_barge_in", True)
    fake_socket = _QueuedOpenAISocket([{"type": "response.created"}])
    original_bridge = realtime_routes.realtime_bridge
    realtime_routes.realtime_bridge = OpenAIRealtimeBridge(connector=lambda: _fake_connect(fake_socket))

    try:
        with client.websocket_connect("/ws/openai-realtime") as websocket:
            websocket.send_text(
                json.dumps(
                    {
                        "event": "start",
                        "start": {"streamSid": "MZ-active", "callSid": "CA-active"},
                    }
                )
            )
            websocket.send_text(
                json.dumps(
                    {
                        "event": "media",
                        "streamSid": "MZ-active",
                        "media": {"payload": b64encode(b"\x07\x08").decode("ascii")},
                    }
                )
            )
            websocket.send_text(json.dumps({"event": "stop", "stop": {"streamSid": "MZ-active"}}))
    finally:
        realtime_routes.realtime_bridge = original_bridge

    sent_types = [message["type"] for message in fake_socket.sent]
    assert "input_audio_buffer.append" in sent_types
    assert "response.cancel" not in sent_types
    assert "input_audio_buffer.clear" not in sent_types


def test_realtime_speech_started_without_outbound_audio_does_not_clear_twilio(client, monkeypatch):
    # speech_started before the assistant has emitted any audio must NOT send a Twilio
    # clear (there is nothing buffered to flush) and must never send response.cancel.
    monkeypatch.setattr(settings, "enable_openai_realtime_experiment", True)
    monkeypatch.setattr(settings, "enable_realtime_barge_in", True)
    fake_socket = _QueuedOpenAISocket(
        [
            {"type": "response.created"},
            {"type": "input_audio_buffer.speech_started"},
        ]
    )
    original_bridge = realtime_routes.realtime_bridge
    realtime_routes.realtime_bridge = OpenAIRealtimeBridge(connector=lambda: _fake_connect(fake_socket))

    try:
        with client.websocket_connect("/ws/openai-realtime") as websocket:
            websocket.send_text(
                json.dumps(
                    {
                        "event": "start",
                        "start": {"streamSid": "MZ-no-clear", "callSid": "CA-no-clear"},
                    }
                )
            )
            websocket.send_text(json.dumps({"event": "stop", "stop": {"streamSid": "MZ-no-clear"}}))
    finally:
        realtime_routes.realtime_bridge = original_bridge

    sent_types = [message["type"] for message in fake_socket.sent]
    assert "response.cancel" not in sent_types
    assert "input_audio_buffer.clear" not in sent_types
    assert fake_socket.closed is True


def test_realtime_response_done_clears_active_state(client, monkeypatch):
    monkeypatch.setattr(settings, "enable_openai_realtime_experiment", True)
    fake_socket = _QueuedOpenAISocket(
        [
            {"type": "response.created"},
            {"type": "response.done"},
        ]
    )
    original_bridge = realtime_routes.realtime_bridge
    realtime_routes.realtime_bridge = OpenAIRealtimeBridge(connector=lambda: _fake_connect(fake_socket))

    try:
        with client.websocket_connect("/ws/openai-realtime") as websocket:
            websocket.send_text(
                json.dumps(
                    {
                        "event": "start",
                        "start": {"streamSid": "MZ-done", "callSid": "CA-done"},
                    }
                )
            )
            websocket.send_text(
                json.dumps(
                    {
                        "event": "media",
                        "streamSid": "MZ-done",
                        "media": {"payload": b64encode(b"\x07\x08").decode("ascii")},
                    }
                )
            )
            websocket.send_text(json.dumps({"event": "stop", "stop": {"streamSid": "MZ-done"}}))
    finally:
        realtime_routes.realtime_bridge = original_bridge

    sent_types = [message["type"] for message in fake_socket.sent]
    assert "input_audio_buffer.append" in sent_types
    assert "response.cancel" not in sent_types


class _FakeTwilioWebSocket:
    def __init__(self):
        self.sent: list[dict[str, object]] = []

    async def send_json(self, payload: dict[str, object]) -> None:
        self.sent.append(payload)


def test_realtime_barge_in_does_not_send_twilio_clear_before_audio_started(monkeypatch):
    monkeypatch.setattr(settings, "enable_realtime_barge_in", True)

    async def _run():
        bridge = OpenAIRealtimeBridge(connector=lambda: _fake_connect(_FakeOpenAISocket()))
        twilio_socket = _FakeTwilioWebSocket()
        session = RealtimeBridgeSession(stream_sid="MZ-no-audio-yet")
        session.openai_response_active = True
        session.outbound_audio_started = False

        await bridge._handle_barge_in(twilio_socket, session, asyncio.Lock())

        assert twilio_socket.sent == []
        assert session.clear_messages_sent == 0

    asyncio.run(_run())


def test_realtime_barge_in_sends_twilio_clear_after_audio_started(monkeypatch):
    monkeypatch.setattr(settings, "enable_realtime_barge_in", True)

    async def _run():
        bridge = OpenAIRealtimeBridge(connector=lambda: _fake_connect(_FakeOpenAISocket()))
        twilio_socket = _FakeTwilioWebSocket()
        session = RealtimeBridgeSession(stream_sid="MZ-audio-started")
        session.openai_response_active = True
        session.outbound_audio_started = True

        await bridge._handle_barge_in(twilio_socket, session, asyncio.Lock())

        # Flushes Twilio's buffered audio; truncation is handled server-side by
        # interrupt_response, so no response.cancel is issued here.
        assert twilio_socket.sent == [{"event": "clear", "streamSid": "MZ-audio-started"}]
        assert session.clear_messages_sent == 1

    asyncio.run(_run())


def test_realtime_barge_in_disabled_is_a_noop(monkeypatch):
    monkeypatch.setattr(settings, "enable_realtime_barge_in", False)

    async def _run():
        bridge = OpenAIRealtimeBridge(connector=lambda: _fake_connect(_FakeOpenAISocket()))
        twilio_socket = _FakeTwilioWebSocket()
        session = RealtimeBridgeSession(stream_sid="MZ-disabled")
        session.openai_response_active = True
        session.outbound_audio_started = True

        await bridge._handle_barge_in(twilio_socket, session, asyncio.Lock())

        assert twilio_socket.sent == []
        assert session.clear_messages_sent == 0

    asyncio.run(_run())


async def _fake_connect(fake_socket):
    return fake_socket
