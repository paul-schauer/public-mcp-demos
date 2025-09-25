import os
import json
import asyncio
from typing import Any, Optional

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

def _auth(auth_header: Optional[str]):
    if MCP_TOKEN:
        if not auth_header or not auth_header.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing bearer")
        if auth_header.split(" ", 1)[1].strip() != MCP_TOKEN:
            raise HTTPException(status_code=401, detail="Bad bearer")


async def sse_generator():
    """Yield SSE events for heartbeat."""
    # initial comment to confirm connection
    yield ": connected\n\n"
    try:
        while True:
            try:
                # heartbeat every 20 seconds
                await asyncio.sleep(20.0)
                yield ": ping\n\n"
            except asyncio.CancelledError:
                break
    finally:
        pass


@api.get("/mcp")
async def mcp_get(authorization: Optional[str] = Header(default=None)):
    """Return SSE stream for MCP notifications (heartbeat only)."""
    _auth(authorization)

    headers = {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(sse_generator(), headers=headers)


@api.post("/mcp")
async def mcp_post(request: Request, authorization: Optional[str] = Header(default=None)):
    """Accepts MCP JSON-RPC requests and returns responses."""
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

        # Normalize the handler response so it's safe to JSON-encode
        try:
            json.dumps(resp)
            resp_safe = resp
        except Exception:
            resp_safe = {"unserializable_result": str(resp)}

        return JSONResponse(resp_safe)

    # Fallback
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


async def handle_http_envelope(envelope: dict) -> dict:
    """Handle an incoming MCP JSON-RPC envelope.

    Supports standard MCP protocol messages: initialize, tools/list, tools/call.
    """
    # Validate JSON-RPC 2.0 format
    if envelope.get("jsonrpc") != "2.0":
        return {"jsonrpc": "2.0", "id": envelope.get("id"), "error": {"code": -32600, "message": "Invalid Request"}}

    method = envelope.get("method")
    req_id = envelope.get("id")
    params = envelope.get("params") or {}

    if method == "initialize":
        # Return server capabilities
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {"listChanged": False}
                },
                "serverInfo": {
                    "name": "usda-fdc-mcp",
                    "version": "1.0.0"
                }
            }
        }

    elif method == "tools/list":
        # Return list of available tools
        tools = [
            {
                "name": "get_food",
                "description": "Get details for a single food item by FDC ID.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "fdc_id": {"type": "string", "description": "The FDC ID of the food item"},
                        "format_type": {"type": "string", "enum": ["abridged", "full"], "default": "full", "description": "Format of the response"},
                        "nutrients": {"type": "array", "items": {"type": "integer"}, "description": "List of nutrient IDs to include"}
                    },
                    "required": ["fdc_id"]
                }
            },
            {
                "name": "get_foods",
                "description": "Get details for multiple food items by FDC IDs.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "fdc_ids": {"type": "array", "items": {"type": "string"}, "description": "List of FDC IDs"},
                        "format_type": {"type": "string", "enum": ["abridged", "full"], "default": "full"},
                        "nutrients": {"type": "array", "items": {"type": "integer"}}
                    },
                    "required": ["fdc_ids"]
                }
            },
            {
                "name": "search_foods",
                "description": "Search for foods using keywords.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query"},
                        "data_type": {"type": "array", "items": {"type": "string"}, "description": "Data types to search"},
                        "page_size": {"type": "integer", "default": 50, "minimum": 1, "maximum": 200},
                        "page_number": {"type": "integer", "default": 1, "minimum": 1},
                        "sort_by": {"type": "string"},
                        "sort_order": {"type": "string", "enum": ["asc", "desc"]},
                        "brand_owner": {"type": "string"}
                    },
                    "required": ["query"]
                }
            },
            {
                "name": "list_foods",
                "description": "Get a paged list of foods.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "data_type": {"type": "array", "items": {"type": "string"}},
                        "page_size": {"type": "integer", "default": 50, "minimum": 1, "maximum": 200},
                        "page_number": {"type": "integer", "default": 1, "minimum": 1},
                        "sort_by": {"type": "string"},
                        "sort_order": {"type": "string", "enum": ["asc", "desc"]}
                    }
                }
            }
        ]
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": tools}
        }

    elif method == "tools/call":
        # Call a tool
        tool_name = params.get("name")
        args = params.get("arguments") or {}

        global mcp_module
        if mcp_module is None or not hasattr(mcp_module, tool_name):
            return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": "Method not found"}}

        fn = getattr(mcp_module, tool_name)

        try:
            result = await fn(**args) if asyncio.iscoroutinefunction(fn) else fn(**args)
            return {"jsonrpc": "2.0", "id": req_id, "result": result}
        except Exception as e:
            return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32000, "message": str(e)}}

    else:
        return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": "Method not found"}}
