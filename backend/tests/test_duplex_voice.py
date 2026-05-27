import asyncio
from base64 import b64encode
import json
import xml.etree.ElementTree as ET

from app.duplex import routes as duplex_routes
from app.duplex.runtime import VoiceDuplexRuntime
from app.duplex.session import AudioFrame, VoiceDuplexSession, VoiceDuplexState


def _parse_xml(text: str) -> ET.Element:
    return ET.fromstring(text)


def test_voice_duplex_returns_connect_stream_twiml(client):
    res = client.post(
        "/voice-duplex",
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
    assert stream.attrib["url"] == "wss://example.ngrok.app/ws/voice-duplex"


def test_voice_duplex_websocket_accepts_start_media_stop(client):
    duplex_routes.duplex_runtime.sessions.clear()

    with client.websocket_connect("/ws/voice-duplex") as websocket:
        websocket.send_text(json.dumps({"event": "connected", "protocol": "Call", "version": "1.0.0"}))
        websocket.send_text(
            json.dumps(
                {
                    "event": "start",
                    "start": {
                        "streamSid": "MZ-duplex",
                        "callSid": "CA-duplex",
                        "accountSid": "AC-duplex",
                        "customParameters": {"From": "+15551230000", "To": "+15557654321"},
                    },
                }
            )
        )
        start_ack = websocket.receive_json()
        assert start_ack["event"] == "mark"
        assert start_ack["streamSid"] == "MZ-duplex"
        assert start_ack["mark"]["name"] == "voice-duplex-started"

        websocket.send_text(
            json.dumps(
                {
                    "event": "media",
                    "streamSid": "MZ-duplex",
                    "media": {"payload": b64encode(b"\x00\x01\x02").decode("ascii")},
                }
            )
        )
        session = duplex_routes.duplex_runtime.sessions["MZ-duplex"]
        assert session.state == VoiceDuplexState.LISTENING

        websocket.send_text(
            json.dumps(
                {
                    "event": "stop",
                    "stop": {"streamSid": "MZ-duplex", "callSid": "CA-duplex"},
                }
            )
        )

    assert "MZ-duplex" not in duplex_routes.duplex_runtime.sessions


class _TranscriptSTTProvider:
    def has_speech(self, audio_bytes: bytes) -> bool:
        return True

    async def transcribe(self, session: VoiceDuplexSession, frame: AudioFrame) -> str | None:
        return "hello"


class _OneChunkTTSProvider:
    async def synthesize_stream(self, session: VoiceDuplexSession, text: str):
        yield b"\x01\x02"


def test_duplex_runtime_state_transitions_through_pipeline():
    async def _run():
        runtime = VoiceDuplexRuntime(
            stt_provider=_TranscriptSTTProvider(),
            tts_provider=_OneChunkTTSProvider(),
            agent_responder=lambda session, transcript: "Hi there.",
        )
        session = VoiceDuplexSession(stream_sid="MZ-state")
        tasks = [
            asyncio.create_task(runtime.stt_worker(session)),
            asyncio.create_task(runtime.agent_worker(session)),
            asyncio.create_task(runtime.tts_sender(session)),
        ]

        await session.audio_queue.put(
            AudioFrame(
                payload_b64=b64encode(b"\x01\x02").decode("ascii"),
                audio_bytes=b"\x01\x02",
            )
        )
        media_message = await asyncio.wait_for(session.outbound_queue.get(), timeout=1)
        mark_message = await asyncio.wait_for(session.outbound_queue.get(), timeout=1)

        assert media_message["event"] == "media"
        assert mark_message["mark"]["name"] == "voice-duplex-tts-complete"
        assert session.state == VoiceDuplexState.LISTENING
        assert session.transition_history == ["IDLE", "LISTENING", "THINKING", "SPEAKING", "LISTENING"]

        await session.audio_queue.put(None)
        await session.transcript_queue.put(None)
        await session.response_queue.put(None)
        await asyncio.gather(*tasks)

    asyncio.run(_run())


def test_duplex_barge_in_sends_clear_and_cancels_tts():
    async def _run():
        runtime = VoiceDuplexRuntime()
        session = VoiceDuplexSession(stream_sid="MZ-barge")
        session.transition(VoiceDuplexState.SPEAKING)
        session.current_tts_task = asyncio.create_task(asyncio.sleep(10))
        handler_task = asyncio.create_task(runtime.interruption_handler(session))

        await session.interruption_queue.put("caller_speech")
        clear_message = await asyncio.wait_for(session.outbound_queue.get(), timeout=1)

        assert clear_message == {"event": "clear", "streamSid": "MZ-barge"}
        assert session.current_tts_task.cancelled()
        assert session.state == VoiceDuplexState.LISTENING
        assert session.transition_history == ["IDLE", "SPEAKING", "INTERRUPTED", "LISTENING"]

        await session.interruption_queue.put(None)
        await handler_task

    asyncio.run(_run())


def test_duplex_session_queues_are_created_and_drained_safely():
    session = VoiceDuplexSession(stream_sid="MZ-queues")

    session.audio_queue.put_nowait(AudioFrame(payload_b64="", audio_bytes=b""))
    session.transcript_queue.put_nowait("hello")
    session.response_queue.put_nowait("hi")
    session.outbound_queue.put_nowait({"event": "mark"})
    session.interruption_queue.put_nowait("caller_speech")

    session.drain_queues()

    assert session.audio_queue.empty()
    assert session.transcript_queue.empty()
    assert session.response_queue.empty()
    assert session.outbound_queue.empty()
    assert session.interruption_queue.empty()
