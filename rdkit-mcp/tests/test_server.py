import base64

from mcp import Client
from starlette.testclient import TestClient

from rdkit_mcp import server

VANILLIN = "COc1cc(C=O)ccc1O"


async def test_lists_all_tools():
    async with Client(server.mcp) as client:
        result = await client.list_tools()

    assert {t.name for t in result.tools} == {
        "analyze_molecular_properties",
        "find_similar_molecules",
        "generate_3d_structure",
        "draw_molecule",
        "check_safety_properties",
    }


async def test_analyze_tool_returns_structured_result():
    async with Client(server.mcp) as client:
        result = await client.call_tool("analyze_molecular_properties", {"smiles": VANILLIN})

    assert not result.is_error
    assert result.structured_content["molecular_formula"] == "C8H8O3"


async def test_draw_molecule_returns_image_content():
    async with Client(server.mcp) as client:
        result = await client.call_tool("draw_molecule", {"smiles": VANILLIN, "size": 200})

    image = result.content[0]
    assert image.type == "image"
    assert image.mime_type == "image/png"
    assert base64.b64decode(image.data).startswith(b"\x89PNG")


async def test_invalid_smiles_becomes_tool_error():
    async with Client(server.mcp) as client:
        result = await client.call_tool("analyze_molecular_properties", {"smiles": "not-a-molecule"})

    assert result.is_error
    assert "Invalid SMILES" in result.content[0].text


async def test_argument_limits_are_enforced():
    async with Client(server.mcp) as client:
        result = await client.call_tool(
            "find_similar_molecules", {"target_smiles": VANILLIN, "candidate_smiles": [], "threshold": 2}
        )

    assert result.is_error


INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}},
}
MCP_HEADERS = {"Accept": "application/json, text/event-stream"}


def test_http_requires_bearer_token():
    with TestClient(server.create_http_app("s3cret")) as http:
        assert http.get("/healthz").status_code == 200
        assert http.post("/mcp", json=INITIALIZE, headers=MCP_HEADERS).status_code == 401

        ok = http.post("/mcp", json=INITIALIZE, headers={**MCP_HEADERS, "Authorization": "Bearer s3cret"})
        assert ok.status_code == 200
        assert ok.json()["result"]["serverInfo"]["name"] == "rdkit"
