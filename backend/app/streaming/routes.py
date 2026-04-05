from __future__ import annotations

import json
from base64 import b64encode

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from twilio.twiml.voice_response import Connect, Parameter, Stream, VoiceResponse

from ..config import settings
from .session import StreamingSessionStore
from .stt_adapter import StreamingSTTAdapter
from .tts_adapter import StreamingTTSAdapter
from .voice import maybe_transcript_to_reply

streaming_router = APIRouter()
streaming_session_store = StreamingSessionStore()
stt_adapter = StreamingSTTAdapter()
tts_adapter = StreamingTTSAdapter()
TRANSCRIBE_BUFFER_BYTES = 6400


def _log_streaming(message: str) -> None:
    print(f"[streaming] {message}", flush=True)


def _build_stream_websocket_url(request: Request) -> str:
    forwarded_proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    ws_scheme = "wss" if forwarded_proto == "https" else "ws"
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    return f"{ws_scheme}://{host}{settings.streaming_ws_path}"


def _build_streaming_greeting_text() -> str:
    business_name = settings.business_name.strip()
    if business_name:
        return f"Hi, {business_name}. How can I help?"
    greeting = " ".join(settings.business_greeting.split()).strip()
    if greeting:
        return greeting
    return "Hi. How can I help?"


def _build_streaming_twiml(request: Request) -> str:
    response = VoiceResponse()
    response.say(_build_streaming_greeting_text())
    connect = Connect()
    stream = Stream(url=_build_stream_websocket_url(request))
    stream.append(Parameter(name="route", value="experimental-stream"))
    connect.append(stream)
    response.append(connect)
    return str(response)


def _build_outbound_mark_message(*, stream_sid: str, mark_name: str) -> dict[str, object]:
    return {
        "event": "mark",
        "streamSid": stream_sid,
        "mark": {"name": mark_name},
    }


def _build_outbound_media_message(*, stream_sid: str, audio_bytes: bytes) -> dict[str, object]:
    return {
        "event": "media",
        "streamSid": stream_sid,
        "media": {"payload": b64encode(audio_bytes).decode("ascii")},
    }


@streaming_router.post(settings.streaming_voice_route)
async def voice_stream(request: Request):
    if not settings.enable_streaming_voice_experiment:
        raise HTTPException(status_code=404, detail="Streaming voice experiment is disabled")
    twiml = _build_streaming_twiml(request)
    return Response(content=twiml, media_type="application/xml")


