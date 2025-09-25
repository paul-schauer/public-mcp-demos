import os
import json
import asyncio
import uuid
from typing import Dict, Any, Optional

from fastapi import FastAPI, Request, Header, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
import importlib
import logging

# We'll import the MCP server module lazily inside the POST handler. Importing
# it at module load can run top-level code in `usda_fdc_mcp_server.py` which
# exits when `USDA_FDC_API_KEY` is missing. Lazy import avoids crashing the
# adapter at startup and lets us handle missing env vars gracefully.
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


@api.post("/messages")
async def messages(request: Request, authorization: Optional[str] = Header(default=None), mcp_session_id: Optional[str] = Header(default=None)):
    """Accepts a JSON envelope and forwards it to the session queue or MCP handler.

    If `mcp_app` exposes an HTTP envelope handler, call it. Otherwise, echo the body and push
    it into the session queue for the given session id (if present).
    """
    _auth(authorization)
    # Read body safely
    try:
        body = await request.json()
    except Exception:
        body = None

    # Lightweight request log (don't log Authorization header)
    headers = {k: v for k, v in request.headers.items() if k.lower() != "authorization"}
    logger.info(f"POST /messages headers={headers} body={str(body)[:1000]}")

    # Lazy import of MCP module if not loaded yet.
    global mcp_module
    if mcp_module is None:
        try:
            mcp_module = importlib.import_module("usda_fdc_mcp_server")
            logger.info("Imported usda_fdc_mcp_server module")
            # If the MCP module defines an FDCAPIClient and an api_key but has no
            # initialized `fdc_client`, initialize it here so tool functions can
            # call the USDA API without needing to run the MCP `main()` process.
            try:
                if getattr(mcp_module, "fdc_client", None) is None and hasattr(mcp_module, "FDCAPIClient") and getattr(mcp_module, "api_key", None):
                    try:
                        # Create and assign the client instance
                        mcp_module.fdc_client = mcp_module.FDCAPIClient(mcp_module.api_key)
                        logger.info("Initialized FDCAPIClient in MCP module")
                    except Exception as e:
                        logger.warning(f"Failed to initialize FDCAPIClient: {e}")
            except Exception:
                # non-fatal; proceed without client initialization
                pass
        except BaseException as exc:
            # Catch BaseException to avoid SystemExit from the MCP module killing
            # the adapter (the module may call exit() when API key is missing).
            logger.warning(f"Could not import usda_fdc_mcp_server: {exc}")
            mcp_module = None

    # If import failed, return an explicit error explaining why MCP functionality
    # is unavailable. This helps deployments like Railway surface the issue to
    # callers such as n8n instead of silently echoing the envelope.
    if mcp_module is None:
        return JSONResponse({
            "ok": False,
            "error": "MCP module unavailable",
            "details": "Could not import usda_fdc_mcp_server. Ensure USDA_FDC_API_KEY is set in the environment and the MCP module can initialize."
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

    # Otherwise, echo and push to session queue if provided
    sid = mcp_session_id
    if sid and sid in sessions:
        await sessions[sid].put(body)

    return JSONResponse({"ok": True, "echo": body})


@api.get("/healthz")
async def healthz():
    """Simple health endpoint for platform readiness checks."""
    return JSONResponse({"ok": True, "status": "ready"})


@api.get("/mcp_status")
async def mcp_status():
    """Return minimal status about the MCP module and FDC client.

    This returns booleans only and does NOT expose the API key.
    Use this to confirm whether the module was imported and whether the
    FDC client was initialized.
    """
    mod_loaded = False
    has_api_key = False
    client_initialized = False
    if mcp_module is not None:
        mod_loaded = True
        try:
            has_api_key = bool(getattr(mcp_module, "api_key", None))
            client_initialized = getattr(mcp_module, "fdc_client", None) is not None
        except Exception:
            pass

    return JSONResponse({
        "mcp_module_loaded": mod_loaded,
        "has_api_key": has_api_key,
        "fdc_client_initialized": client_initialized,
    })
