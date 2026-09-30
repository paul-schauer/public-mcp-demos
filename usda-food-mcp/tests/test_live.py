"""Smoke tests against the real FoodData Central API. Run with ``LIVE_TESTS=1 pytest``.

Uses ``USDA_FDC_API_KEY`` if set, otherwise the rate-limited public ``DEMO_KEY``.
"""

import os

import pytest
from mcp import Client

from usda_food_mcp import server

pytestmark = pytest.mark.skipif(os.environ.get("LIVE_TESTS") != "1", reason="set LIVE_TESTS=1 to hit the real API")


@pytest.fixture(autouse=True)
def api_key(monkeypatch):
    monkeypatch.setenv("USDA_FDC_API_KEY", os.environ.get("USDA_FDC_API_KEY") or "DEMO_KEY")
    server.set_client(None)
    yield
    server.set_client(None)


async def test_search_then_get():
    async with Client(server.mcp) as client:
        search = await client.call_tool("search_foods", {"query": "cheddar cheese", "page_size": 2})
        assert not search.is_error, search.content[0].text
        fdc_id = search.structured_content["foods"][0]["fdcId"]

        food = await client.call_tool("get_food", {"fdc_id": fdc_id, "format": "abridged"})
        assert not food.is_error, food.content[0].text
        assert food.structured_content["fdcId"] == fdc_id
