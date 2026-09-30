"""Smoke tests against the real Open Food Facts API. Run with ``LIVE_TESTS=1 pytest``."""

import os

import pytest
from mcp import Client

from openfoodfacts_mcp import server

pytestmark = pytest.mark.skipif(os.environ.get("LIVE_TESTS") != "1", reason="set LIVE_TESTS=1 to hit the real API")

NUTELLA = "3017620422003"


async def call(tool: str, args: dict):
    async with Client(server.mcp) as client:
        result = await client.call_tool(tool, args)
    assert not result.is_error, result.content[0].text
    return result.structured_content


async def test_product_lookup():
    result = await call("get_product_nutrition", {"barcode": NUTELLA})
    assert result["barcode"] == NUTELLA
    assert result["per_100g"]["sugars"] > 40


async def test_search():
    result = await call("search_products", {"query": "nutella", "page_size": 3})
    assert result["count"] > 0


async def test_advanced_search():
    result = await call("advanced_search", {"categories": "breakfast-cereals", "nutrition_grades": "a", "page_size": 3})
    assert result["count"] > 0


async def test_facets():
    labels = await call("list_facets", {"facet_type": "labels"})
    assert labels["values"]
    products = await call("get_products_by_facets", {"facets": {"label": "en:organic"}})
    assert products["count"] > 0
