"""MCP server for Open Food Facts: packaged-food products, nutrition, ingredients and facets."""

from __future__ import annotations

import hmac
import os
from collections.abc import Awaitable
from typing import Annotated, Any, Literal, TypeVar

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from openfoodfacts_mcp.client import KNOWLEDGE_PANEL_URL, OFFClient, OFFError, validate_tag

mcp = MCPServer(
    name="openfoodfacts",
    instructions=(
        "Look up packaged food products from Open Food Facts. Use search_products or "
        "advanced_search to find barcodes, then the barcode tools for full details. "
        "Facet tools are limited to 2 requests per minute, so prefer search when possible. "
        "Data is © Open Food Facts contributors, available under the ODbL."
    ),
    website_url="https://world.openfoodfacts.org/",
)

_client: OFFClient | None = None


def get_client() -> OFFClient:
    global _client
    if _client is None:
        _client = OFFClient()
    return _client


def set_client(client: OFFClient | None) -> None:
    """Replace the shared client (used by tests)."""
    global _client
    _client = client


T = TypeVar("T")


async def _call(coro: Awaitable[T]) -> T:
    try:
        return await coro
    except OFFError as exc:
        raise ToolError(str(exc)) from None


Barcode = Annotated[str, Field(description="Product barcode (EAN-13, UPC-A, ...), e.g. '3017620422003'")]
Page = Annotated[int, Field(ge=1)]
SortBy = Literal["popularity", "product_name", "created_t", "last_modified_t"]

SUMMARY_FIELDS = (
    "code,product_name,brands,categories,labels,quantity,serving_size,"
    "nutriscore_grade,ecoscore_grade,nova_group,image_url"
)
NUTRITION_FIELDS = "code,product_name,brands,nutriments,nutriscore_grade,nutriscore_score,serving_size,serving_quantity"
INGREDIENT_FIELDS = (
    "code,product_name,brands,ingredients_text,ingredients,allergens,allergens_tags,traces,traces_tags,"
    "additives_tags,additives_n,nova_group,ingredients_analysis_tags,labels_tags"
)
PER_100G = {
    "energy_kcal": "energy-kcal",
    "energy_kj": "energy-kj",
    "fat": "fat",
    "saturated_fat": "saturated-fat",
    "trans_fat": "trans-fat",
    "cholesterol": "cholesterol",
    "carbohydrates": "carbohydrates",
    "sugars": "sugars",
    "fiber": "fiber",
    "proteins": "proteins",
    "salt": "salt",
    "sodium": "sodium",
    "calcium": "calcium",
    "iron": "iron",
    "vitamin_a": "vitamin-a",
    "vitamin_c": "vitamin-c",
}
PER_SERVING = ("energy_kcal", "fat", "carbohydrates", "sugars", "proteins", "salt")

# Singular facet names map to URL segments; the plural list endpoints add an "s".
FACETS = {
    "category": "category",
    "brand": "brand",
    "label": "label",
    "additive": "additive",
    "allergen": "allergen",
    "country": "country",
    "ingredient": "ingredient",
    "store": "store",
    "origin": "origin",
    "state": "state",
    "packaging": "packaging",
    "nutrition_grade": "nutrition-grade",
    "nova_group": "nova-group",
    "ecoscore_grade": "ecoscore-grade",
}
Facet = Literal[
    "category",
    "brand",
    "label",
    "additive",
    "allergen",
    "country",
    "ingredient",
    "store",
    "origin",
    "state",
    "packaging",
    "nutrition_grade",
    "nova_group",
    "ecoscore_grade",
]
FacetList = Literal[
    "categories",
    "brands",
    "labels",
    "additives",
    "allergens",
    "countries",
    "ingredients",
    "stores",
    "origins",
    "states",
    "packaging",
    "nutrition_grades",
    "nova_groups",
    "ecoscore_grades",
]
TaxonomyType = Literal[
    "categories",
    "brands",
    "labels",
    "ingredients",
    "additives",
    "allergens",
    "countries",
    "stores",
    "origins",
    "states",
    "packaging_shapes",
    "packaging_materials",
    "languages",
    "traces",
]


def summarize(product: dict[str, Any]) -> dict[str, Any]:
    return {field: product.get(field, "") for field in SUMMARY_FIELDS.split(",")}


def nutrition(product: dict[str, Any]) -> dict[str, Any]:
    n = product.get("nutriments", {})
    per_100g = {key: n.get(f"{off}_100g") for key, off in PER_100G.items()}
    return {
        "barcode": product.get("code", ""),
        "product_name": product.get("product_name", ""),
        "brands": product.get("brands", ""),
        "serving_size": product.get("serving_size", ""),
        "nutriscore": {"grade": product.get("nutriscore_grade", ""), "score": product.get("nutriscore_score")},
        "per_100g": per_100g,
        "per_serving": {key: n.get(f"{PER_100G[key]}_serving") for key in PER_SERVING},
    }


