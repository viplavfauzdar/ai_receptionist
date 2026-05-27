from __future__ import annotations

import asyncio
import base64
import json
from collections.abc import Callable

from fastapi import WebSocket, WebSocketDisconnect

from .session import AudioFrame, VoiceDuplexSession, VoiceDuplexState
from .stt import StreamingSTTProvider, StubStreamingSTTProvider
from .tts import StreamingTTSProvider, StubStreamingTTSProvider

AgentResponder = Callable[[VoiceDuplexSession, str], str]


def _log_duplex(message: str) -> None:
    print(f"[voice-duplex] {message}", flush=True)


def _default_agent_response(session: VoiceDuplexSession, transcript: str) -> str:
    return "I heard you. This full-duplex path is still experimental."


class VoiceDuplexRuntime:
    def __init__(
        self,
        *,
        stt_provider: StreamingSTTProvider | None = None,
        tts_provider: StreamingTTSProvider | None = None,
        agent_responder: AgentResponder | None = None,
    ) -> None:
        self.stt_provider = stt_provider or StubStreamingSTTProvider()
        self.tts_provider = tts_provider or StubStreamingTTSProvider()
        self.agent_responder = agent_responder or _default_agent_response
        self.sessions: dict[str, VoiceDuplexSession] = {}

    async def handle_websocket(self, websocket: WebSocket) -> None:
        session = VoiceDuplexSession(stream_sid="pending-duplex")
        tasks = [
            asyncio.create_task(self.inbound_audio_receiver(websocket, session)),
            asyncio.create_task(self.stt_worker(session)),
            asyncio.create_task(self.agent_worker(session)),
            asyncio.create_task(self.tts_sender(session)),
            asyncio.create_task(self.interruption_handler(session)),
            asyncio.create_task(self.outbound_sender(websocket, session)),
        ]
        try:
            await session.stop_event.wait()
        finally:
            await self._stop_workers(session)
            await asyncio.gather(*tasks, return_exceptions=True)
            self.sessions.pop(session.stream_sid, None)
            session.drain_queues()

    async def _stop_workers(self, session: VoiceDuplexSession) -> None:
        session.stop_event.set()
        if session.current_tts_task is not None and not session.current_tts_task.done():
            session.current_tts_task.cancel()
        await session.audio_queue.put(None)
        await session.transcript_queue.put(None)
        await session.response_queue.put(None)
        await session.outbound_queue.put(None)
        await session.interruption_queue.put(None)

    async def inbound_audio_receiver(self, websocket: WebSocket, session: VoiceDuplexSession) -> None:
        try:
            while not session.stop_event.is_set():
                raw_text = await websocket.receive_text()
                payload = json.loads(raw_text)
                event_type = str(payload.get("event") or "").lower()

                if event_type == "connected":
                    _log_duplex("event=connected")
                    continue

                if event_type == "start":
                    start = payload.get("start") or {}
                    custom_parameters = start.get("customParameters") or {}
                    old_stream_sid = session.stream_sid
                    session.update_start(
                        stream_sid=str(start.get("streamSid") or payload.get("streamSid") or old_stream_sid),
                        call_sid=start.get("callSid"),
                        account_sid=start.get("accountSid"),
                        from_number=(start.get("from") or start.get("caller")) or custom_parameters.get("From"),
                        to_number=(start.get("to") or start.get("called")) or custom_parameters.get("To"),
                    )
                    self.sessions.pop(old_stream_sid, None)
                    self.sessions[session.stream_sid] = session
                    await session.outbound_queue.put(session.build_mark_message("voice-duplex-started"))
                    _log_duplex(
                        f"event=start stream_sid={session.stream_sid} call_sid={session.call_sid} "
                        f"state={session.state.value}"
                    )
                    continue

                if event_type == "media":
                    media = payload.get("media") or {}
                    payload_b64 = str(media.get("payload") or "")
                    try:
                        audio_bytes = base64.b64decode(payload_b64)
                    except Exception:
                        audio_bytes = b""
                    session.record_audio(audio_bytes)
                    if (
                        session.state == VoiceDuplexState.SPEAKING
                        and audio_bytes
                        and self.stt_provider.has_speech(audio_bytes)
                    ):
                        await session.interruption_queue.put("caller_speech")
                    await session.audio_queue.put(
                        AudioFrame(
                            payload_b64=payload_b64,
                            audio_bytes=audio_bytes,
                            sequence_number=media.get("chunk") or payload.get("sequenceNumber"),
                        )
                    )
                    continue

                if event_type == "stop":
                    _log_duplex(
                        f"event=stop stream_sid={session.stream_sid} "
                        f"media_chunks={session.media_chunk_count} audio_bytes={session.total_audio_bytes}"
                    )
                    session.stop_event.set()
                    return

                _log_duplex(f"event=ignored type={event_type!r}")
        except WebSocketDisconnect:
            _log_duplex(f"event=disconnect stream_sid={session.stream_sid}")
            session.stop_event.set()

    async def stt_worker(self, session: VoiceDuplexSession) -> None:
        while True:
            frame = await session.audio_queue.get()
            try:
                if frame is None:
                    return
                if session.state in {VoiceDuplexState.IDLE, VoiceDuplexState.INTERRUPTED}:
                    session.transition(VoiceDuplexState.LISTENING)
                transcript = await self.stt_provider.transcribe(session, frame)
                if transcript:
                    await session.transcript_queue.put(transcript)
            finally:
                session.audio_queue.task_done()

    async def agent_worker(self, session: VoiceDuplexSession) -> None:
        while True:
            transcript = await session.transcript_queue.get()
            try:
                if transcript is None:
                    return
                session.transition(VoiceDuplexState.THINKING)
                response_text = self.agent_responder(session, transcript)
                if response_text:
                    await session.response_queue.put(response_text)
                else:
                    session.transition(VoiceDuplexState.LISTENING)
            finally:
                session.transcript_queue.task_done()

    async def tts_sender(self, session: VoiceDuplexSession) -> None:
        while True:
            response_text = await session.response_queue.get()
            try:
                if response_text is None:
                    return
                session.transition(VoiceDuplexState.SPEAKING)
                session.current_tts_task = asyncio.create_task(self._stream_tts_audio(session, response_text))
                try:
                    await session.current_tts_task
                except asyncio.CancelledError:
                    continue
                finally:
                    session.current_tts_task = None
                if session.state == VoiceDuplexState.SPEAKING:
                    session.transition(VoiceDuplexState.LISTENING)
                    await session.outbound_queue.put(session.build_mark_message("voice-duplex-tts-complete"))
            finally:
                session.response_queue.task_done()

    async def _stream_tts_audio(self, session: VoiceDuplexSession, response_text: str) -> None:
        async for audio_chunk in self.tts_provider.synthesize_stream(session, response_text):
            if not audio_chunk:
                continue
            payload_b64 = base64.b64encode(audio_chunk).decode("ascii")
            await session.outbound_queue.put(session.build_media_message(payload_b64))

    async def interruption_handler(self, session: VoiceDuplexSession) -> None:
        while True:
            reason = await session.interruption_queue.get()
            try:
                if reason is None:
                    return
                if session.state != VoiceDuplexState.SPEAKING:
                    continue
                session.transition(VoiceDuplexState.INTERRUPTED)
                if session.current_tts_task is not None and not session.current_tts_task.done():
                    session.current_tts_task.cancel()
                await session.outbound_queue.put(session.build_clear_message())
                session.transition(VoiceDuplexState.LISTENING)
                _log_duplex(f"event=barge_in stream_sid={session.stream_sid} reason={reason}")
            finally:
                session.interruption_queue.task_done()

    async def outbound_sender(self, websocket: WebSocket, session: VoiceDuplexSession) -> None:
        while True:
            message = await session.outbound_queue.get()
            try:
                if message is None:
                    return
                await websocket.send_json(message)
            finally:
                session.outbound_queue.task_done()