@streaming_router.websocket(settings.streaming_ws_path)
async def media_stream(websocket: WebSocket):
    await websocket.accept()
    if not settings.enable_streaming_voice_experiment:
        await websocket.close(code=1008)
        return

    current_stream_sid: str | None = None
    try:
        while True:
            raw_text = await websocket.receive_text()
            payload = json.loads(raw_text)
            event_type = str(payload.get("event") or "").lower()

            if event_type == "connected":
                protocol = payload.get("protocol", "Call")
                version = payload.get("version", "1.0.0")
                _log_streaming(f"event=connected protocol={protocol} version={version}")
                continue

            if event_type == "start":
                start = payload.get("start") or {}
                current_stream_sid = str(start.get("streamSid") or payload.get("streamSid") or "unknown-stream")
                custom_parameters = {
                    str(key): str(value)
                    for key, value in (start.get("customParameters") or {}).items()
                }
                session = streaming_session_store.create_or_update_start(
                    stream_sid=current_stream_sid,
                    call_sid=start.get("callSid"),
                    account_sid=start.get("accountSid"),
                    from_number=(start.get("from") or start.get("caller")) or custom_parameters.get("From"),
                    to_number=(start.get("to") or start.get("called")) or custom_parameters.get("To"),
                    custom_parameters=custom_parameters,
                )
                _log_streaming(
                    f"event=start stream_sid={session.stream_sid} call_sid={session.call_sid} "
                    f"from_number={session.from_number} to_number={session.to_number}"
                )
                await websocket.send_json(
                    _build_outbound_mark_message(stream_sid=session.stream_sid, mark_name="stream-started")
                )
                continue

            if event_type == "media":
                media = payload.get("media") or {}
                current_stream_sid = str(payload.get("streamSid") or current_stream_sid or "unknown-stream")
                session = streaming_session_store.get(current_stream_sid)
                if session is None:
                    session = streaming_session_store.create_connected_placeholder(current_stream_sid)
                session.record_event("media")
                raw_payload = str(media.get("payload") or "")
                raw_audio = stt_adapter.decode_payload_to_pcm16_16khz(raw_payload)
                session.record_media_chunk(len(raw_audio) // 4 if raw_audio else 0)
                session.append_audio_bytes(raw_audio)
                _log_streaming(
                    f"event=media stream_sid={session.stream_sid} call_sid={session.call_sid} "
                    f"raw_payload_bytes={len(raw_payload)} pcm_bytes={len(raw_audio)}"
                )
                transcript_text = None
                audio_chunk = session.consume_audio_chunk(TRANSCRIBE_BUFFER_BYTES)
                if audio_chunk:
                    try:
                        transcript_text = stt_adapter.transcribe_buffer(session, audio_chunk)
                    except Exception as exc:
                        _log_streaming(
                            f"event=stt_error stream_sid={session.stream_sid} "
                            f"call_sid={session.call_sid} error={exc}"
                        )
                        transcript_text = None
                    if transcript_text:
                        _log_streaming(
                            f"event=transcript stream_sid={session.stream_sid} "
                            f"call_sid={session.call_sid} transcript={transcript_text!r}"
                        )
                    else:
                        _log_streaming(
                            f"event=transcript stream_sid={session.stream_sid} "
                            f"call_sid={session.call_sid} transcript=None"
                        )
                reply_plan = maybe_transcript_to_reply(session, transcript_text)
                await websocket.send_json(
                    _build_outbound_mark_message(stream_sid=session.stream_sid, mark_name="media-received")
                )
                if reply_plan.reply_text:
                    _log_streaming(
                        f"event=reply stream_sid={session.stream_sid} call_sid={session.call_sid} "
                        f"intent={reply_plan.intent} fallback_used={str(reply_plan.fallback_used).lower()} "
                        f"reply={reply_plan.reply_text!r}"
                    )
                    try:
                        audio_bytes = tts_adapter.synthesize_mulaw(reply_plan.reply_text)
                    except Exception as exc:
                        _log_streaming(
                            f"event=tts_error stream_sid={session.stream_sid} "
                            f"call_sid={session.call_sid} error={exc}"
                        )
                        audio_bytes = None
                    if audio_bytes:
                        await websocket.send_json(_build_outbound_media_message(stream_sid=session.stream_sid, audio_bytes=audio_bytes))
                        _log_streaming(
                            f"event=outbound_audio stream_sid={session.stream_sid} "
                            f"call_sid={session.call_sid} audio_bytes={len(audio_bytes)}"
                        )
                        await websocket.send_json(
                            _build_outbound_mark_message(stream_sid=session.stream_sid, mark_name="reply-sent")
                        )
                continue

            if event_type == "mark":
                current_stream_sid = str(payload.get("streamSid") or current_stream_sid or "unknown-stream")
                session = streaming_session_store.get(current_stream_sid)
                if session is not None:
                    session.record_event("mark")
                    await websocket.send_json(
                        _build_outbound_mark_message(stream_sid=session.stream_sid, mark_name="mark-received")
                    )
                _log_streaming(f"event=mark stream_sid={current_stream_sid}")
                continue

            if event_type == "stop":
                stop = payload.get("stop") or {}
                current_stream_sid = str(stop.get("streamSid") or payload.get("streamSid") or current_stream_sid or "unknown-stream")
                session = streaming_session_store.remove(current_stream_sid)
                _log_streaming(
                    f"event=stop stream_sid={current_stream_sid} "
                    f"media_chunks={session.media_chunk_count if session else 0} "
                    f"audio_bytes={session.total_audio_bytes if session else 0}"
                )
                await websocket.close(code=1000)
                return

            _log_streaming(f"event=ignored type={event_type!r}")
    except WebSocketDisconnect:
        if current_stream_sid:
            streaming_session_store.remove(current_stream_sid)
