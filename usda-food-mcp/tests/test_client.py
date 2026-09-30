import httpx
import pytest
import respx

from usda_food_mcp.client import BASE_URL, FDCClient, FDCError


@pytest.fixture
async def client():
    c = FDCClient("secret-key")
    yield c
    await c.aclose()


@respx.mock
async def test_api_key_sent_as_header_not_query(client):
    route = respx.get(f"{BASE_URL}/food/171705").mock(return_value=httpx.Response(200, json={"fdcId": 171705}))

    assert await client.get_food(171705) == {"fdcId": 171705}

    request = route.calls.last.request
    assert request.headers["X-Api-Key"] == "secret-key"
    assert "secret-key" not in str(request.url)
    assert request.url.params["format"] == "full"


@respx.mock
async def test_get_food_joins_nutrients(client):
    route = respx.get(f"{BASE_URL}/food/1").mock(return_value=httpx.Response(200, json={}))

    await client.get_food(1, "abridged", [203, 204])

    assert route.calls.last.request.url.params["nutrients"] == "203,204"


@respx.mock
async def test_search_builds_body_and_clamps_page_size(client):
    route = respx.post(f"{BASE_URL}/foods/search").mock(return_value=httpx.Response(200, json={"foods": []}))

    await client.search_foods("apple", ["Foundation"], page_size=999, brand_owner="Acme")

    body = route.calls.last.request.read()
    assert b'"pageSize":200' in body
    assert b'"query":"apple"' in body
    assert b'"dataType":["Foundation"]' in body
    assert b'"brandOwner":"Acme"' in body


async def test_get_foods_rejects_too_many_ids(client):
    with pytest.raises(ValueError, match="At most 20"):
        await client.get_foods(list(range(1, 22)))


@respx.mock
@pytest.mark.parametrize(
    ("status", "message"),
    [(404, "No food found"), (403, "rejected the API key"), (429, "rate limit"), (500, "HTTP 500")],
)
async def test_errors_are_mapped_and_never_leak_the_key(client, status, message):
    respx.get(f"{BASE_URL}/food/1").mock(return_value=httpx.Response(status, text="details"))

    with pytest.raises(FDCError, match=message) as exc_info:
        await client.get_food(1)
    assert "secret-key" not in str(exc_info.value)


@respx.mock
async def test_network_errors_are_wrapped(client):
    respx.get(f"{BASE_URL}/food/1").mock(side_effect=httpx.ConnectError("boom"))

    with pytest.raises(FDCError, match="Could not reach"):
        await client.get_food(1)


def test_requires_api_key():
    with pytest.raises(ValueError):
        FDCClient("")
