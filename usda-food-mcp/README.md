# food-mcp

USDA Food Data Central MCP Server

This repository provides both Python and TypeScript implementations of an MCP server for accessing USDA Food Data Central API.

## TypeScript Version (Recommended for Railway)

The TypeScript version uses the official MCP SDK and supergateway for stable HTTP+SSE deployment.

### Requirements
- Node.js 18+
- npm

### Installation
```bash
npm install
```

### Build
```bash
npm run build
```

### Environment
- `USDA_FDC_API_KEY` - Your USDA FDC API key

### Run locally (stdio)
```bash
npm run dev
```

### Deploy on Railway
Use the Procfile with supergateway:
```
web: npx -y supergateway --stdio "node build/index.js" --port $PORT --ssePath /sse --messagePath /message --cors --healthEndpoint /healthz
```

## Python Version (Alternative)

This repository exposes your MCP tools (search_foods, get_food, get_foods, list_foods) and provides a small HTTP+SSE adapter so MCP clients (for example n8n's MCP Client Tool) can connect using the HTTP+SSE transport.

Files added/important:
- `usda_fdc_mcp_server.py` - MCP tools and `handle_http_envelope` handler.
- `adapter_http.py` - FastAPI adapter exposing `/mcp` (SSE) and `/messages` (POST) endpoints.
- `app.py` - simple entrypoint that calls `main()` in `usda_fdc_mcp_server.py`.
- `Procfile` - starts the FastAPI adapter with uvicorn (used for deployments like Railway).
- `test_streamable_handshake.py` - local test script to perform the SSE handshake.

Requirements
------------
- Python 3.8+
- Create and activate a virtualenv, then install requirements:

```powershell
& .venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Environment
-----------
- `USDA_FDC_API_KEY` (required) — your USDA FDC API key. Set this in your deployment environment (do not commit it).
- `MCP_BEARER_TOKEN` (optional) — if set, the adapter requires a Bearer token for `/mcp` and `/messages`.

Run locally (adapter)
---------------------
Start the FastAPI adapter (recommended) so HTTP+SSE clients can connect:

```powershell
& .venv\Scripts\Activate.ps1
$env:USDA_FDC_API_KEY = (Get-Content .env | Select-String 'USDA_FDC_API_KEY' | ForEach-Object { $_.ToString().Split('=',2)[1].Trim() })
uvicorn adapter_http:api --host 0.0.0.0 --port 8000 --timeout-keep-alive 120
```

The adapter will now be available at `http://127.0.0.1:8000`.

Run locally (original MCP server)
-------------------------------
If you want to run the original MCP process (not the HTTP adapter):

```powershell
python app.py
```

Endpoints (adapter)
-------------------
- `GET /mcp` — create a session (Accept: application/json, text/event-stream). Returns `{ "session": "<id>" }`.
- `GET /mcp` with header `mcp-session-id: <id>` and `Accept: text/event-stream` — open SSE stream for that session.
- `POST /messages` — send a JSON envelope. Include header `mcp-session-id: <id>` to route responses to that session.

Example sequence (curl)
------------------------
1. Create session (GET)

```bash
curl -i -H "Accept: application/json, text/event-stream" https://<your-domain>/mcp
# -> {"session":"<id>"}
```

2. POST the envelope

```bash
curl -i -X POST https://<your-domain>/messages \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "mcp-session-id: <id>" \
  -d '{"tool":"search_foods","id":"1","arguments":{"query":"cheddar cheese"}}'
```

3. Open the SSE stream (client must accept `text/event-stream`)

```bash
curl -i -N -H "Accept: text/event-stream" -H "mcp-session-id: <id>" https://<your-domain>/mcp
```

Deployment notes
----------------
- Use the included `Procfile` (or set the start command) so the platform runs the adapter:

```
web: uvicorn adapter_http:api --host 0.0.0.0 --port ${PORT:-8000} --timeout-keep-alive 120
```

- Ensure `USDA_FDC_API_KEY` is set in the deployment environment. If it is missing the original MCP server may exit.
- If you enable `MCP_BEARER_TOKEN`, set the same token in n8n's node as Bearer auth.

Troubleshooting n8n connection errors
-------------------------------------
- "Could not connect to your MCP server": usually means n8n can't reach the SSE or messages endpoint. Confirm both URLs are reachable and return 200 for the GET session and POST messages.
- Check platform logs for startup errors (missing env vars, binding errors) — ensure the adapter process is running and listening on `$PORT`.

If you provide the deployed base URL (for example `https://food-mcp-production.up.railway.app`), I can run the GET/POST checks and tell you exactly what n8n will see.

License
-------
MIT
# food-mcp
MCP Server