def ingredients(product: dict[str, Any]) -> dict[str, Any]:
    analysis = product.get("ingredients_analysis_tags", [])
    is_vegan = "en:vegan" in analysis
    return {
        "barcode": product.get("code", ""),
        "product_name": product.get("product_name", ""),
        "brands": product.get("brands", ""),
        "ingredients_text": product.get("ingredients_text", ""),
        "ingredients": [
            {k: ing.get(k) for k in ("id", "text", "percent_estimate", "vegan", "vegetarian")}
            for ing in product.get("ingredients", [])[:20]
        ],
        "allergens": {"text": product.get("allergens", ""), "tags": product.get("allergens_tags", [])},
        "traces": {"text": product.get("traces", ""), "tags": product.get("traces_tags", [])},
        "additives": {"count": product.get("additives_n", 0), "tags": product.get("additives_tags", [])},
        "nova_group": product.get("nova_group"),
        "analysis": {
            "is_vegan": is_vegan,
            "is_vegetarian": is_vegan or "en:vegetarian" in analysis,
            "is_palm_oil_free": "en:palm-oil-free" in analysis,
            "tags": analysis,
        },
        "labels": product.get("labels_tags", []),
    }


def product_page(data: dict[str, Any], page: int, page_size: int, full: bool = False) -> dict[str, Any]:
    products = data.get("products", [])
    return {
        "count": data.get("count", 0),
        "page": data.get("page", page),
        "page_size": data.get("page_size", page_size),
        "page_count": data.get("page_count"),
        "products": products if full else [summarize(p) for p in products],
    }


# --- Product lookups ---------------------------------------------------------------------------


@mcp.tool()
async def get_product_by_barcode(barcode: Barcode) -> dict[str, Any]:
    """Get a product's summary, nutrition and ingredients in one call."""
    product = await _call(get_client().get_product(barcode))
    return {"product": summarize(product), "nutrition": nutrition(product), "ingredients": ingredients(product)}


@mcp.tool()
async def get_product_nutrition(barcode: Barcode) -> dict[str, Any]:
    """Get nutrition facts per 100 g and per serving, plus the Nutri-Score."""
    return nutrition(await _call(get_client().get_product(barcode, NUTRITION_FIELDS)))


@mcp.tool()
async def get_product_ingredients(barcode: Barcode) -> dict[str, Any]:
    """Get ingredients, allergens, traces, additives, NOVA group and vegan/vegetarian/palm-oil analysis."""
    return ingredients(await _call(get_client().get_product(barcode, INGREDIENT_FIELDS)))


@mcp.tool()
async def get_products_by_barcodes(
    barcodes: Annotated[list[Barcode], Field(min_length=1, max_length=100)],
) -> dict[str, Any]:
    """Look up to 100 products at once and report which barcodes weren't found."""
    client = get_client()

    async def fetch() -> Any:
        codes = [c.strip() for c in barcodes]
        for code in codes:
            if not code.isdigit():
                raise OFFError(f"Invalid barcode {code!r}")
        params = {"code": ",".join(codes), "fields": SUMMARY_FIELDS, "page_size": len(codes)}
        return codes, await client.get("/api/v2/search", params, client.search_limit)

    codes, data = await _call(fetch())
    products = data.get("products", [])
    found = {p.get("code") for p in products}
    return {
        "found": [summarize(p) for p in products],
        "not_found": [c for c in codes if c not in found],
    }


# --- Search ------------------------------------------------------------------------------------


@mcp.tool()
async def search_products(
    query: Annotated[str, Field(min_length=1, max_length=200, description="Product name, brand or category")],
    page: Page = 1,
    page_size: Annotated[int, Field(ge=1, le=100)] = 10,
    sort_by: SortBy = "popularity",
) -> dict[str, Any]:
    """Full-text search for products. Limited to 10 searches per minute."""
    client = get_client()
    params = {"search_terms": query, "page": page, "page_size": page_size, "sort_by": sort_by, "json": 1}
    data = await _call(client.get("/cgi/search.pl", params, client.search_limit))
    return {"query": query, **product_page(data, page, page_size)}


