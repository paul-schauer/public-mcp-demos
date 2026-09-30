import os
import json
import asyncio
import uuid
from typing import Any, Optional, Dict

from fastapi import FastAPI, Request, Response, Header, HTTPException, Query
from fastapi.responses import StreamingResponse, JSONResponse
import importlib
import logging

# Import the RDKit MCP server module lazily inside the POST handler.
mcp_module = None

# Simple logger
logger = logging.getLogger("adapter-http")
logger.addHandler(logging.StreamHandler())
logger.setLevel(logging.INFO)

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
        logger.info(f"Created session {sid}")
        return JSONResponse({"session": sid})

    # If a session id provided, return a streaming response
    sid = mcp_session_id
    if sid not in sessions:
        # create the session if it doesn't exist yet
        sessions[sid] = asyncio.Queue()
        logger.info(f"Opened SSE for session {sid}")

    headers = {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(sse_generator(sid), headers=headers)


@api.post("/mcp")
async def mcp_post(request: Request, authorization: Optional[str] = Header(default=None), mcp_session_id: Optional[str] = Header(default=None)):
    """Accepts MCP JSON-RPC requests and forwards it to the session queue or MCP handler."""
    _auth(authorization)
    # Read body safely
    try:
        body = await request.json()
    except Exception:
        body = None

    # Lightweight request log (don't log Authorization header)
    headers = {k: v for k, v in request.headers.items() if k.lower() != "authorization"}
    logger.info(f"POST /mcp headers={headers} body={str(body)[:1000]}")

    # Lazy import of MCP module if not loaded yet.
    global mcp_module
    if mcp_module is None:
        try:
            mcp_module = importlib.import_module("rdkit_mcp_server")
            logger.info("Imported rdkit_mcp_server module")
        except BaseException as exc:
            logger.warning(f"Could not import rdkit_mcp_server: {exc}")
            mcp_module = None

    # If import failed, return an explicit error explaining why MCP functionality
    # is unavailable.
    if mcp_module is None:
        return JSONResponse({
            "ok": False,
            "error": "MCP module unavailable",
            "details": "Could not import rdkit_mcp_server. Ensure RDKit is installed (pip install rdkit)."
        }, status_code=500)

    # If the MCP module exposes a handler `handle_http_envelope`, prefer that
    if mcp_module and hasattr(mcp_module, "handle_http_envelope"):
        import traceback
        handler = getattr(mcp_module, "handle_http_envelope")
        try:
            # If it's async, await it
            if asyncio.iscoroutinefunction(handler):
                resp = await handler(body)
            else:
                resp = handler(body)
        except Exception as exc:
            tb = traceback.format_exc()
            # Return an informative JSON error so callers (and logs) can see the cause
            return JSONResponse({"ok": False, "error": str(exc), "traceback": tb}, status_code=500)

        # Normalize the handler response so it's safe to JSON-encode and to push
        # into the SSE queue. If it's not serializable, fall back to a string.
        try:
            # Try serializing to ensure it's safe
            json.dumps(resp)
            resp_safe = resp
        except Exception:
            resp_safe = {"unserializable_result": str(resp)}

        # If a session id was provided and a session queue exists, push the
        # handler response (safe version) into the queue so any SSE client receives it.
        sid = mcp_session_id
        if sid and sid in sessions:
            try:
                await sessions[sid].put(resp_safe)
            except Exception:
                # best-effort: ignore queue push failures
                pass

        return JSONResponse(resp_safe)

    # Fallback
    return JSONResponse({"ok": True, "echo": body})


@api.get("/healthz")
async def healthz():
    """Simple health endpoint for platform readiness checks."""
    return Response("", status_code=200)


@api.get("/mcp_status")
async def mcp_status():
    """Return minimal status about the MCP module and RDKit availability.

    Use this to confirm whether the module was imported and whether
    RDKit is available.
    """
    mod_loaded = False
    rdkit_available = False
    if mcp_module is not None:
        mod_loaded = True
        try:
            rdkit_available = getattr(mcp_module, "RDKIT_AVAILABLE", False)
        except Exception:
            pass

    return JSONResponse({
        "mcp_module_loaded": mod_loaded,
        "rdkit_available": rdkit_available,
    })


@api.get("/sse")
async def sse_get(
    request: Request,
    authorization: Optional[str] = Header(default=None),
    mcp_session_id: Optional[str] = Header(default=None),
    sessionId: Optional[str] = Query(default=None),
):
    """Standard SSE endpoint used by many MCP clients (e.g. n8n expects /sse).

    If a session id is provided via header `mcp-session-id` or query `sessionId`,
    attach to that session; otherwise create a new session. Emits an initial
    event with the session id so clients can reference it for POST messages.
    """
    _auth(authorization)

    # Determine or create session id
    sid = mcp_session_id or sessionId or uuid.uuid4().hex
    if sid not in sessions:
        sessions[sid] = asyncio.Queue()
        logger.info(f"Created SSE session {sid}")

    async def generator_with_session(sid_local: str):
        # Send initial session event so clients know the id
        yield f"event: session\n"
        yield f"data: {json.dumps({'session': sid_local})}\n\n"
        # Then continue normal streaming
        async for chunk in sse_generator(sid_local):
            yield chunk

    headers = {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(generator_with_session(sid), headers=headers)


@api.post("/messages")
async def messages_post(
    request: Request,
    authorization: Optional[str] = Header(default=None),
    mcp_session_id: Optional[str] = Header(default=None),
):
    """Alias for POST /mcp to support standard MCP client expectations."""
    return await mcp_post(request, authorization, mcp_session_id)
