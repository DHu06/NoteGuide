"""NoteGuide verification API.

Two ways in, same verifier behind both:
  POST /verify          one-shot, easy to curl and to test
  WS   /ws/verify       the flowchart's path — the editor holds this open
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError

from .explain import build_verdict
from .models import VerifyRequest, Verdict, WSError
from .verifier import check_step

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("noteguide")

app = FastAPI(title="NoteGuide", version="0.1.0")

# The editor shell is opened from disk during development, which sends
# `Origin: null`. Tighten this to the real origin before deploying.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


async def verify(request: VerifyRequest) -> Verdict:
    # SymPy is synchronous and CPU-bound; keep it off the event loop.
    result = await asyncio.to_thread(check_step, request.text, request.previous)
    return await build_verdict(request.step_id, result)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/verify", response_model=Verdict)
async def verify_endpoint(request: VerifyRequest) -> Verdict:
    return await verify(request)


@app.websocket("/ws/verify")
async def verify_socket(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        while True:
            payload = await websocket.receive_json()
            try:
                request = VerifyRequest.model_validate(payload)
            except ValidationError as exc:
                await websocket.send_json(
                    WSError(message=f"Invalid request: {exc.error_count()} problem(s)").model_dump()
                )
                continue

            try:
                verdict = await verify(request)
            except Exception:
                # One bad step must not tear down the student's whole session.
                log.exception("Verification failed for step %s", request.step_id)
                await websocket.send_json(
                    Verdict(
                        step_id=request.step_id,
                        status="uncertain",
                        confidence=0.0,
                        short="Verifier error",
                        details="Something went wrong while checking this step.",
                        source="error",
                    ).model_dump()
                )
                continue

            await websocket.send_json(verdict.model_dump())
    except WebSocketDisconnect:
        return