@mcp.tool()
async def advanced_search(
    categories: str | None = None,
    brands: str | None = None,
    labels: str | None = None,
    nutrition_grades: Annotated[str | None, Field(description="Nutri-Score grade a-e")] = None,
    nova_groups: Annotated[str | None, Field(description="NOVA processing group 1-4")] = None,
    ecoscore_grades: str | None = None,
    allergens: str | None = None,
    countries: str | None = None,
    ingredients: str | None = None,
    additives: Annotated[str | None, Field(description="E-number, e.g. 'e330'")] = None,
    states: str | None = None,
    page: Page = 1,
    page_size: Annotated[int, Field(ge=1, le=100)] = 24,
    sort_by: SortBy = "popularity",
) -> dict[str, Any]:
    """Filter products by tags, e.g. categories='breakfast-cereals' and nutrition_grades='a'.
    Separate multiple values with commas (AND) or '|' (OR)."""
    filters = {
        "categories_tags_en": categories,
        "brands_tags": brands,
        "labels_tags_en": labels,
        "nutrition_grades_tags": nutrition_grades,
        "nova_groups_tags": nova_groups,
        "ecoscore_grades_tags": ecoscore_grades,
        "allergens_tags": allergens,
        "countries_tags_en": countries,
        "ingredients_tags_en": ingredients,
        "additives_tags": additives,
        "states_tags": states,
    }
    client = get_client()
    params: dict[str, Any] = {"page": page, "page_size": page_size, "sort_by": sort_by, "fields": SUMMARY_FIELDS}
    params.update({key: value for key, value in filters.items() if value})
    data = await _call(client.get("/api/v2/search", params, client.search_limit))
    return product_page(data, page, page_size)


@mcp.tool()
async def get_taxonomy_suggestions(
    tagtype: TaxonomyType,
    term: Annotated[str, Field(min_length=1, max_length=100)],
    limit: Annotated[int, Field(ge=1, le=100)] = 10,
) -> dict[str, Any]:
    """Autocomplete a tag value, e.g. tagtype='categories', term='choco'."""
    client = get_client()
    params = {"tagtype": tagtype, "term": term, "limit": limit}
    data = await _call(client.get("/cgi/suggest.pl", params, client.search_limit))
    return {"tagtype": tagtype, "term": term, "suggestions": data[:limit] if isinstance(data, list) else []}


# --- Facets (Open Food Facts allows 2 requests per minute) -------------------------------------


@mcp.tool()
async def list_facets(facet_type: FacetList, page: Page = 1) -> dict[str, Any]:
    """List the values of a facet with product counts, e.g. all labels. Limited to 2 per minute."""
    client = get_client()
    data = await _call(client.get(f"/{facet_type}.json", {"page": page}, client.facet_limit))
    tags = data.get("tags", [])
    return {
        "facet_type": facet_type,
        "count": data.get("count", len(tags)),
        "page": page,
        "values": [{k: t.get(k) for k in ("id", "name", "products")} for t in tags],
    }


@mcp.tool()
async def get_products_by_facets(
    facets: Annotated[
        dict[Facet, str],
        Field(
            min_length=1,
            max_length=4,
            description="Facet filters, e.g. {'category': 'breakfast-cereals', 'label': 'organic'}",
        ),
    ],
    page: Page = 1,
) -> dict[str, Any]:
    """Get products matching one or more facet values (AND). Limited to 2 per minute."""
    client = get_client()

    async def fetch() -> Any:
        path = "/".join(f"{FACETS[f]}/{validate_tag(v, 'facet value')}" for f, v in facets.items())
        return await client.get(f"/{path}.json", {"page": page}, client.facet_limit)

    data = await _call(fetch())
    return {"facets": facets, **product_page(data, page, 24)}


@mcp.tool()
async def get_facet_knowledge_panel(
    facet_type: Literal["category", "brand", "label", "additive", "allergen", "country", "ingredient", "origin"],
    facet_value: Annotated[str, Field(description="Tag value, e.g. 'en:organic'")],
    language: Annotated[str, Field(pattern=r"^[a-z]{2}$")] = "en",
) -> dict[str, Any]:
    """Get the explanatory "knowledge panel" Open Food Facts shows for a facet value."""
    client = get_client()

    async def fetch() -> Any:
        params = {"facet_tag": facet_type, "value_tag": validate_tag(facet_value, "facet value"), "lang_code": language}
        return await client.get(KNOWLEDGE_PANEL_URL, params, client.facet_limit)

    data = await _call(fetch())
    return {"facet_type": facet_type, "facet_value": facet_value, "panels": data.get("knowledge_panels", data)}


# --- HTTP transport ----------------------------------------------------------------------------


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
            "Refusing to serve HTTP without MCP_BEARER_TOKEN, since anyone could use up this "
            "server's Open Food Facts rate limit. Set ALLOW_UNAUTHENTICATED=1 to override for local testing."
        )
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(create_http_app(token), host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
