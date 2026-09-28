import asyncio
import json
from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from .runtime import get_runtime
from .contracts import TERMINAL
from .telemetry.events import VISIBLE_EVENT_KINDS

router = APIRouter(prefix="/agent", tags=["Agent"])


class Prompt(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class Approval(BaseModel):
    digest: str = Field(min_length=64, max_length=64)
    allow: bool


def authorize(sid, authorization):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Session capability required")
    runtime = get_runtime()
    if not runtime.store.authenticate(sid, authorization[7:]):
        raise HTTPException(404, "Session not found")
    return runtime


@router.post("/sessions", status_code=202)
def create_session(body: Prompt):
    runtime = get_runtime()
    try:
        state, token = runtime.start_session(body.message)
    except ValueError as exc:
        raise HTTPException(429, str(exc)) from None
    return {"id": state["id"], "token": token}


@router.get("/sessions/{sid}")
def task(sid: str, authorization: str | None = Header(default=None)):
    return authorize(sid, authorization).user_view(sid)


@router.post("/sessions/{sid}/turns", status_code=202)
def turn(sid: str, body: Prompt, authorization: str | None = Header(default=None)):
    runtime = authorize(sid, authorization)
    try:
        runtime.turn(sid, body.message)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None
    return {"accepted": True}


@router.post("/sessions/{sid}/approval", status_code=202)
def approval(sid: str, body: Approval, authorization: str | None = Header(default=None)):
    runtime = authorize(sid, authorization)
    try:
        runtime.approve(sid, body.digest, body.allow)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None
    return {"accepted": True}


@router.post("/sessions/{sid}/resume", status_code=202)
def resume(sid: str, authorization: str | None = Header(default=None)):
    runtime = authorize(sid, authorization)
    try:
        runtime.resume(sid)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None
    return {"accepted": True}


@router.get("/sessions/{sid}/events")
async def events(sid: str, request: Request, after: int = 0,
                 authorization: str | None = Header(default=None)):
    runtime = authorize(sid, authorization)
    async def stream():
        cursor = max(0, after)
        ticks = 0
        while not await request.is_disconnected():
            rows = runtime.store.events(sid, cursor)
            for event in rows:
                cursor = event["id"]
                if event["kind"] not in VISIBLE_EVENT_KINDS:
                    continue
                yield f"id: {cursor}\nevent: trace\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
            if not rows and runtime.store.get(sid)["status"] in TERMINAL | {
                "awaiting_approval", "awaiting_input", "waiting",
            }:
                break
            ticks += 1
            if ticks % 40 == 0:
                yield ": keepalive\n\n"
            await asyncio.sleep(0.25)
    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})
