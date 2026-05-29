from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from fastapi import WebSocket, WebSocketDisconnect
import websockets

from ..config import settings
from .session import RealtimeBridgeSession
from .tools import (
    REALTIME_TOOL_DEFINITIONS,
    REALTIME_TOOL_HANDLERS,
    persist_realtime_call_end,
    persist_realtime_call_log,
    persist_realtime_call_start,
    persist_realtime_transcript,
)

REALTIME_TWILIO_AUDIO_FORMAT = {"type": "audio/pcmu"}

# Phrases detected in ASSISTANT speech that signal the call should end
END_CALL_PHRASES = (
    "goodbye",
    "bye",
    "have a good day",
    "have a great day",
    "the office will follow up",
    "we'll follow up",
    "we will follow up",
)

# Phrases detected in USER speech that signal they are wrapping up
# When set, the bridge ends the call after the assistant's next response finishes
USER_FAREWELL_PHRASES = (
    "goodbye",
    "bye",
    "thank you",
    "thanks",
    "have a good",
    "that's all",
    "that will be all",
    "talk to you then",
)


class RealtimeSocket(Protocol):
    async def send(self, message: str) -> None:
        ...

    async def recv(self) -> str:
        ...

    async def close(self) -> None:
        ...


RealtimeConnector = Callable[[], Awaitable[RealtimeSocket]]


def _log_realtime(message: str) -> None:
    print(f"[openai-realtime] {message}", flush=True)


def _iter_text_values(value: Any):
    if isinstance(value, str):
        yield value
        return
    if isinstance(value, dict):
        for nested in value.values():
            yield from _iter_text_values(nested)
        return
    if isinstance(value, list):
        for nested in value:
            yield from _iter_text_values(nested)


def _should_end_call(event: dict[str, Any]) -> bool:
    """Check assistant speech for farewell phrases."""
    text = " ".join(_iter_text_values(event)).lower()
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return False

    for phrase in END_CALL_PHRASES:
        if phrase == "bye":
            if re.search(r"\bbye\b", text):
                return True
            continue
        if phrase in text:
            return True
    return False


def _user_said_farewell(transcript: str) -> bool:
    """Check user transcript for farewell/wrap-up phrases."""
    text = transcript.lower().strip()
    text = re.sub(r"\s+", " ", text)
    for phrase in USER_FAREWELL_PHRASES:
        if phrase in ("bye",):
            if re.search(r"\bbye\b", text):
                return True
            continue
        if phrase in text:
            return True
    return False


def _event_text_summary(event: dict[str, Any], *, max_chars: int = 300) -> str:
    text = " ".join(_iter_text_values(event))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_chars]


def build_realtime_receptionist_instructions() -> str:
    booking_status = "enabled" if settings.booking_enabled else "disabled"
    return "\n".join(
        [
            f"You are a warm, upbeat dental receptionist for {settings.business_name}. You genuinely enjoy helping people.",
            f"Business hours: {settings.business_hours}. Booking is {booking_status}.",
            "Sound like a friendly human — natural, cheerful, and brief. Never robotic or scripted.",
            "Keep responses short: one or two sentences at most.",
            "Do not repeat the greeting after the first turn.",
            "Do not assume the caller wants an appointment. Let them lead.",
            "Do not start the booking flow until the caller clearly says they want one.",
            "When the caller wants to book, ask for day and time in one warm question, like: 'What day and time works for you?'",
            "Once you have day and time, ask for name and callback number together in one question.",
            "Once you have all four — day, time, name, number — call the book_appointment tool right away.",
            "Include the appointment type (e.g. deep cleaning, checkup, whitening) in the notes field.",
            "Pass just the weekday in appointment_day (e.g. 'Wednesday', not 'next Wednesday').",
            "After booking succeeds, confirm warmly in one sentence using the specific date (e.g. 'June 4th', not just 'Wednesday'), the time, and the caller's name.",
            "Then pause and let the caller respond — do not ask 'Is there anything else?' immediately.",
            "When the caller says thanks, thank you, bye, goodbye, or sounds like they are wrapping up: say a single warm farewell — e.g. 'You're welcome, bye!' or 'Talk to you then, bye!' — and stop. Do not ask follow-up questions.",
            "Never say 'Hello?' or re-greet after the caller says goodbye.",
            "If you missed something, ask for just that one thing in a natural way.",
        ]
    )


