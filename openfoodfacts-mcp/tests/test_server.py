import httpx
import pytest
import respx
from mcp import Client
from starlette.testclient import TestClient

from openfoodfacts_mcp import server
from openfoodfacts_mcp.client import BASE_URL, KNOWLEDGE_PANEL_URL, OFFClient

NUTELLA = "3017620422003"
PRODUCT = {
    "code": NUTELLA,
    "product_name": "Nutella",
    "brands": "Ferrero",
    "nutriscore_grade": "e",
    "nutriscore_score": 26,
    "nutriments": {"energy-kcal_100g": 539, "sugars_100g": 56.3, "fat_serving": 4.65},
    "ingredients": [{"id": "en:sugar", "text": "Sugar", "percent_estimate": 55}],
    "ingredients_analysis_tags": ["en:palm-oil", "en:non-vegan", "en:vegetarian"],
    "allergens_tags": ["en:milk", "en:nuts"],
}


@pytest.fixture(autouse=True)
async def off_client():
    client = OFFClient()
    server.set_client(client)
    yield client
    server.set_client(None)
    await client.aclose()


async def call(tool: str, args: dict):
    async with Client(server.mcp) as client:
        return await client.call_tool(tool, args)


async def test_lists_all_tools():
    async with Client(server.mcp) as client:
        tools = {t.name for t in (await client.list_tools()).tools}

    assert tools == {
        "get_product_by_barcode",
        "get_product_nutrition",
        "get_product_ingredients",
        "get_products_by_barcodes",
        "search_products",
        "advanced_search",
        "get_taxonomy_suggestions",
        "list_facets",
        "get_products_by_facets",
        "get_facet_knowledge_panel",
    }


@respx.mock
async def test_get_product_by_barcode_combines_sections():
    respx.get(f"{BASE_URL}/api/v2/product/{NUTELLA}.json").mock(
        return_value=httpx.Response(200, json={"status": 1, "product": PRODUCT})
    )

    result = (await call("get_product_by_barcode", {"barcode": NUTELLA})).structured_content

    assert result["product"]["product_name"] == "Nutella"
    assert result["nutrition"]["per_100g"]["sugars"] == 56.3
    assert result["nutrition"]["per_serving"]["fat"] == 4.65
    assert result["nutrition"]["nutriscore"] == {"grade": "e", "score": 26}
    assert result["ingredients"]["analysis"] == {
        "is_vegan": False,
        "is_vegetarian": True,
        "is_palm_oil_free": False,
        "tags": PRODUCT["ingredients_analysis_tags"],
    }


@respx.mock
async def test_unknown_barcode_is_a_tool_error():
    respx.get(f"{BASE_URL}/api/v2/product/0000000000000.json").mock(return_value=httpx.Response(404))

    result = await call("get_product_nutrition", {"barcode": "0000000000000"})

    assert result.is_error
    assert "No product found" in result.content[0].text


async def test_path_injection_is_rejected_before_any_request():
    with respx.mock(assert_all_called=False) as mock:
        result = await call("get_product_ingredients", {"barcode": "123/../../admin"})
        facets = await call("get_products_by_facets", {"facets": {"category": "../../x"}})

    assert result.is_error and "Invalid barcode" in result.content[0].text
    assert facets.is_error and "Invalid facet value" in facets.content[0].text
    assert not mock.calls


@respx.mock
async def test_search_products_passes_parameters():
    route = respx.get(f"{BASE_URL}/cgi/search.pl").mock(
        return_value=httpx.Response(200, json={"count": 1, "page": 1, "products": [PRODUCT]})
    )

    result = (await call("search_products", {"query": "nutella", "page_size": 5})).structured_content

    params = route.calls.last.request.url.params
    assert params["search_terms"] == "nutella"
    assert params["page_size"] == "5"
    assert result["products"][0]["brands"] == "Ferrero"


@respx.mock
async def test_advanced_search_maps_only_given_filters():
    route = respx.get(f"{BASE_URL}/api/v2/search").mock(return_value=httpx.Response(200, json={"products": []}))

    await call("advanced_search", {"categories": "breakfast-cereals", "nutrition_grades": "a"})

    params = route.calls.last.request.url.params
    assert params["categories_tags_en"] == "breakfast-cereals"
    assert params["nutrition_grades_tags"] == "a"
    assert "brands_tags" not in params


@respx.mock
async def test_get_products_by_barcodes_reports_missing():
    respx.get(f"{BASE_URL}/api/v2/search").mock(return_value=httpx.Response(200, json={"products": [PRODUCT]}))

    result = (await call("get_products_by_barcodes", {"barcodes": [NUTELLA, "5449000000996"]})).structured_content

    assert [p["code"] for p in result["found"]] == [NUTELLA]
    assert result["not_found"] == ["5449000000996"]


@respx.mock
async def test_get_products_by_facets_builds_path():
    route = respx.get(f"{BASE_URL}/category/breakfast-cereals/label/en:organic.json").mock(
        return_value=httpx.Response(200, json={"count": 0, "products": []})
    )

    result = await call("get_products_by_facets", {"facets": {"category": "breakfast-cereals", "label": "en:organic"}})

    assert not result.is_error
    assert route.called


@respx.mock
async def test_knowledge_panel_uses_separate_host():
    route = respx.get(KNOWLEDGE_PANEL_URL).mock(return_value=httpx.Response(200, json={"knowledge_panels": {"a": 1}}))

    result = await call("get_facet_knowledge_panel", {"facet_type": "label", "facet_value": "en:organic"})

    assert result.structured_content["panels"] == {"a": 1}
    assert route.calls.last.request.url.params["value_tag"] == "en:organic"


@respx.mock
async def test_facet_rate_limit_is_enforced_locally():
    route = respx.get(f"{BASE_URL}/labels.json").mock(return_value=httpx.Response(200, json={"tags": []}))

    results = [await call("list_facets", {"facet_type": "labels"}) for _ in range(3)]

    assert [r.is_error for r in results] == [False, False, True]
    assert "2 facet requests per 60s" in results[2].content[0].text
    assert route.call_count == 2


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
        assert ok.json()["result"]["serverInfo"]["name"] == "openfoodfacts"
