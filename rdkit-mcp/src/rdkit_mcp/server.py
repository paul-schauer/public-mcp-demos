"""MCP server exposing RDKit chemistry tools for food and flavor work.

Tools are synchronous on purpose: the SDK runs them in a worker thread, so CPU-heavy
RDKit calls don't block the event loop.
"""

from __future__ import annotations

import hmac
import os
from collections.abc import Callable
from typing import Annotated, Any, TypeVar

from mcp.server.mcpserver import Image, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from rdkit_mcp import chemistry

MAX_CANDIDATES = 1000

mcp = MCPServer(
    name="rdkit",
    instructions=(
        "Cheminformatics tools for food and flavor chemistry. Every tool takes SMILES "
        "strings; get them from PubChem if you only have a compound name."
    ),
    website_url="https://www.rdkit.org/",
)

T = TypeVar("T")

Smiles = Annotated[
    str,
    Field(
        description="SMILES string, e.g. 'COc1cc(C=O)ccc1O' for vanillin",
        min_length=1,
        max_length=chemistry.MAX_SMILES_LENGTH,
    ),
]


def _run(fn: Callable[..., T], *args: Any) -> T:
    try:
        return fn(*args)
    except ValueError as exc:
        raise ToolError(str(exc)) from None


@mcp.tool()
def analyze_molecular_properties(smiles: Smiles) -> dict[str, Any]:
    """Compute LogP, molecular weight, H-bond donors/acceptors, TPSA and rotatable bonds,
    plus a rough guide to whether the compound extracts best in water, alcohol or fat."""
    return _run(chemistry.analyze_properties, smiles)


@mcp.tool()
def find_similar_molecules(
    target_smiles: Smiles,
    candidate_smiles: Annotated[list[str], Field(max_length=MAX_CANDIDATES)],
    threshold: Annotated[float, Field(ge=0, le=1, description="Minimum Tanimoto similarity")] = 0.7,
) -> dict[str, Any]:
    """Rank candidates by structural similarity to a target (Morgan fingerprints, Tanimoto).
    Useful for finding flavor substitutes. Invalid candidate SMILES are reported, not fatal."""
    return _run(chemistry.find_similar, target_smiles, candidate_smiles, threshold)


@mcp.tool()
def generate_3d_structure(smiles: Smiles) -> dict[str, Any]:
    """Generate a force-field-optimized 3D conformer and return it as a MOL block."""
    return _run(chemistry.generate_3d, smiles)


@mcp.tool()
def draw_molecule(
    smiles: Smiles,
    size: Annotated[int, Field(ge=100, le=1000, description="Image width and height in pixels")] = 400,
) -> Image:
    """Render a 2D structure diagram as a PNG image."""
    return Image(data=_run(chemistry.draw_png, smiles, size), format="png")


@mcp.tool()
def check_safety_properties(smiles: Smiles) -> dict[str, Any]:
    """Screen a compound for properties worth a closer look (QED drug-likeness, size,
    lipophilicity, structural alerts). A starting point for research, not a safety verdict."""
    return _run(chemistry.screen_properties, smiles)


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
            "Refusing to serve HTTP without MCP_BEARER_TOKEN, since anyone could use the "
            "server's CPU. Set ALLOW_UNAUTHENTICATED=1 to override for local testing."
        )
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(create_http_app(token), host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
