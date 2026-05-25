from __future__ import annotations

from fastapi import APIRouter, Request, WebSocket
from fastapi.responses import Response
from twilio.twiml.voice_response import Connect, Stream, VoiceResponse

from ..config import settings
from .bridge import OpenAIRealtimeBridge

realtime_router = APIRouter()
realtime_bridge = OpenAIRealtimeBridge()


def _build_realtime_websocket_url(request: Request) -> str:
    forwarded_proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    ws_scheme = "wss" if forwarded_proto == "https" else "ws"
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    return f"{ws_scheme}://{host}{settings.openai_realtime_ws_path}"


def _build_realtime_twiml(request: Request) -> str:
    response = VoiceResponse()
    connect = Connect()
    connect.append(Stream(url=_build_realtime_websocket_url(request)))
    response.append(connect)
    return str(response)


def _build_disabled_twiml() -> str:
    response = VoiceResponse()
    response.say("The OpenAI Realtime experiment is not enabled.")
    response.hangup()
    return str(response)


@realtime_router.post(settings.openai_realtime_route)
async def voice_realtime(request: Request):
    if not settings.enable_openai_realtime_experiment:
        return Response(content=_build_disabled_twiml(), media_type="application/xml")
    return Response(content=_build_realtime_twiml(request), media_type="application/xml")


@realtime_router.websocket(settings.openai_realtime_ws_path)
async def openai_realtime_websocket(websocket: WebSocket):
    await websocket.accept()
    if not settings.enable_openai_realtime_experiment:
        await websocket.close(code=1008)
        return
    await realtime_bridge.handle(websocket)
