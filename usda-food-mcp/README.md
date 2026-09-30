# usda-food-mcp

An [MCP](https://modelcontextprotocol.io) server that gives AI assistants access to
[USDA FoodData Central](https://fdc.nal.usda.gov/), the U.S. government's nutrition
database of 400k+ foods. You can ask Claude "how much protein is in 100 g of cheddar?"
and it looks up the real data rather than guessing.

## Tools

| Tool | What it does |
| --- | --- |
| `search_foods` | Keyword search, with optional filters for data type and brand owner. Returns FDC IDs. |
| `get_food` | Full record for one food, optionally limited to specific nutrients. |
| `get_foods` | Records for up to 20 foods in one call. |
| `list_foods` | Page through foods in abridged form. |

Tool inputs are validated from type hints (ranges, enums, list lengths), so an assistant
gets a clear error for bad arguments before any API call is made.

## Quick start

You need Python 3.11+ and a free API key from https://fdc.nal.usda.gov/api-key-signup
(`DEMO_KEY` also works for light testing).

```bash
cd usda-food-mcp
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest
```

### Use with Claude Desktop (stdio)

Add this to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "usda-food": {
      "command": "/path/to/usda-food-mcp/.venv/bin/usda-food-mcp",
      "env": { "USDA_FDC_API_KEY": "your-key" }
    }
  }
}
```

### Run as a remote server (Streamable HTTP)

```bash
export USDA_FDC_API_KEY=your-key MCP_BEARER_TOKEN=$(openssl rand -hex 32)
MCP_TRANSPORT=http usda-food-mcp          # serves http://0.0.0.0:8000/mcp
```

Or with Docker:

```bash
docker build -t usda-food-mcp .
docker run -p 8000:8000 -e USDA_FDC_API_KEY -e MCP_BEARER_TOKEN usda-food-mcp
```

Point any Streamable HTTP client (Claude, n8n's MCP Client node, MCP Inspector) at
`http://<host>:8000/mcp` with the header `Authorization: Bearer <token>`.
`GET /healthz` is left unauthenticated for platform health checks.

| Variable | Default | Purpose |
| --- | --- | --- |
| `USDA_FDC_API_KEY` | required | FoodData Central API key |
| `MCP_TRANSPORT` | `stdio` (`http` in Docker) | `stdio` or `http` |
| `MCP_BEARER_TOKEN` | required for `http` | Shared secret that clients send as a bearer token |
| `PORT` | `8000` | HTTP port |
| `ALLOW_UNAUTHENTICATED` | unset | Set to `1` to serve HTTP without a token (local testing only) |

## Design notes

- **Built on the official MCP Python SDK.** Tool schemas come from the function signatures,
  and the SDK handles the protocol and transport.
- **The API key never leaves the server.** It goes in the `X-Api-Key` header rather than
  the query string, so it can't appear in logged URLs. Upstream errors are mapped to
  short messages (not found, rejected key, rate limited) instead of passing through raw
  responses or tracebacks.
- **The HTTP server is stateless.** Each request is independent, so nothing builds up in
  memory and it scales horizontally. It refuses to start without a bearer token, because
  an open endpoint would let anyone use your API quota.
- **Tests make no network calls.** The HTTP layer is mocked with `respx`, and the tools
  are exercised through a real in-process MCP client.

## History

I first built this in August–September 2025 to give an n8n agent nutrition lookups,
deployed on Railway. That version hand-rolled the MCP JSON-RPC and SSE handling in a
FastAPI adapter to match what n8n expected at the time. The commit history shows
that iteration, including a short-lived TypeScript port.

In September 2026 I came back to it and rewrote it on MCP SDK v2 (which also fixed a
build break, since the old unpinned `mcp>=1.0` dependency now resolved to v2). The rewrite
closed the security gaps (tracebacks returned to callers, a timing-unsafe token check,
unbounded sessions) and added tests, CI and packaging.

## License

MIT, see [LICENSE](LICENSE).
