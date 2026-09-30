import httpx
import pytest
import respx
from mcp import Client
from starlette.testclient import TestClient

from usda_food_mcp import server
from usda_food_mcp.client import BASE_URL, FDCClient


@pytest.fixture(autouse=True)
async def fdc_client(monkeypatch):
    monkeypatch.delenv("USDA_FDC_API_KEY", raising=False)
    client = FDCClient("test-key")
    server.set_client(client)
    yield client
    server.set_client(None)
    await client.aclose()


async def test_lists_all_tools():
    async with Client(server.mcp) as client:
        result = await client.list_tools()

    assert {t.name for t in result.tools} == {"search_foods", "get_food", "get_foods", "list_foods"}


@respx.mock
async def test_search_foods_tool_returns_api_result():
    respx.post(f"{BASE_URL}/foods/search").mock(
        return_value=httpx.Response(200, json={"totalHits": 1, "foods": [{"fdcId": 1, "description": "Apple"}]})
    )

    async with Client(server.mcp) as client:
        result = await client.call_tool("search_foods", {"query": "apple"})

    assert not result.is_error
    assert result.structured_content["totalHits"] == 1


@respx.mock
async def test_api_errors_become_tool_errors():
    respx.get(f"{BASE_URL}/food/999").mock(return_value=httpx.Response(404))

    async with Client(server.mcp) as client:
        result = await client.call_tool("get_food", {"fdc_id": 999})

    assert result.is_error
    assert "No food found" in result.content[0].text


async def test_invalid_arguments_are_rejected():
    async with Client(server.mcp) as client:
        result = await client.call_tool("get_foods", {"fdc_ids": list(range(1, 30))})

    assert result.is_error


async def test_missing_api_key_is_reported():
    server.set_client(None)

    async with Client(server.mcp) as client:
        result = await client.call_tool("get_food", {"fdc_id": 1})

    assert result.is_error
    assert "USDA_FDC_API_KEY" in result.content[0].text


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
        wrong = {**MCP_HEADERS, "Authorization": "Bearer nope"}
        assert http.post("/mcp", json=INITIALIZE, headers=wrong).status_code == 401

        ok = http.post("/mcp", json=INITIALIZE, headers={**MCP_HEADERS, "Authorization": "Bearer s3cret"})
        assert ok.status_code == 200
        assert ok.json()["result"]["serverInfo"]["name"] == "usda-food"
