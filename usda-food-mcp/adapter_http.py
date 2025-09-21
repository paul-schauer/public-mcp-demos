import os
import json
import asyncio
import uuid
from typing import Dict, Any, Optional

from fastapi import FastAPI, Request, Header, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse

try:
    from usda_fdc_mcp_server import app as mcp_app
except Exception:
    mcp_app = None  # we'll fallback to echo behavior

MCP_TOKEN = os.getenv("MCP_BEARER_TOKEN")

api = FastAPI()

# Simple in-memory session store: session_id -> asyncio.Queue
sessions: Dict[str, asyncio.Queue] = {}

def _auth(auth_header: Optional[str]):
    if MCP_TOKEN:
        if not auth_header or not auth_header.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing bearer")
        if auth_header.split(" ", 1)[1].strip() != MCP_TOKEN:
            raise HTTPException(status_code=401, detail="Bad bearer")


async def sse_generator(session_id: str):
    """Yield SSE events for a session from the session queue."""
    q = sessions.get(session_id)
    if q is None:
        yield "event: error\n"
        yield f"data: {json.dumps({'error':'unknown session'})}\n\n"
        return

    # initial comment to confirm connection
    yield ": connected\n\n"
    try:
        while True:
            try:
                item = await asyncio.wait_for(q.get(), timeout=20.0)
            except asyncio.TimeoutError:
                # heartbeat
                yield ": ping\n\n"
                continue
            # item should be JSON-serializable
            data = json.dumps(item)
            yield f"data: {data}\n\n"
    finally:
        # cleanup on disconnect
        sessions.pop(session_id, None)


@api.get("/mcp")
async def mcp_get(authorization: Optional[str] = Header(default=None), mcp_session_id: Optional[str] = Header(default=None)):
    """Create or attach to an SSE session.

    If no `mcp-session-id` is provided, we create one and return JSON with the id (application/json).
    If `Accept: text/event-stream` is used by the client, they should call GET with that header and the session id to stream events.
    """
    _auth(authorization)

    # If the client is opening the SSE stream, they will include Accept: text/event-stream
    # FastAPI/uvicorn handles Accept; here we always return the session id as JSON or stream
    if not mcp_session_id:
        # create session and return JSON with id
        sid = uuid.uuid4().hex
        sessions[sid] = asyncio.Queue()
        return JSONResponse({"session": sid})

    # If a session id provided, return a streaming response
    sid = mcp_session_id
    if sid not in sessions:
        # create the session if it doesn't exist yet
        sessions[sid] = asyncio.Queue()

    headers = {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(sse_generator(sid), headers=headers)


@api.post("/messages")
async def messages(request: Request, authorization: Optional[str] = Header(default=None), mcp_session_id: Optional[str] = Header(default=None)):
    """Accepts a JSON envelope and forwards it to the session queue or MCP handler.

    If `mcp_app` exposes an HTTP envelope handler, call it. Otherwise, echo the body and push
    it into the session queue for the given session id (if present).
    """
    _auth(authorization)
    body = await request.json()

    # If the MCP app exposes a handler `handle_http_envelope`, prefer that
    if mcp_app and hasattr(mcp_app, "handle_http_envelope"):
        handler = getattr(mcp_app, "handle_http_envelope")
        # If it's async, await it
        if asyncio.iscoroutinefunction(handler):
            resp = await handler(body)
        else:
            resp = handler(body)
        return JSONResponse(resp)

    # Otherwise, echo and push to session queue if provided
    sid = mcp_session_id
    if sid and sid in sessions:
        await sessions[sid].put(body)

    return JSONResponse({"ok": True, "echo": body})
