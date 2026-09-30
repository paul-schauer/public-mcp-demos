"""MCP server exposing USDA FoodData Central search and lookup tools.

Run over stdio (for Claude Desktop and other local clients) or Streamable HTTP
(for remote clients such as n8n). See the README for configuration.
"""

from __future__ import annotations

import hmac
import os
from typing import Annotated, Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from usda_food_mcp.client import (
    MAX_IDS_PER_REQUEST,
    MAX_PAGE_SIZE,
    DataType,
    FDCClient,
    FDCError,
    Format,
    SortOrder,
)

mcp = MCPServer(
    name="usda-food",
    instructions=(
        "Look up nutrition data from USDA FoodData Central. Use search_foods to find "
        "a food's FDC ID, then get_food or get_foods for its full nutrient profile."
    ),
    website_url="https://fdc.nal.usda.gov/",
)

_client: FDCClient | None = None


def get_client() -> FDCClient:
    """Return the shared FDC client, creating it from ``USDA_FDC_API_KEY`` on first use."""
    global _client
    if _client is None:
        api_key = os.environ.get("USDA_FDC_API_KEY")
        if not api_key:
            raise ToolError("USDA_FDC_API_KEY is not set. Get a free key at https://fdc.nal.usda.gov/api-key-signup")
        _client = FDCClient(api_key)
    return _client


def set_client(client: FDCClient | None) -> None:
    """Replace the shared client (used by tests)."""
    global _client
    _client = client


async def _call(coro: Any) -> Any:
    try:
        return await coro
    except (FDCError, ValueError) as exc:
        raise ToolError(str(exc)) from None


FdcId = Annotated[int, Field(description="FoodData Central ID, e.g. 171705", gt=0)]
Nutrients = Annotated[
    list[int] | None,
    Field(description="Only return these nutrient numbers, e.g. [203, 204, 205] for protein, fat, carbs"),
]
DataTypes = Annotated[list[DataType] | None, Field(description="Restrict to these FDC data types")]
PageSize = Annotated[int, Field(ge=1, le=MAX_PAGE_SIZE)]
PageNumber = Annotated[int, Field(ge=1)]


@mcp.tool()
async def search_foods(
    query: Annotated[str, Field(description="Keywords, e.g. 'cheddar cheese'", min_length=1)],
    data_type: DataTypes = None,
    page_size: PageSize = 25,
    page_number: PageNumber = 1,
    sort_by: Annotated[
        str | None, Field(description="dataType.keyword, lowercaseDescription.keyword, fdcId or publishedDate")
    ] = None,
    sort_order: SortOrder | None = None,
    brand_owner: Annotated[str | None, Field(description="Branded foods only: filter by brand owner")] = None,
) -> dict[str, Any]:
    """Search FoodData Central by keyword and return matching foods with their FDC IDs."""
    return await _call(
        get_client().search_foods(query, data_type, page_size, page_number, sort_by, sort_order, brand_owner)
    )


@mcp.tool()
async def get_food(fdc_id: FdcId, format: Format = "full", nutrients: Nutrients = None) -> dict[str, Any]:
    """Get the full record, including nutrients, for one food by FDC ID."""
    return await _call(get_client().get_food(fdc_id, format, nutrients))


@mcp.tool()
async def get_foods(
    fdc_ids: Annotated[list[int], Field(min_length=1, max_length=MAX_IDS_PER_REQUEST)],
    format: Format = "full",
    nutrients: Nutrients = None,
) -> list[dict[str, Any]]:
    """Get records for up to 20 foods at once by FDC ID."""
    return await _call(get_client().get_foods(fdc_ids, format, nutrients))


@mcp.tool()
async def list_foods(
    data_type: DataTypes = None,
    page_size: PageSize = 25,
    page_number: PageNumber = 1,
    sort_by: str | None = None,
    sort_order: SortOrder | None = None,
) -> list[dict[str, Any]]:
    """Page through foods in abridged form, optionally filtered by data type."""
    return await _call(get_client().list_foods(data_type, page_size, page_number, sort_by, sort_order))


@mcp.custom_route("/healthz", methods=["GET"])
async def healthz(_: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


class BearerAuthMiddleware:
    """Require ``Authorization: Bearer <token>`` on every HTTP request except health checks."""

    def __init__(self, app: ASGIApp, token: str, public_paths: frozenset[str] = frozenset({"/healthz"})) -> None:
        self.app = app
        self.expected = f"Bearer {token}".encode()
        self.public_paths = public_paths

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["path"] not in self.public_paths:
            provided = dict(scope["headers"]).get(b"authorization", b"")
            if not hmac.compare_digest(provided, self.expected):
                response = JSONResponse(
                    {"error": "unauthorized"}, status_code=401, headers={"WWW-Authenticate": "Bearer"}
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


def create_http_app(token: str | None = None) -> ASGIApp:
    """Build the Streamable HTTP app served at ``/mcp``, behind bearer auth when a token is set."""
    app: ASGIApp = mcp.streamable_http_app(host="0.0.0.0", stateless_http=True, json_response=True)
    return BearerAuthMiddleware(app, token) if token else app


def main() -> None:
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    if transport == "stdio":
        mcp.run("stdio")
        return
    if transport != "http":
        raise SystemExit(f"Unknown MCP_TRANSPORT {transport!r}; use 'stdio' or 'http'")

    import uvicorn

    token = os.environ.get("MCP_BEARER_TOKEN")
    if not token and os.environ.get("ALLOW_UNAUTHENTICATED") != "1":
        raise SystemExit(
            "Refusing to serve HTTP without MCP_BEARER_TOKEN, since anyone could spend your "
            "USDA API quota. Set ALLOW_UNAUTHENTICATED=1 to override for local testing."
        )
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(create_http_app(token), host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
