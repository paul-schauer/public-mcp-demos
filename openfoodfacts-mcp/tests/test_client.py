import httpx
import pytest
import respx

from openfoodfacts_mcp.client import (
    BASE_URL,
    USER_AGENT,
    OFFClient,
    OFFError,
    RateLimiter,
    validate_barcode,
    validate_tag,
)


@pytest.fixture
async def client():
    c = OFFClient()
    yield c
    await c.aclose()


@respx.mock
async def test_get_product_sends_user_agent_and_fields(client):
    route = respx.get(f"{BASE_URL}/api/v2/product/3017620422003.json").mock(
        return_value=httpx.Response(200, json={"status": 1, "product": {"code": "3017620422003"}})
    )

    product = await client.get_product("3017620422003", "code,product_name")

    assert product == {"code": "3017620422003"}
    request = route.calls.last.request
    assert request.headers["User-Agent"] == USER_AGENT
    assert request.url.params["fields"] == "code,product_name"


@respx.mock
@pytest.mark.parametrize("response", [httpx.Response(404, json={"status": 0}), httpx.Response(200, json={"status": 0})])
async def test_missing_product_raises_not_found(client, response):
    respx.get(f"{BASE_URL}/api/v2/product/0000000000000.json").mock(return_value=response)

    with pytest.raises(OFFError, match="No product found for barcode 0000000000000"):
        await client.get_product("0000000000000")


@respx.mock
@pytest.mark.parametrize(("status", "message"), [(429, "rate limit"), (503, "HTTP 503")])
async def test_http_errors_are_mapped(client, status, message):
    respx.get(f"{BASE_URL}/x").mock(return_value=httpx.Response(status))

    with pytest.raises(OFFError, match=message):
        await client.get("/x", None, client.product_limit)


@respx.mock
async def test_non_json_response_is_reported(client):
    respx.get(f"{BASE_URL}/x").mock(return_value=httpx.Response(200, text="<html>"))

    with pytest.raises(OFFError, match="non-JSON"):
        await client.get("/x", None, client.product_limit)


@pytest.mark.parametrize("bad", ["", "abc", "123", "12345/../../x", "1" * 25, "3017620422003?x=1"])
def test_validate_barcode_rejects_bad_input(bad):
    with pytest.raises(OFFError):
        validate_barcode(bad)


def test_validate_barcode_strips_whitespace():
    assert validate_barcode(" 3017620422003 ") == "3017620422003"


@pytest.mark.parametrize("good", ["en:organic", "breakfast-cereals", "coca-cola", "e330", "crème"])
def test_validate_tag_accepts_tags(good):
    assert validate_tag(good) == good


@pytest.mark.parametrize("bad", ["", "../admin", "a/b", "x.json", "a?b=c", "a b"])
def test_validate_tag_rejects_path_characters(bad):
    with pytest.raises(OFFError):
        validate_tag(bad)


def test_rate_limiter_fails_fast_then_recovers(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr("openfoodfacts_mcp.client.time.monotonic", lambda: now[0])
    limiter = RateLimiter(2, 60, "facet")

    limiter.acquire()
    limiter.acquire()
    with pytest.raises(OFFError, match="2 facet requests per 60s; retry in 60s"):
        limiter.acquire()

    now[0] += 60
    limiter.acquire()
