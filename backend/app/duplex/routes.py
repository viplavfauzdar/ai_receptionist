from __future__ import annotations

from fastapi import APIRouter, Request, WebSocket
from fastapi.responses import Response
from twilio.twiml.voice_response import Connect, Stream, VoiceResponse

from .runtime import VoiceDuplexRuntime

duplex_router = APIRouter()
duplex_runtime = VoiceDuplexRuntime()
VOICE_DUPLEX_ROUTE = "/voice-duplex"
VOICE_DUPLEX_WS_PATH = "/ws/voice-duplex"


def _build_duplex_websocket_url(request: Request) -> str:
    forwarded_proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    ws_scheme = "wss" if forwarded_proto == "https" else "ws"
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    return f"{ws_scheme}://{host}{VOICE_DUPLEX_WS_PATH}"


def _build_duplex_twiml(request: Request) -> str:
    response = VoiceResponse()
    connect = Connect()
    connect.append(Stream(url=_build_duplex_websocket_url(request)))
    response.append(connect)
    return str(response)


@duplex_router.post(VOICE_DUPLEX_ROUTE)
async def voice_duplex(request: Request):
    return Response(content=_build_duplex_twiml(request), media_type="application/xml")


@duplex_router.websocket(VOICE_DUPLEX_WS_PATH)
async def voice_duplex_websocket(websocket: WebSocket):
    await websocket.accept()
    await duplex_runtime.handle_websocket(websocket)