class OpenAIRealtimeBridge:
    def __init__(self, connector: RealtimeConnector | None = None) -> None:
        self.connector = connector or self._connect_openai

    def build_connect_url(self) -> str:
        return f"wss://api.openai.com/v1/realtime?model={settings.openai_realtime_model}"

    def build_connect_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {settings.openai_api_key}"}

    async def _connect_openai(self) -> RealtimeSocket:
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required for the OpenAI Realtime experiment")
        url = self.build_connect_url()
        _log_realtime(f"event=openai_connect url={url}")
        return await websockets.connect(
            url,
            additional_headers=self.build_connect_headers(),
        )

    def _log_session_update_shape(self, session_update: dict[str, Any]) -> None:
        session = session_update.get("session") if isinstance(session_update.get("session"), dict) else {}
        audio = session.get("audio") if isinstance(session.get("audio"), dict) else {}
        audio_input = audio.get("input") if isinstance(audio.get("input"), dict) else {}
        audio_output = audio.get("output") if isinstance(audio.get("output"), dict) else {}
        input_format = audio_input.get("format") if isinstance(audio_input.get("format"), dict) else {}
        output_format = audio_output.get("format") if isinstance(audio_output.get("format"), dict) else {}
        transcription = audio_input.get("transcription") if isinstance(audio_input.get("transcription"), dict) else {}
        _log_realtime(
            "event=session_update_shape "
            f"input_format={input_format.get('type')} "
            f"output_format={output_format.get('type')} "
            f"transcription_model={transcription.get('model')} "
            f"voice={audio_output.get('voice')}"
        )

    def build_session_update(self) -> dict[str, Any]:
        # TODO: Keep this isolated so protocol field names can be adjusted as Realtime evolves.
        return {
            "type": "session.update",
            "session": {
                "type": "realtime",
                "model": settings.openai_realtime_model,
                "output_modalities": ["audio"],
                "instructions": build_realtime_receptionist_instructions(),
                "tools": REALTIME_TOOL_DEFINITIONS,
                "tool_choice": "auto",
                "audio": {
                    "input": {
                        "format": dict(REALTIME_TWILIO_AUDIO_FORMAT),
                        "transcription": {
                            "model": settings.streaming_stt_model,
                        },
                        "turn_detection": {
                            "type": settings.realtime_turn_detection_type,
                            # Let the Realtime model own turn-taking: it auto-creates a
                            # response when it detects end-of-turn, which is far more
                            # natural (and lower latency) than gating every reply behind a
                            # separate transcription round-trip.
                            "create_response": True,
                            # When enabled, the model truncates its own audio the instant
                            # the caller starts speaking, giving true full-duplex barge-in.
                            "interrupt_response": settings.enable_realtime_barge_in,
                        },
                    },
                    "output": {
                        "format": dict(REALTIME_TWILIO_AUDIO_FORMAT),
                        "voice": settings.openai_realtime_voice,
                    },
                },
            },
        }

    def build_initial_greeting_response_create(self) -> dict[str, Any]:
        greeting = " ".join(settings.business_greeting.split()).strip()
        if not greeting:
            greeting = "Hi, thanks for calling. How can I help?"
        return {
            "type": "response.create",
            "response": {
                "instructions": f"Say exactly this greeting, then wait for the caller: {greeting}",
            },
        }

    async def handle(self, twilio_websocket: WebSocket) -> None:
        session = RealtimeBridgeSession()
        openai_socket: RealtimeSocket | None = None
        stop_event = asyncio.Event()
        twilio_send_lock = asyncio.Lock()
        openai_send_lock = asyncio.Lock()
        tasks: list[asyncio.Task[None]] = []

        try:
            openai_socket = await self.connector()
            session_update = self.build_session_update()
            await self._send_openai(openai_socket, openai_send_lock, session_update)
            self._log_session_update_shape(session_update)
            _log_realtime(
                "event=realtime_turn_detection "
                f"type={settings.realtime_turn_detection_type} "
                "create_response=true "
                f"interrupt_response={str(settings.enable_realtime_barge_in).lower()}"
            )
            _log_realtime(f"event=input_transcription_enabled model={settings.streaming_stt_model}")
            _log_realtime(
                "event=session_update_sent "
                f"model={session_update['session'].get('model')} "
                f"voice={session_update['session'].get('audio', {}).get('output', {}).get('voice')}"
            )
            tasks = [
                asyncio.create_task(
                    self._twilio_receive_loop(
                        twilio_websocket,
                        openai_socket,
                        session,
                        stop_event,
                        twilio_send_lock,
                        openai_send_lock,
                    )
                ),
                asyncio.create_task(
                    self._openai_receive_loop(
                        twilio_websocket,
                        openai_socket,
                        session,
                        stop_event,
                        twilio_send_lock,
                        openai_send_lock,
                    )
                ),
            ]
            await stop_event.wait()
        except Exception as exc:
            _log_realtime(f"event=bridge_error error={exc}")
        finally:
            stop_event.set()
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            if openai_socket is not None:
                try:
                    await openai_socket.close()
                except Exception:
                    pass
            # If the call ended because the user (or assistant) said goodbye, give
            # Twilio a moment to finish draining already-buffered audio before we
            # close the WebSocket. This prevents the farewell from being cut off
            # mid-word. The sleep runs here — in handle's finally — so it cannot
            # be cancelled the way a task-internal sleep would be.
            if session.user_said_goodbye:
                await asyncio.sleep(3.0)
            try:
                await twilio_websocket.close(code=1000)
            except Exception:
                pass
            persist_realtime_call_end(session)
            _log_realtime(
                f"event=cleanup stream_sid={session.stream_sid} "
                f"twilio_media_chunks={session.twilio_media_chunks} "
                f"openai_audio_deltas={session.openai_audio_deltas}"
            )

    async def _send_openai(
        self,
        openai_socket: RealtimeSocket,
        send_lock: asyncio.Lock,
        payload: dict[str, Any],
    ) -> None:
        async with send_lock:
            await openai_socket.send(json.dumps(payload))

    async def _send_twilio(
        self,
        twilio_websocket: WebSocket,
        send_lock: asyncio.Lock,
        payload: dict[str, Any],
    ) -> None:
        async with send_lock:
            await twilio_websocket.send_json(payload)

    async def _twilio_receive_loop(
        self,
        twilio_websocket: WebSocket,
        openai_socket: RealtimeSocket,
        session: RealtimeBridgeSession,
        stop_event: asyncio.Event,
        twilio_send_lock: asyncio.Lock,
        openai_send_lock: asyncio.Lock,
    ) -> None:
        try:
            while not stop_event.is_set():
                raw_text = await twilio_websocket.receive_text()
                payload = json.loads(raw_text)
                event_type = str(payload.get("event") or "").lower()

                if event_type == "connected":
                    session.record_event("connected")
                    continue

                if event_type == "start":
                    session.update_from_start(payload.get("start") or {})
                    _log_realtime(f"event=start stream_sid={session.stream_sid} call_sid={session.call_sid}")
                    persist_realtime_call_start(session)
                    greeting_response = self.build_initial_greeting_response_create()
                    await self._send_openai(openai_socket, openai_send_lock, greeting_response)
                    _log_realtime(f"event=response_create_sent stream_sid={session.stream_sid} reason=initial_greeting")
                    continue

                if event_type == "media":
                    media = payload.get("media") or {}
                    audio_payload = str(media.get("payload") or "")
                    session.twilio_media_chunks += 1
                    _log_realtime(
                        f"event=twilio_media_received stream_sid={session.stream_sid} "
                        f"chunk={session.twilio_media_chunks} payload_chars={len(audio_payload)}"
                    )
                    # Always forward caller audio to OpenAI. Barge-in is driven by the
                    # server VAD's speech_started event (handled in the OpenAI loop), not
                    # by raw media frames — Twilio streams a frame every ~20ms regardless
                    # of whether the caller is actually speaking, so triggering on frames
                    # would cancel the assistant on background noise.
                    await self._send_openai(
                        openai_socket,
                        openai_send_lock,
                        {
                            "type": "input_audio_buffer.append",
                            "audio": audio_payload,
                        },
                    )
                    _log_realtime(
                        f"event=input_audio_buffer_append_sent stream_sid={session.stream_sid} "
                        f"chunk={session.twilio_media_chunks} payload_chars={len(audio_payload)}"
                    )
                    continue

                if event_type == "stop":
                    session.record_event("stop")
                    persist_realtime_call_end(session)
                    stop_event.set()
                    return

                session.record_event(f"ignored:{event_type}")
        except WebSocketDisconnect:
            stop_event.set()

    async def _openai_receive_loop(
        self,
        twilio_websocket: WebSocket,
        openai_socket: RealtimeSocket,
        session: RealtimeBridgeSession,
        stop_event: asyncio.Event,
        twilio_send_lock: asyncio.Lock,
        openai_send_lock: asyncio.Lock,
    ) -> None:
        while not stop_event.is_set():
            raw_text = await openai_socket.recv()
            event = json.loads(raw_text)
            event_type = str(event.get("type") or "")

            if event_type in {"session.created", "session.updated"}:
                session.openai_session_id = event.get("session", {}).get("id") if isinstance(event.get("session"), dict) else None
                session.record_event(event_type)
                continue

            if event_type == "response.created":
                if not session.openai_response_active:
                    _log_realtime(f"event=response_active value=true stream_sid={session.stream_sid}")
                session.openai_response_active = True
                session.record_event(event_type)
                continue

            if event_type in {"response.output_audio.delta", "response.audio.delta"}:
                audio_delta = str(event.get("delta") or "")
                if audio_delta:
                    _log_realtime(
                        f"event=openai_audio_delta_received stream_sid={session.stream_sid} "
                        f"payload_chars={len(audio_delta)}"
                    )
                    for _ in range(50):
                        if session.stream_sid != "pending-realtime" or stop_event.is_set():
                            break
                        await asyncio.sleep(0.01)
                    if session.stream_sid == "pending-realtime":
                        continue
                    session.openai_audio_deltas += 1
                    session.outbound_audio_active = True
                    session.outbound_audio_started = True
                    if not session.openai_response_active:
                        _log_realtime(f"event=response_active value=true stream_sid={session.stream_sid}")
                    session.openai_response_active = True
                    await self._send_twilio(
                        twilio_websocket,
                        twilio_send_lock,
                        session.build_twilio_media(audio_delta),
                    )
                    _log_realtime(
                        f"event=openai_audio_delta_forwarded stream_sid={session.stream_sid} "
                        f"delta_index={session.openai_audio_deltas} "
                        "openai_audio_delta_forwarded_direct=true"
                    )
                continue

            if event_type in {"response.output_audio.done", "response.audio.done"}:
                session.outbound_audio_active = False
                session.record_event(event_type)
                continue

            if event_type in {"response.done", "response.cancelled", "response.completed"}:
                session.outbound_audio_active = False
                session.outbound_audio_started = False
                if session.openai_response_active:
                    _log_realtime(f"event=response_active value=false stream_sid={session.stream_sid} reason={event_type}")
                session.openai_response_active = False
                session.record_event(event_type)
                persist_realtime_transcript(session, role="assistant", text=_event_text_summary(event))
                if _should_end_call(event) or session.user_said_goodbye:
                    reason = "response_done" if _should_end_call(event) else "user_said_goodbye"
                    _log_realtime(f"event=end_call_requested stream_sid={session.stream_sid} reason={reason}")
                    persist_realtime_call_end(session)
                    # Signal all loops to stop. The drain sleep and WebSocket close
                    # happen in handle()'s finally block where they cannot be cancelled.
                    stop_event.set()
                    return
                continue

            if event_type == "input_audio_buffer.speech_started":
                # The caller started talking. If the assistant is mid-utterance, flush the
                # audio already buffered on Twilio so the caller hears themselves take the
                # floor immediately. The model truncates its own response via
                # interrupt_response, so we do not cancel it manually here.
                await self._handle_barge_in(twilio_websocket, session, twilio_send_lock)
                session.record_event(event_type)
                continue

            if event_type == "conversation.item.input_audio_transcription.completed":
                transcript = str(event.get("transcript") or "").strip()
                _log_realtime(
                    f"event=transcription_completed stream_sid={session.stream_sid} "
                    f"transcript={transcript}"
                )
                persist_realtime_transcript(session, role="user", text=transcript)
                session.record_event(event_type)
                if _user_said_farewell(transcript):
                    _log_realtime(
                        f"event=user_farewell_detected stream_sid={session.stream_sid} "
                        f"transcript={transcript}"
                    )
                    session.user_said_goodbye = True
                    # Race condition: response.done may have already fired before this
                    # transcription event arrived (semantic VAD starts the model fast).
                    # If no response is currently active, we missed our hangup window —
                    # trigger it now directly.
                    if not session.openai_response_active:
                        _log_realtime(
                            f"event=end_call_requested stream_sid={session.stream_sid} "
                            "reason=user_farewell_post_response"
                        )
                        persist_realtime_call_end(session)
                        # Drain sleep and WebSocket close happen in handle()'s finally.
                        stop_event.set()
                        return
                continue

            if event_type in {
                "input_audio_buffer.speech_stopped",
                "input_audio_buffer.committed",
                "conversation.item.input_audio_transcription.failed",
            }:
                # The model auto-creates the response at end-of-turn (create_response=true),
                # so there is nothing for the bridge to send here.
                session.record_event(event_type)
                continue

            if event_type in {
                "response.function_call_arguments.done",
                "response.tool_call_arguments.done",
                "response.output_item.done",
                "tool.call.done",
            }:
                item = event.get("item") if isinstance(event.get("item"), dict) else {}
                if event_type == "response.output_item.done" and item.get("type") != "function_call":
                    session.record_event(event_type)
                    continue
                await self._handle_tool_call(openai_socket, openai_send_lock, session, event)
                continue

            if event_type == "error":
                if not session.first_openai_error_logged:
                    _log_realtime(f"event=openai_error detail={event}")
                    session.first_openai_error_logged = True
                error = event.get("error") if isinstance(event.get("error"), dict) else {}
                error_code = str(error.get("code") or "")
                if error_code in {"response_cancel_not_active", "response_not_found"}:
                    session.outbound_audio_active = False
                    session.outbound_audio_started = False
                    if session.openai_response_active:
                        _log_realtime(
                            f"event=response_active value=false stream_sid={session.stream_sid} reason={error_code}"
                        )
                    session.openai_response_active = False
                continue

            session.record_event(event_type)

    async def _handle_barge_in(
        self,
        twilio_websocket: WebSocket,
        session: RealtimeBridgeSession,
        twilio_send_lock: asyncio.Lock,
    ) -> None:
        if not settings.enable_realtime_barge_in:
            _log_realtime(f"event=barge_in_disabled stream_sid={session.stream_sid}")
            session.record_event("barge_in_disabled")
            return

        session.outbound_audio_active = False
        # Flush audio Twilio has already buffered but not yet played, so the assistant goes
        # silent the instant the caller speaks. We rely on the Realtime session's
        # interrupt_response=true to truncate the model's response on the OpenAI side, so we
        # do NOT send response.cancel (which races interrupt_response) or
        # input_audio_buffer.clear (which would discard the caller's interrupting speech).
        if session.outbound_audio_started:
            await self._send_twilio(twilio_websocket, twilio_send_lock, session.build_twilio_clear())
            session.outbound_audio_started = False
            _log_realtime(f"event=twilio_clear_sent stream_sid={session.stream_sid} reason=barge_in")
        else:
            _log_realtime(f"event=barge_in_no_audio_to_clear stream_sid={session.stream_sid}")
        session.record_event("barge_in")

    async def _handle_tool_call(
        self,
        openai_socket: RealtimeSocket,
        openai_send_lock: asyncio.Lock,
        session: RealtimeBridgeSession,
        event: dict[str, Any],
    ) -> None:
        item = event.get("item") if isinstance(event.get("item"), dict) else {}
        tool_name = str(event.get("name") or event.get("tool_name") or item.get("name") or "")
        call_id = str(event.get("call_id") or event.get("callId") or event.get("id") or item.get("call_id") or "")
        raw_arguments = event.get("arguments") or item.get("arguments") or "{}"
        try:
            arguments = json.loads(raw_arguments) if isinstance(raw_arguments, str) else dict(raw_arguments)
        except (TypeError, ValueError):
            arguments = {}

        handler = REALTIME_TOOL_HANDLERS.get(tool_name)
        _log_realtime(
            "event=realtime_tool_call_received "
            f"stream_sid={session.stream_sid} tool_name={tool_name} call_id={call_id}"
        )
        persist_realtime_call_log(
            session,
            event_name="realtime_tool_call_received",
            payload={"tool_name": tool_name, "call_id": call_id},
        )
        if handler is None:
            result = {"status": "error", "message": f"Unknown tool: {tool_name}"}
        else:
            result = await handler(session, arguments)

        # TODO: Keep tool output event isolated for protocol updates.
        await self._send_openai(
            openai_socket,
            openai_send_lock,
            {
                "type": "conversation.item.create",
                "item": {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": json.dumps(result),
                },
            },
        )
        await self._send_openai(openai_socket, openai_send_lock, {"type": "response.create"})
